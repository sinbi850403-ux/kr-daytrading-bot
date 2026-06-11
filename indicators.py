"""5분봉 기술 지표 — 순수 함수 (부작용 없음).

swing_highs / swing_lows: N봉 좌우 비교로 스윙 포인트 식별
find_bullish_ob          : Bullish OB (마지막 음봉 before BOS) 반환
rvol                     : 상대 거래량 (현재봉/rolling mean)
session_vwap             : 당일 누적 VWAP
"""
import math
from typing import Optional
import pandas as pd


def swing_highs(high: pd.Series, n: int = 3) -> pd.Series:
    """좌우 n봉보다 고가가 높은 봉 = Swing High."""
    result = pd.Series(False, index=high.index)
    for i in range(n, len(high) - n):
        window = high.iloc[i-n:i+n+1]
        if high.iloc[i] == window.max() and list(window).count(high.iloc[i]) == 1:
            result.iloc[i] = True
    return result


def swing_lows(low: pd.Series, n: int = 3) -> pd.Series:
    """좌우 n봉보다 저가가 낮은 봉 = Swing Low."""
    result = pd.Series(False, index=low.index)
    for i in range(n, len(low) - n):
        window = low.iloc[i-n:i+n+1]
        if low.iloc[i] == window.min() and list(window).count(low.iloc[i]) == 1:
            result.iloc[i] = True
    return result


def find_bullish_ob(df: pd.DataFrame, swing_n: int = 3,
                    lookback: int = 30) -> Optional[dict]:
    """
    최근 lookback봉 내 가장 최근 유효 Bullish OB 반환.

    Bullish OB = Swing Low 이후 BOS(직전 Swing High 상향 돌파) 직전
                 마지막 음봉. 현재까지 OB 하단이 지켜진 것만 유효.

    반환: {'ob_low': float, 'ob_high': float} 또는 None
    """
    n_need = lookback + swing_n * 2 + 1
    sub = df.iloc[-min(len(df), n_need):].reset_index(drop=True)
    if len(sub) < swing_n * 2 + 2:
        return None

    sh_mask = swing_highs(sub["high"], swing_n)
    sl_mask = swing_lows(sub["low"],  swing_n)

    last_ob = None
    last_sh_price: Optional[float] = None
    last_sh_idx: int = -1

    for i in range(len(sub)):
        if sh_mask.iloc[i]:
            last_sh_price = float(sub["high"].iloc[i])
            last_sh_idx   = i

        # BOS: 종가가 직전 swing high 돌파
        if (last_sh_price is not None and i > last_sh_idx
                and float(sub["close"].iloc[i]) > last_sh_price):
            # BOS 구간(last_sh_idx ~ i)에서 마지막 음봉 = OB
            for k in range(i - 1, last_sh_idx, -1):
                if float(sub["close"].iloc[k]) < float(sub["open"].iloc[k]):
                    last_ob = {
                        "ob_low":  float(sub["low"].iloc[k]),
                        "ob_high": float(sub["high"].iloc[k]),
                    }
                    break
            # 이 BOS의 swing high 리셋 (같은 BOS를 중복 처리 방지)
            last_sh_price = None
            last_sh_idx   = -1

    if last_ob is None:
        return None

    # OB 무효화: 현재 종가가 OB 하단 아래
    current_close = float(sub["close"].iloc[-1])
    if current_close < last_ob["ob_low"]:
        return None

    return last_ob


def rvol(volume: pd.Series, window: int = 20) -> pd.Series:
    """상대 거래량 = 현재봉 / 이전 window봉 평균."""
    avg = volume.shift(1).rolling(window).mean()
    return volume / avg.replace(0, float("nan"))


def session_vwap(high: pd.Series, low: pd.Series,
                 close: pd.Series, volume: pd.Series) -> pd.Series:
    """당일 누적 VWAP (세션 시작부터 현재까지)."""
    tp  = (high + low + close) / 3.0
    cum_tpv = (tp * volume).cumsum()
    cum_vol = volume.cumsum()
    return cum_tpv / cum_vol.replace(0, float("nan"))
