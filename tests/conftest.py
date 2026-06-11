"""5분봉 합성 데이터 생성 헬퍼."""
import pandas as pd


def make_df5(closes, opens=None, highs=None, lows=None, vols=None):
    """5분봉 DataFrame 생성 헬퍼."""
    n = len(closes)
    closes = [float(x) for x in closes]

    if opens is None:
        opens = [closes[max(i-1, 0)] for i in range(n)]
    else:
        opens = [float(x) for x in opens]
        if len(opens) != n:
            opens = opens + [closes[-1]] * (n - len(opens))

    if highs is None:
        highs = [max(o, c) * 1.003 for o, c in zip(opens, closes)]
    else:
        highs = [float(x) for x in highs]
        if len(highs) != n:
            highs = highs + [max(opens[-1], closes[-1]) * 1.003] * (n - len(highs))

    if lows is None:
        lows = [min(o, c) * 0.997 for o, c in zip(opens, closes)]
    else:
        lows = [float(x) for x in lows]
        if len(lows) != n:
            lows = lows + [min(opens[-1], closes[-1]) * 0.997] * (n - len(lows))

    if vols is None:
        vols = [1000.0] * n
    else:
        vols = [float(x) for x in vols]
        if len(vols) != n:
            vols = vols + [1000.0] * (n - len(vols))

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": vols
    })
