"""텔레그램 알림."""
import logging
import requests
from config import Config
from signals import DaySignal

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._base = f"https://api.telegram.org/bot{cfg.telegram_token}"

    def send(self, text: str) -> None:
        if not self.cfg.telegram_token or not self.cfg.telegram_chat:
            log.warning("텔레그램 미설정 — 알림 스킵")
            return
        try:
            requests.post(f"{self._base}/sendMessage", json={
                "chat_id": self.cfg.telegram_chat,
                "text": text, "parse_mode": "HTML",
            }, timeout=10)
        except Exception as e:   # noqa: BLE001
            log.error("텔레그램 전송 실패: %s", e)

    def alert_day_signal(self, name: str, sig: DaySignal) -> None:
        r = sig.entry_price - sig.sl_price
        text = (
            f"📊 <b>[{name}] {sig.symbol} 단타신호</b>\n"
            f"OB구간: {sig.ob_low:,.0f} ~ {sig.ob_high:,.0f}원\n"
            f"현재가: {sig.entry_price:,.0f}원\n"
            f"손절: {sig.sl_price:,.0f}원 (OB 하단) | R: {r:,.0f}원\n"
            f"익절1: {sig.tp1_price:,.0f}원 (1R) | 익절2: {sig.tp2_price:,.0f}원 (2R)\n"
            f"RVOL: {sig.rvol:.1f}x | VWAP: {sig.vwap:,.0f}원\n"
            f"조건: OB진입✅ 양봉✅ RVOL✅ VWAP위✅\n"
            f"⏰ {sig.timestamp}"
        )
        self.send(text)

    def alert_error(self, text: str) -> None:
        self.send(f"🚨 {text}")
