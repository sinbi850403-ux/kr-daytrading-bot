"""ICT 단타 신호 생성 (순수)."""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

import indicators as ind
from config import Config


@dataclass
class DaySignal:
    symbol:       str
    ob_low:       float
    ob_high:      float
    entry_price:  float
    sl_price:     float      # 손절 = OB 하단
    tp1_price:    float      # 익절1 = entry + R
    tp2_price:    float      # 익절2 = entry + 2R
    rvol:         float
    vwap:         float
    timestamp:    str = ""


def generate_signal(symbol: str, df5: pd.DataFrame,
                    cfg: Config,
                    timestamp: str = "") -> Optional[DaySignal]:
    """
    5분봉 df5로 ICT Bullish OB 신호 생성.

    조건 (모두 AND):
      ① Bullish OB 존재 (find_bullish_ob)
      ② 현재 종가가 OB 구간 내 (ob_low <= close <= ob_high)
      ③ 양봉 (close >= open)
      ④ RVOL >= cfg.rvol_threshold
      ⑤ 현재 종가 > VWAP
      ⑥ R >= entry의 min_r_pct% (손절폭 최소값 — 노이즈 방지)
    """
    if df5 is None or len(df5) < cfg.swing_n * 2 + 3:
        return None

    ob = ind.find_bullish_ob(df5, cfg.swing_n, cfg.ob_lookback)
    if ob is None:
        return None

    c, o = float(df5["close"].iloc[-1]), float(df5["open"].iloc[-1])
    rv   = float(ind.rvol(df5["volume"], cfg.rvol_window).iloc[-1])
    vw   = float(ind.session_vwap(
        df5["high"], df5["low"], df5["close"], df5["volume"]).iloc[-1])

    # 5개 조건
    in_ob       = ob["ob_low"] <= c <= ob["ob_high"]
    is_bull     = c >= o
    rvol_ok     = (not _nan(rv)) and rv >= cfg.rvol_threshold
    above_vwap  = (not _nan(vw)) and c > vw

    if not (in_ob and is_bull and rvol_ok and above_vwap):
        return None

    # R 계산 및 최소폭 체크
    sl = ob["ob_low"]
    r = c - sl
    r_pct = (r / c) * 100

    if r_pct < cfg.min_r_pct:
        return None

    # 손절/익절 가격 계산
    tp1 = c + r
    tp2 = c + 2 * r

    return DaySignal(
        symbol=symbol, ob_low=ob["ob_low"], ob_high=ob["ob_high"],
        entry_price=c, sl_price=sl, tp1_price=round(tp1, 0), tp2_price=round(tp2, 0),
        rvol=round(rv, 2), vwap=round(vw, 2),
        timestamp=timestamp)


def _nan(v: float) -> bool:
    import math
    try:
        return math.isnan(v)
    except (TypeError, ValueError):
        return True
