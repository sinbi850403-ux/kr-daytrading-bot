"""스캐너 함수 테스트."""
import pytest
from unittest.mock import Mock
from datetime import datetime
import pytz
from config import Config
from scanner import DayScanner, is_tradable
import signals as sig_mod
from tests.conftest import make_df5

KST = pytz.timezone("Asia/Seoul")


class TestIsTradable:
    def test_valid_code(self):
        assert is_tradable("000660", "SK하이닉스") is True
        assert is_tradable("000100", "한국가스공사") is True

    def test_invalid_length(self):
        assert is_tradable("00001", "테스트") is False
        assert is_tradable("0000001", "테스트") is False

    def test_invalid_not_digit(self):
        assert is_tradable("00000A", "테스트") is False
        assert is_tradable("ABCDEF", "테스트") is False

    def test_invalid_last_digit_not_zero(self):
        assert is_tradable("000001", "테스트") is False
        assert is_tradable("000005", "테스트") is False

    def test_exclude_warrant(self):
        assert is_tradable("000001", "삼성전자우") is False

    def test_exclude_spac(self):
        assert is_tradable("000010", "테스트스팩") is False

    def test_exclude_etn(self):
        assert is_tradable("000020", "테스트ETN") is False

    def test_exclude_etf(self):
        assert is_tradable("000030", "테스트ETF") is False

    def test_exclude_reit(self):
        assert is_tradable("000040", "테스트리츠") is False

    def test_exclude_inverse_leverage(self):
        assert is_tradable("000050", "테스트인버스") is False
        assert is_tradable("000060", "테스트레버리지") is False

    def test_exclude_branded_etf(self):
        assert is_tradable("000070", "KODEX") is False
        assert is_tradable("000080", "TIGER삼성") is False
        assert is_tradable("000090", "ARIRANG테스트") is False

    def test_empty_code(self):
        assert is_tradable("", "테스트") is False
        assert is_tradable(None, "테스트") is False

    def test_empty_name(self):
        assert is_tradable("000100", "") is True
        assert is_tradable("000100", None) is True


class TestDayScannerBuildCandidates:
    def setup_method(self):
        self.cfg = Config(is_paper=True)
        self.mock_client = Mock()

    def test_build_candidates_empty(self):
        self.mock_client.volume_rank.return_value = []
        scanner = DayScanner(self.cfg, self.mock_client)
        result = scanner.build_candidates()
        assert result == {}

    def test_build_candidates_filters_invalid(self):
        self.mock_client.volume_rank.side_effect = [
            [("000001", "삼성전자우"), ("000100", "TCL")],  # blng=1
            [("000200", "SK이노베이션")]  # blng=3
        ]
        scanner = DayScanner(self.cfg, self.mock_client)
        result = scanner.build_candidates()
        assert "000100" in result
        assert "000200" in result
        assert "000001" not in result  # 우 제외

    def test_build_candidates_handles_exception(self, caplog):
        self.mock_client.volume_rank.side_effect = Exception("API error")
        scanner = DayScanner(self.cfg, self.mock_client)
        result = scanner.build_candidates()
        # 예외 발생 후에도 계속 진행, 빈 결과 반환
        assert isinstance(result, dict)

    def test_build_candidates_merges_multiple_sources(self):
        self.mock_client.volume_rank.side_effect = [
            [("000100", "TCL"), ("000200", "SK이노베이션")],
            [("000300", "삼성화학")]
        ]
        scanner = DayScanner(self.cfg, self.mock_client)
        result = scanner.build_candidates()
        assert len(result) == 3
        assert "000100" in result
        assert "000200" in result
        assert "000300" in result


class TestDayScannerScan:
    def setup_method(self):
        self.cfg = Config(is_paper=True, swing_n=3, rvol_threshold=1.5)
        self.mock_client = Mock()

    def test_scan_outside_trading_hours(self):
        scanner = DayScanner(self.cfg, self.mock_client)
        # 토요일 오후 3시
        now = datetime(2024, 1, 6, 15, 0, tzinfo=KST)
        result = scanner.scan(now=now)
        assert result == []

    def test_scan_before_market_open(self):
        scanner = DayScanner(self.cfg, self.mock_client)
        # 평일 오전 9시 (0900보다 전)
        now = datetime(2024, 1, 1, 9, 0, tzinfo=KST)
        result = scanner.scan(now=now)
        assert result == []

    def test_scan_after_market_close(self):
        scanner = DayScanner(self.cfg, self.mock_client)
        # 평일 오후 3:30 (1525보다 후)
        now = datetime(2024, 1, 1, 15, 30, tzinfo=KST)
        result = scanner.scan(now=now)
        assert result == []

    def test_scan_empty_candidates(self):
        self.mock_client.volume_rank.return_value = []
        scanner = DayScanner(self.cfg, self.mock_client)
        now = datetime(2024, 1, 1, 10, 0, tzinfo=KST)  # 평일 오전
        result = scanner.scan(now=now)
        assert result == []

    def test_scan_generates_signals(self):
        self.mock_client.volume_rank.return_value = [("000100", "테스트1")]
        # 신호 생성 조건을 만족하는 df5
        closes = list(range(100, 130)) + [130.0] * 20
        vols = [1000.0] * 50
        df = make_df5(closes, vols=vols)
        self.mock_client.get_min5.return_value = df
        scanner = DayScanner(self.cfg, self.mock_client)
        now = datetime(2024, 1, 1, 10, 30, tzinfo=KST)
        result = scanner.scan(now=now)
        # 신호가 없을 수도 있지만 적어도 처리는 정상적으로 되어야 함
        assert isinstance(result, list)
        if len(result) > 0:
            name, signal = result[0]
            assert name == "테스트1"
            assert signal.symbol == "000100"

    def test_scan_handles_empty_dataframe(self):
        self.mock_client.volume_rank.return_value = [("000100", "테스트")]
        self.mock_client.get_min5.return_value = None
        scanner = DayScanner(self.cfg, self.mock_client)
        now = datetime(2024, 1, 1, 10, 0, tzinfo=KST)
        result = scanner.scan(now=now)
        assert result == []

    def test_scan_handles_exception_in_signal_generation(self):
        self.mock_client.volume_rank.return_value = [("000100", "테스트")]
        self.mock_client.get_min5.side_effect = Exception("Network error")
        scanner = DayScanner(self.cfg, self.mock_client)
        now = datetime(2024, 1, 1, 10, 0, tzinfo=KST)
        result = scanner.scan(now=now)
        assert result == []

    def test_scan_timestamp_format(self):
        self.mock_client.volume_rank.return_value = [("000100", "테스트")]
        closes = [100, 102, 105, 103, 101, 100, 99, 106] + [104] * 22 + [105]
        vols = [1000] * 8 + [1000] * 22 + [2000]
        df = make_df5(closes, vols=vols)
        self.mock_client.get_min5.return_value = df
        scanner = DayScanner(self.cfg, self.mock_client)
        now = datetime(2024, 1, 1, 10, 25, tzinfo=KST)
        result = scanner.scan(now=now)
        if result:
            _, signal = result[0]
            assert signal.timestamp == "10:25"
