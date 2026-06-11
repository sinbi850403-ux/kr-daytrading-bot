"""단타 알림봇 메인 루프."""
import logging
import time
import os
from datetime import datetime

import pytz
from dotenv import load_dotenv

load_dotenv()

from config import Config
from kis_client import KISClient
from scanner import DayScanner
from notify import Notifier
import signals as sig_mod

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")
KST = pytz.timezone("Asia/Seoul")


class DayBot:
    def __init__(self, cfg: Config, client, scanner: DayScanner, notifier: Notifier):
        self.cfg      = cfg
        self.client   = client
        self.scanner  = scanner
        self.notifier = notifier
        self.alerted: set = set()   # {symbol_YYYYMMDD} 중복 방지

    def _is_trading_hours(self, now) -> bool:
        if now.weekday() >= 5:
            return False
        hhmm = now.strftime("%H%M")
        return self.cfg.scan_start <= hhmm <= self.cfg.scan_end

    def run_cycle(self, now=None):
        now = now or datetime.now(KST)
        if not self._is_trading_hours(now):
            return
        ds = now.strftime("%Y%m%d")
        for name, sig in self.scanner.scan(now=now):
            key = f"{sig.symbol}_{ds}"
            if key not in self.alerted:
                self.notifier.alert_day_signal(name, sig)
                self.alerted.add(key)
        # 날짜 바뀌면 alerted 초기화
        for key in list(self.alerted):
            if not key.endswith(ds):
                self.alerted.discard(key)


def main():
    cfg = Config.from_env()
    cfg.validate()
    client   = KISClient(cfg)
    scanner  = DayScanner(cfg, client)
    notifier = Notifier(cfg)
    bot      = DayBot(cfg, client, scanner, notifier)
    mode = "모의" if cfg.is_paper else "⚠️실전"
    notifier.send(f"📊 단타 알림봇 ON [{mode}]\nRVOL {cfg.rvol_threshold}x | 3분 주기")
    while True:
        try:
            bot.run_cycle()
        except Exception as e:   # noqa: BLE001
            log.exception("루프 오류: %s", e)
        time.sleep(cfg.scan_interval)


if __name__ == "__main__":
    main()
