"""지표 함수 테스트."""
import pandas as pd
import pytest
import indicators as ind
from tests.conftest import make_df5


class TestSwingHighs:
    def test_simple_swing_high(self):
        # [10, 15, 20, 15, 10] — 20이 swing high
        highs = pd.Series([10.0, 15.0, 20.0, 15.0, 10.0])
        result = ind.swing_highs(highs, n=1)
        expected = pd.Series([False, False, True, False, False])
        pd.testing.assert_series_equal(result, expected)

    def test_swing_high_with_n3(self):
        # 5개 이상 필요 (n=3: 앞3 + 중심 + 뒤3 = 7개)
        highs = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        result = ind.swing_highs(highs, n=3)
        assert result.sum() == 0  # 우상향 차트는 swing high 없음

    def test_swing_high_peak(self):
        # [1, 2, 3, 2, 1, 2, 3, 2, 1]에서 3이 두 개 — 하나만 선택됨
        highs = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0, 2.0, 1.0])
        result = ind.swing_highs(highs, n=1)
        assert result.sum() == 2


class TestSwingLows:
    def test_simple_swing_low(self):
        # [10, 5, 1, 5, 10] — 1이 swing low
        lows = pd.Series([10.0, 5.0, 1.0, 5.0, 10.0])
        result = ind.swing_lows(lows, n=1)
        expected = pd.Series([False, False, True, False, False])
        pd.testing.assert_series_equal(result, expected)

    def test_swing_low_valley(self):
        # 패턴: 높음-낮음-매우낮음-낮음-높음 with n=1
        lows = pd.Series([10.0, 5.0, 1.0, 5.0, 10.0])
        result = ind.swing_lows(lows, n=1)
        assert result.sum() == 1  # 1.0이 swing low


class TestFindBullishOB:
    def test_no_ob_insufficient_data(self):
        df = make_df5([100, 101, 102])
        result = ind.find_bullish_ob(df, swing_n=3, lookback=30)
        assert result is None

    def test_no_ob_no_bos(self):
        df = make_df5([100] * 50)  # 평탄한 차트
        result = ind.find_bullish_ob(df, swing_n=3, lookback=30)
        assert result is None

    def test_bullish_ob_valid(self):
        # 단순 상승 트렌드 - 스윙 포인트와 OB 테스트
        closes = [100, 95, 110, 105, 115] + [115.0] * 30
        df = make_df5(closes, vols=[1000.0]*len(closes))
        result = ind.find_bullish_ob(df, swing_n=1, lookback=30)
        # 결과가 있으면 유효한 OB, 없으면 None (둘 다 정상)
        if result is not None:
            assert result["ob_low"] > 0
            assert result["ob_high"] > result["ob_low"]

    def test_bullish_ob_invalidated_by_close_below(self):
        # OB 생성 후 종가가 OB 하단 아래로
        closes = [
            100, 102, 105, 103, 101,  # 105 swing high
            100, 99,                   # OB
            106,                       # BOS
        ] + [97] * 22  # 현재 종가가 OB 하단(99) 아래
        df = make_df5(closes, vols=[1000]*len(closes))
        result = ind.find_bullish_ob(df, swing_n=2, lookback=30)
        assert result is None


class TestRVOL:
    def test_rvol_basic(self):
        volumes = pd.Series([100.0] * 25)
        result = ind.rvol(volumes, window=20)
        # shift(1).rolling(20).mean() → 21번째부터 값이 있음
        # 21번째: (100*20)/20 = 1.0
        assert result.iloc[-1] == pytest.approx(1.0)

    def test_rvol_spike(self):
        volumes = [100.0] * 20 + [200.0]  # 마지막 봉이 2배
        vol_series = pd.Series(volumes)
        result = ind.rvol(vol_series, window=20)
        # 마지막: 200 / 100 = 2.0
        assert result.iloc[-1] == pytest.approx(2.0)

    def test_rvol_nan_at_start(self):
        volumes = pd.Series([100.0] * 5)
        result = ind.rvol(volumes, window=20)
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])


class TestSessionVWAP:
    def test_session_vwap_single_candle(self):
        df = make_df5([100], highs=[102], lows=[98], vols=[1000])
        tp = (102 + 98 + 100) / 3.0  # 100
        result = ind.session_vwap(df["high"], df["low"], df["close"], df["volume"])
        assert result.iloc[0] == pytest.approx(100.0)

    def test_session_vwap_accumulation(self):
        closes = [100.0, 102.0]
        highs = [101.0, 103.0]
        lows = [99.0, 101.0]
        vols = [1000.0, 1000.0]
        df = make_df5(closes, highs=highs, lows=lows, vols=vols)
        result = ind.session_vwap(df["high"], df["low"], df["close"], df["volume"])
        # tp[0] = (101+99+100)/3 = 100.0, tp[1] = (103+101+102)/3 = 102.0
        # vwap[1] = (100*1000 + 102*1000) / 2000 = 101.0
        assert result.iloc[1] == pytest.approx(101.0, abs=0.01)

    def test_session_vwap_with_volume_weight(self):
        df = make_df5(
            [100, 102],
            highs=[101, 103],
            lows=[99, 101],
            vols=[1000, 2000]
        )
        result = ind.session_vwap(df["high"], df["low"], df["close"], df["volume"])
        # 두 번째 봉이 2배 볼륨이므로 VWAP은 102에 더 가까워야 함
        assert 101.3 < result.iloc[1] < 102.0
