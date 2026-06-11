"""KIS REST API 래퍼 — 5분봉 특화."""
import time
import logging
import threading
from datetime import datetime

import requests
import pandas as pd
import pytz

from config import Config

log = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

_MIN5_REN = {
    "stck_cntg_hour": "time",
    "stck_oprc": "open", "stck_hgpr": "high",
    "stck_lwpr": "low",  "stck_prpr": "close",
    "acml_vol": "volume",
}


class KISClient:
    def __init__(self, cfg: Config, session=None):
        self.cfg = cfg
        self.session = session or requests.Session()
        self._token_value = None
        self._token_exp   = 0.0
        self._rate_lock   = threading.Lock()
        self._last_call   = 0.0

    def _throttle(self):
        gap = 1.0 / self.cfg.rate_per_sec
        with self._rate_lock:
            now  = time.monotonic()
            wait = self._last_call + gap - now
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _get_token(self):
        if self._token_value and time.time() < self._token_exp:
            return self._token_value
        r = self.session.post(f"{self.cfg.base_url}/oauth2/tokenP", json={
            "grant_type": "client_credentials",
            "appkey": self.cfg.app_key,
            "appsecret": self.cfg.app_secret,
        }, timeout=10)
        r.raise_for_status()
        d = r.json()
        self._token_value = d["access_token"]
        self._token_exp   = time.time() + int(d.get("expires_in", 86400)) - 120
        return self._token_value

    def _headers(self, tr_id):
        return {
            "authorization": f"Bearer {self._get_token()}",
            "appkey":    self.cfg.app_key,
            "appsecret": self.cfg.app_secret,
            "tr_id":     tr_id,
            "custtype":  "P",
            "content-type": "application/json; charset=utf-8",
        }

    def _get(self, path, tr_id, params, retries=2):
        headers = self._headers(tr_id)
        for attempt in range(retries + 1):
            self._throttle()
            try:
                r = self.session.get(f"{self.cfg.base_url}{path}",
                                     headers=headers, params=params, timeout=10)
                if r.status_code == 200:
                    return r.json()
                log.warning("GET %s status=%s (재시도 %d)", path, r.status_code, attempt)
                time.sleep(0.5 * (attempt + 1))
            except requests.RequestException as e:
                log.warning("GET %s 예외 %s (재시도 %d)", path, e, attempt)
                time.sleep(0.5 * (attempt + 1))
        return {}

    def get_min5(self, symbol: str) -> pd.DataFrame:
        """당일 5분봉 조회 (최근 30봉, 과거→현재 정렬)."""
        params = {
            "FID_ETC_CLS_CODE":       "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD":         symbol,
            "FID_INPUT_HOUR_1":       "153000",
            "FID_PW_DATA_INCU_YN":    "N",
        }
        j = self._get("/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                      self.cfg.tr_id("min5"), params)
        rows = j.get("output2") or []
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).rename(columns={k: v for k, v in _MIN5_REN.items()
                                                if k in pd.DataFrame(rows).columns})
        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["close"])
        df = df[df["close"] > 0].iloc[::-1].reset_index(drop=True)
        return df

    def volume_rank(self, blng_cls="1", market="0000"):
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE":  "20171",
            "FID_INPUT_ISCD":         market,
            "FID_DIV_CLS_CODE":       "0",
            "FID_BLNG_CLS_CODE":      blng_cls,
            "FID_TRGT_CLS_CODE":      "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "0000000000",
            "FID_INPUT_PRICE_1": "", "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "", "FID_INPUT_DATE_1": "",
        }
        j = self._get("/uapi/domestic-stock/v1/quotations/volume-rank",
                      self.cfg.tr_id("vol_rank"), params)
        out = []
        for row in (j.get("output") or []):
            code = row.get("mksc_shrn_iscd") or row.get("stck_shrn_iscd")
            name = row.get("hts_kor_isnm")
            if code:
                out.append((code, name))
        return out
