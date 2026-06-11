"""설정 — KIS 인증·텔레그램·단타 파라미터."""
import os
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

_TR_MAP = {
    "min5":     ("FHKST03010200", "FHKST03010200"),  # 5분봉 (모의/실전 동일)
    "price":    ("FHKST01010100", "FHKST01010100"),
    "vol_rank": ("FHPST01710000", "FHPST01710000"),
}

_REAL_BASE  = "https://openapi.koreainvestment.com:9443"
_PAPER_BASE = "https://openapivts.koreainvestment.com:29443"


@dataclass
class Config:
    # KIS 인증
    app_key:      str   = ""
    app_secret:   str   = ""
    cano:         str   = ""
    acnt_prdt_cd: str   = "01"

    # 텔레그램
    telegram_token: str = ""
    telegram_chat:  str = ""

    # 모드
    is_paper: bool = True

    # 스캔
    top_n:         int   = 50
    scan_interval: int   = 180    # 3분
    rate_per_sec:  float = 8.0

    # ICT 파라미터
    swing_n:       int   = 3      # 스윙 포인트 좌우 봉 수
    ob_lookback:   int   = 30     # OB 탐색 범위(봉)
    rvol_threshold: float = 1.5
    rvol_window:   int   = 20

    # 거래시간 (KST HHMM)
    scan_start: str = "0905"
    scan_end:   str = "1525"

    @property
    def base_url(self) -> str:
        return _PAPER_BASE if self.is_paper else _REAL_BASE

    def tr_id(self, action: str) -> str:
        real, paper = _TR_MAP[action]
        return paper if self.is_paper else real

    @classmethod
    def from_env(cls) -> "Config":
        g = os.getenv
        cano, prdt = "", "01"
        acct = g("KIS_ACCOUNT", "")
        if acct:
            if "-" in acct:
                cano, prdt = acct.split("-", 1)
            elif len(acct) >= 10:
                cano, prdt = acct[:8], acct[8:]
            else:
                cano = acct

        def _f(k, d): v = g(k); return float(v) if v not in (None,"") else d
        def _i(k, d): v = g(k); return int(v)   if v not in (None,"") else d

        return cls(
            app_key=g("KIS_APP_KEY",""),
            app_secret=g("KIS_APP_SECRET",""),
            cano=cano, acnt_prdt_cd=prdt,
            telegram_token=g("TELEGRAM_TOKEN",""),
            telegram_chat=g("TELEGRAM_CHAT_ID",""),
            is_paper=g("ENABLE_REAL_TRADING","") not in ("1","YES","true","on"),
            top_n=_i("TOP_N",50),
            scan_interval=_i("SCAN_INTERVAL",180),
            rvol_threshold=_f("RVOL_THRESHOLD",1.5),
        )

    def validate(self) -> None:
        missing = [k for k,v in {
            "KIS_APP_KEY": self.app_key,
            "KIS_APP_SECRET": self.app_secret,
            "TELEGRAM_TOKEN": self.telegram_token,
            "TELEGRAM_CHAT_ID": self.telegram_chat,
            "CANO": self.cano,
        }.items() if not v]
        if missing:
            raise ValueError(f"필수 환경변수 누락: {', '.join(missing)}")
