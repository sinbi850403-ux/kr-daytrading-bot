"""메인 봇 로직 테스트."""
import pytest
from unittest.mock import Mock
from datetime import datetime
import pytz
from config import Config
from main import DayBot
import signals as sig_mod
from tests.conftest import make_df5

KST = pytz.timezone("Asia/Seoul")


class TestDayBotTradingHours:
    def setup_method(self):
        self.cfg = Config(scan_start="0905", scan_end="1525", is_paper=True)
        self.mock_client = Mock()
        self.mock_scanner = Mock()
        self.mock_notifier = Mock()
        self.bot = DayBot(self.cfg, self.mock_client, self.mock_scanner, self.mock_notifier)

    def test_trading_hours_within_range(self):
        now = datetime(2024, 1, 1, 10, 0, tzinfo=KST)  # 평일 오전
        assert self.bot._is_trading_hours(now) is True

    def test_trading_hours_start_boundary(self):
        now = datetime(2024, 1, 1, 9, 5, tzinfo=KST)  # 정확히 0905
        assert self.bot._is_trading_hours(now) is True

    def test_trading_hours_end_boundary(self):
        now = datetime(2024, 1, 1, 15, 25, tzinfo=KST)  # 정확히 1525
        assert self.bot._is_trading_hours(now) is True

    def test_trading_hours_before_open(self):
        now = datetime(2024, 1, 1, 9, 0, tzinfo=KST)  # 0900 (0905 전)
        assert self.bot._is_trading_hours(now) is False

    def test_trading_hours_after_close(self):
        now = datetime(2024, 1, 1, 15, 30, tzinfo=KST)  # 1530 (1525 후)
        assert self.bot._is_trading_hours(now) is False

    def test_trading_hours_weekend_saturday(self):
        now = datetime(2024, 1, 6, 10, 0, tzinfo=KST)  # 토요일
        assert self.bot._is_trading_hours(now) is False

    def test_trading_hours_weekend_sunday(self):
        now = datetime(2024, 1, 7, 10, 0, tzinfo=KST)  # 일요일
        assert self.bot._is_trading_hours(now) is False


class TestDayBotRunCycle:
    def setup_method(self):
        self.cfg = Config(scan_start="0905", scan_end="1525", is_paper=True)
        self.mock_client = Mock()
        self.mock_scanner = Mock()
        self.mock_notifier = Mock()
        self.bot = DayBot(self.cfg, self.mock_client, self.mock_scanner, self.mock_notifier)

    def test_run_cycle_outside_hours_skips(self):
        now = datetime(2024, 1, 1, 16, 0, tzinfo=KST)  # 장 마감 후
        self.bot.run_cycle(now=now)
        self.mock_scanner.scan.assert_not_called()

    def test_run_cycle_generates_signals(self):
        signal = sig_mod.DaySignal(
            symbol="000100",
            ob_low=99.0,
            ob_high=100.0,
            entry_price=99.5,
            rvol=1.8,
            vwap=98.0,
            timestamp="10:30"
        )
        self.mock_scanner.scan.return_value = [("테스트", signal)]
        now = datetime(2024, 1, 1, 10, 30, tzinfo=KST)
        self.bot.run_cycle(now=now)
        self.mock_notifier.alert_day_signal.assert_called_once_with("테스트", signal)

    def test_run_cycle_prevents_duplicate_alerts_same_day(self):
        signal = sig_mod.DaySignal(
            symbol="000100",
            ob_low=99.0,
            ob_high=100.0,
            entry_price=99.5,
            rvol=1.8,
            vwap=98.0
        )
        self.mock_scanner.scan.return_value = [("테스트", signal)]
        now = datetime(2024, 1, 1, 10, 30, tzinfo=KST)

        # 첫 번째 사이클
        self.bot.run_cycle(now=now)
        assert self.mock_notifier.alert_day_signal.call_count == 1

        # 두 번째 사이클 (같은 날)
        now2 = datetime(2024, 1, 1, 11, 0, tzinfo=KST)
        self.bot.run_cycle(now=now2)
        # 중복 알림 방지
        assert self.mock_notifier.alert_day_signal.call_count == 1

    def test_run_cycle_allows_alert_next_day(self):
        signal = sig_mod.DaySignal(
            symbol="000100",
            ob_low=99.0,
            ob_high=100.0,
            entry_price=99.5,
            rvol=1.8,
            vwap=98.0
        )
        self.mock_scanner.scan.return_value = [("테스트", signal)]

        # 1월 1일
        now1 = datetime(2024, 1, 1, 10, 30, tzinfo=KST)
        self.bot.run_cycle(now=now1)
        assert self.mock_notifier.alert_day_signal.call_count == 1

        # 1월 2일 (다음날)
        now2 = datetime(2024, 1, 2, 10, 30, tzinfo=KST)
        self.bot.run_cycle(now=now2)
        # 새로운 날이므로 다시 알림
        assert self.mock_notifier.alert_day_signal.call_count == 2

    def test_run_cycle_clears_old_dates_from_alert_set(self):
        signal1 = sig_mod.DaySignal(
            symbol="000100",
            ob_low=99.0,
            ob_high=100.0,
            entry_price=99.5,
            rvol=1.8,
            vwap=98.0
        )
        signal2 = sig_mod.DaySignal(
            symbol="000200",
            ob_low=49.0,
            ob_high=50.0,
            entry_price=49.5,
            rvol=1.5,
            vwap=48.0
        )

        # 1월 1일: 첫 신호
        self.mock_scanner.scan.return_value = [("테스트1", signal1)]
        now1 = datetime(2024, 1, 1, 10, 30, tzinfo=KST)
        self.bot.run_cycle(now=now1)
        assert "000100_20240101" in self.bot.alerted

        # 1월 2일: 다른 신호
        self.mock_scanner.scan.return_value = [("테스트2", signal2)]
        now2 = datetime(2024, 1, 2, 10, 30, tzinfo=KST)
        self.bot.run_cycle(now=now2)

        # 1월 1일 데이터는 제거되어야 함
        assert "000100_20240101" not in self.bot.alerted
        assert "000200_20240102" in self.bot.alerted

    def test_run_cycle_multiple_signals_same_cycle(self):
        signal1 = sig_mod.DaySignal(
            symbol="000100",
            ob_low=99.0,
            ob_high=100.0,
            entry_price=99.5,
            rvol=1.8,
            vwap=98.0
        )
        signal2 = sig_mod.DaySignal(
            symbol="000200",
            ob_low=49.0,
            ob_high=50.0,
            entry_price=49.5,
            rvol=1.5,
            vwap=48.0
        )
        self.mock_scanner.scan.return_value = [
            ("테스트1", signal1),
            ("테스트2", signal2)
        ]
        now = datetime(2024, 1, 1, 10, 30, tzinfo=KST)
        self.bot.run_cycle(now=now)
        assert self.mock_notifier.alert_day_signal.call_count == 2
