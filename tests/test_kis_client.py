"""KIS 클라이언트 테스트."""
import pytest
from unittest.mock import Mock, patch
import pandas as pd
from config import Config
from kis_client import KISClient


class TestKISClientGetMin5:
    def setup_method(self):
        self.cfg = Config(
            app_key="test_key",
            app_secret="test_secret",
            cano="12345678",
            is_paper=True
        )

    def test_get_min5_empty_response(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={})
        result = client.get_min5("000001")
        assert result.empty

    def test_get_min5_no_output2(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={"output": []})
        result = client.get_min5("000001")
        assert result.empty

    def test_get_min5_parse_candles(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={
            "output2": [
                {
                    "stck_cntg_hour": "093000",
                    "stck_oprc": "1000",
                    "stck_hgpr": "1050",
                    "stck_lwpr": "950",
                    "stck_prpr": "1020",
                    "acml_vol": "1000000",
                },
                {
                    "stck_cntg_hour": "093500",
                    "stck_oprc": "1020",
                    "stck_hgpr": "1080",
                    "stck_lwpr": "1010",
                    "stck_prpr": "1050",
                    "acml_vol": "1500000",
                },
            ]
        })
        result = client.get_min5("000001")
        assert len(result) == 2
        assert "open" in result.columns or "stck_oprc" in result.columns
        assert "high" in result.columns or "stck_hgpr" in result.columns
        assert "low" in result.columns or "stck_lwpr" in result.columns
        assert "close" in result.columns or "stck_prpr" in result.columns
        assert "volume" in result.columns or "acml_vol" in result.columns

    def test_get_min5_reverse_chronological(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={
            "output2": [
                {"stck_prpr": "1050", "stck_oprc": "1000", "stck_hgpr": "1050",
                 "stck_lwpr": "950", "acml_vol": "100", "stck_cntg_hour": "153000"},
                {"stck_prpr": "1020", "stck_oprc": "1010", "stck_hgpr": "1030",
                 "stck_lwpr": "1000", "acml_vol": "100", "stck_cntg_hour": "152500"},
            ]
        })
        result = client.get_min5("000001")
        # API 반환이 최신→과거 순이므로, 역순 정렬으로 과거→현재가 되어야 함
        assert result.iloc[0]["close"] == 1020  # 152500 (과거)
        assert result.iloc[1]["close"] == 1050  # 153000 (현재)

    def test_get_min5_filters_zero_close(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={
            "output2": [
                {"stck_prpr": "0", "stck_oprc": "0", "stck_hgpr": "0",
                 "stck_lwpr": "0", "acml_vol": "0", "stck_cntg_hour": "093000"},
                {"stck_prpr": "1000", "stck_oprc": "900", "stck_hgpr": "1000",
                 "stck_lwpr": "800", "acml_vol": "100", "stck_cntg_hour": "093500"},
            ]
        })
        result = client.get_min5("000001")
        assert len(result) == 1
        assert result.iloc[0]["close"] == 1000

    def test_get_min5_coerces_to_numeric(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={
            "output2": [
                {"stck_prpr": "1000", "stck_oprc": "900", "stck_hgpr": "1100",
                 "stck_lwpr": "800", "acml_vol": "500000", "stck_cntg_hour": "093000"},
            ]
        })
        result = client.get_min5("000001")
        assert result["close"].dtype in [float, int]
        assert result["volume"].dtype in [float, int]


class TestKISClientVolumeRank:
    def setup_method(self):
        self.cfg = Config(
            app_key="test_key",
            app_secret="test_secret",
            cano="12345678",
            is_paper=True
        )

    def test_volume_rank_empty(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={})
        result = client.volume_rank()
        assert result == []

    def test_volume_rank_with_data(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={
            "output": [
                {
                    "mksc_shrn_iscd": "000001",
                    "hts_kor_isnm": "테스트주식"
                },
                {
                    "stck_shrn_iscd": "000002",
                    "hts_kor_isnm": "테스트주식2"
                },
            ]
        })
        result = client.volume_rank(blng_cls="1")
        assert len(result) == 2
        assert result[0][0] == "000001"
        assert result[0][1] == "테스트주식"
        assert result[1][0] == "000002"

    def test_volume_rank_prefers_mksc_over_stck(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={
            "output": [
                {
                    "mksc_shrn_iscd": "000001",
                    "stck_shrn_iscd": "000099",
                    "hts_kor_isnm": "테스트"
                }
            ]
        })
        result = client.volume_rank()
        assert result[0][0] == "000001"

    def test_volume_rank_no_code_skipped(self):
        client = KISClient(self.cfg)
        client._get = Mock(return_value={
            "output": [
                {"hts_kor_isnm": "코드없음"},
                {"mksc_shrn_iscd": "000001", "hts_kor_isnm": "테스트"},
            ]
        })
        result = client.volume_rank()
        assert len(result) == 1
        assert result[0][0] == "000001"


class TestKISClientThrottling:
    def setup_method(self):
        self.cfg = Config(
            app_key="test_key",
            app_secret="test_secret",
            cano="12345678",
            rate_per_sec=10.0,
            is_paper=True
        )

    def test_throttle_enforces_rate(self):
        client = KISClient(self.cfg)
        import time
        start = time.monotonic()
        client._throttle()
        client._throttle()
        elapsed = time.monotonic() - start
        # rate_per_sec=10 → 100ms per call
        assert elapsed >= 0.05  # At least some throttling


class TestKISClientTokenManagement:
    def setup_method(self):
        self.cfg = Config(
            app_key="test_key",
            app_secret="test_secret",
            cano="12345678",
            is_paper=True
        )

    def test_get_token_caches(self):
        session = Mock()
        client = KISClient(self.cfg, session=session)

        session.post.return_value.json.return_value = {
            "access_token": "test_token",
            "expires_in": "3600"
        }
        session.post.return_value.status_code = 200
        session.post.return_value.raise_for_status = Mock()

        token1 = client._get_token()
        token2 = client._get_token()

        assert token1 == token2
        assert session.post.call_count == 1  # Called only once, cached
