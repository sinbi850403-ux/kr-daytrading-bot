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
        """
        당일 5분봉 조회 (최대 60봉, 과거→현재 정렬).

        페이지네이션:
        - 1차 호출: FID_INPUT_HOUR_1="153000" → 최신 30봉
        - 1차가 30봉 미만이면 종료 (장 초반)
        - 1차가 30봉이면 2차 호출: 가장 오래된 봉의 시각을 FID_INPUT_HOUR_1로
          → 그 시각 이전 30봉 추가 확보
        - 결과: 시간 기준 중복 제거, 과거→현재 오름차순 정렬
        """
        all_rows = []

        # 1차 호출: 최신 데이터
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

        all_rows.extend(rows)

        # 2차 호출: 30봉이 정확히 반환되면 추가 수집
        if len(rows) == 30:
            # 1차 결과의 가장 오래된 봉 시각 추출 (rows는 역순이므로 마지막)
            oldest_time = rows[-1].get("stck_cntg_hour", "")
            if oldest_time:
                params["FID_INPUT_HOUR_1"] = oldest_time
                j2 = self._get("/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                              self.cfg.tr_id("min5"), params)
                rows2 = j2.get("output2") or []
                if rows2:
                    all_rows.extend(rows2)

        # DataFrame 변환
        if not all_rows:
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)
        ren = {k: v for k, v in _MIN5_REN.items() if k in df.columns}
        # 분봉 거래량: cntg_vol(해당 봉 체결량)이 정식 필드. acml_vol은 폴백.
        if "cntg_vol" in df.columns:
            ren["cntg_vol"] = "volume"
        elif "acml_vol" in df.columns:
            ren["acml_vol"] = "volume"
        df = df.rename(columns=ren)

        # 수치 변환
        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        # 0 종가 필터링
        df = df.dropna(subset=["close"])
        df = df[df["close"] > 0]

        # 시간 기준 중복 제거 (time 컬럼이 있으면 사용)
        if "time" in df.columns:
            df = df.drop_duplicates(subset=["time"], keep="first")

        # 역순 정렬 (API 반환이 최신→과거) → 과거→현재로 정렬
        df = df.iloc[::-1].reset_index(drop=True)

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
