"""후보 선정 + 신호 스캔."""
import logging
from datetime import datetime
from typing import List, Tuple

import pytz

import signals as sig_mod
from config import Config

log = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

_BAD = ["우", "스팩", "ETN", "ETF", "리츠", "인버스", "레버리지",
        "KODEX", "TIGER", "ARIRANG", "KBSTAR", "HANARO", "PLUS",
        "ACE", "SOL", "RISE"]


def is_tradable(code: str, name: str) -> bool:
    if not code or len(code) != 6 or not code.isdigit():
        return False
    if code[-1] != "0":
        return False
    return not any(b in (name or "") for b in _BAD)


class DayScanner:
    def __init__(self, cfg: Config, client):
        self.cfg    = cfg
        self.client = client

    def build_candidates(self) -> dict:
        cand = {}
        for blng in ("1", "3"):
            try:
                for code, name in self.client.volume_rank(blng):
                    if is_tradable(code, name):
                        cand[code] = name
            except Exception as e:   # noqa: BLE001
                log.error("후보 소스 오류 (blng=%s): %s", blng, e)
        return cand

    def scan(self, now=None) -> List[Tuple[str, sig_mod.DaySignal]]:
        now = now or datetime.now(KST)
        ts  = now.strftime("%H:%M")
        cand = self.build_candidates()
        if not cand:
            log.warning("단타 스캔: 후보 0개")
            return []
        log.info("단타 스캔 시작: 후보 %d개", len(cand))
        signals = []
        for code, name in cand.items():
            try:
                df5 = self.client.get_min5(code)
                if df5 is None or df5.empty:
                    continue
                s = sig_mod.generate_signal(code, df5, self.cfg, timestamp=ts)
                if s:
                    signals.append((name, s))
            except Exception as e:   # noqa: BLE001
                log.error("단타 스캔 오류 %s: %s", code, e)
        log.info("단타 스캔 완료: 신호 %d개", len(signals))
        return signals
