"""Pure pandas/numpy implementations of common technical indicators.

Drop-in replacement for the `ta` library — no additional dependencies required.
All functions accept pandas Series/DataFrames and return the same types as `ta`.
"""

import numpy as np
import pandas as pd


def _last(series: pd.Series):
    """Return the last value as a Python float, or None for NaN."""
    try:
        v = float(series.iloc[-1])
        return None if (v != v) else round(v, 4)
    except Exception:
        return None


# ── Moving averages ───────────────────────────────────────────────────────────

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


# ── Momentum ──────────────────────────────────────────────────────────────────

def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def macd_line(series: pd.Series) -> pd.Series:
    return ema(series, 12) - ema(series, 26)


def macd_signal_line(series: pd.Series) -> pd.Series:
    return ema(macd_line(series), 9)


def macd_diff(series: pd.Series) -> pd.Series:
    return macd_line(series) - macd_signal_line(series)


def stoch(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    low_min = low.rolling(window).min()
    high_max = high.rolling(window).max()
    denom = (high_max - low_min).replace(0, float("nan"))
    return (close - low_min) / denom * 100


def stoch_signal(high: pd.Series, low: pd.Series, close: pd.Series,
                 window: int = 14, smooth: int = 3) -> pd.Series:
    return stoch(high, low, close, window).rolling(smooth).mean()


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    high_max = high.rolling(window).max()
    low_min = low.rolling(window).min()
    denom = (high_max - low_min).replace(0, float("nan"))
    return (high_max - close) / denom * -100


def roc(series: pd.Series, window: int = 10) -> pd.Series:
    return (series / series.shift(window) - 1) * 100


# ── Volatility ────────────────────────────────────────────────────────────────

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    return pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    return true_range(high, low, close).rolling(window).mean()


def bollinger_upper(series: pd.Series, window: int = 20, num_std: float = 2) -> pd.Series:
    return series.rolling(window).mean() + num_std * series.rolling(window).std()


def bollinger_middle(series: pd.Series, window: int = 20) -> pd.Series:
    return series.rolling(window).mean()


def bollinger_lower(series: pd.Series, window: int = 20, num_std: float = 2) -> pd.Series:
    return series.rolling(window).mean() - num_std * series.rolling(window).std()


def keltner_middle(close: pd.Series, window: int = 20) -> pd.Series:
    return ema(close, window)


def keltner_upper(high: pd.Series, low: pd.Series, close: pd.Series,
                  window: int = 20, atr_window: int = 10, mult: float = 2) -> pd.Series:
    return keltner_middle(close, window) + mult * atr(high, low, close, atr_window)


def keltner_lower(high: pd.Series, low: pd.Series, close: pd.Series,
                  window: int = 20, atr_window: int = 10, mult: float = 2) -> pd.Series:
    return keltner_middle(close, window) - mult * atr(high, low, close, atr_window)


# ── Trend ─────────────────────────────────────────────────────────────────────

def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    atr_series = tr.rolling(window).mean()
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    dm_plus = (high - prev_high).clip(lower=0)
    dm_minus = (prev_low - low).clip(lower=0)
    # Zero out when the other DM is larger
    dm_plus = dm_plus.where(dm_plus >= dm_minus, 0)
    dm_minus = dm_minus.where(dm_minus > dm_plus, 0)
    di_plus = 100 * dm_plus.rolling(window).mean() / atr_series.replace(0, float("nan"))
    di_minus = 100 * dm_minus.rolling(window).mean() / atr_series.replace(0, float("nan"))
    denom = (di_plus + di_minus).replace(0, float("nan"))
    dx = 100 * (di_plus - di_minus).abs() / denom
    return dx.rolling(window).mean()


def cci(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 20) -> pd.Series:
    typical = (high + low + close) / 3
    sma_tp = typical.rolling(window).mean()
    mad = typical.rolling(window).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    return (typical - sma_tp) / (0.015 * mad.replace(0, float("nan")))


def aroon_up(high: pd.Series, window: int = 14) -> pd.Series:
    return high.rolling(window + 1).apply(
        lambda x: (np.argmax(x) / window) * 100, raw=True
    )


def aroon_down(low: pd.Series, window: int = 14) -> pd.Series:
    return low.rolling(window + 1).apply(
        lambda x: (np.argmin(x) / window) * 100, raw=True
    )


def psar_approx(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Simplified PSAR approximation: trailing stop based on recent swing low/high."""
    return low.rolling(5).min().where(close > close.shift(1), high.rolling(5).max())


def ichimoku_a(high: pd.Series, low: pd.Series,
               tenkan: int = 9, kijun: int = 26) -> pd.Series:
    """Senkou Span A = (Tenkan-sen + Kijun-sen) / 2."""
    t = (high.rolling(tenkan).max() + low.rolling(tenkan).min()) / 2
    k = (high.rolling(kijun).max() + low.rolling(kijun).min()) / 2
    return (t + k) / 2


def ichimoku_b(high: pd.Series, low: pd.Series, window: int = 52) -> pd.Series:
    """Senkou Span B = (52-period high + 52-period low) / 2."""
    return (high.rolling(window).max() + low.rolling(window).min()) / 2


# ── Volume ────────────────────────────────────────────────────────────────────

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * volume).cumsum()


def acc_dist_index(high: pd.Series, low: pd.Series,
                   close: pd.Series, volume: pd.Series) -> pd.Series:
    denom = (high - low).replace(0, float("nan"))
    clv = ((close - low) - (high - close)) / denom
    return (clv * volume).cumsum()


def money_flow_index(high: pd.Series, low: pd.Series,
                     close: pd.Series, volume: pd.Series, window: int = 14) -> pd.Series:
    typical = (high + low + close) / 3
    flow = typical * volume
    pos = flow.where(typical > typical.shift(1), 0).rolling(window).sum()
    neg = flow.where(typical < typical.shift(1), 0).rolling(window).sum()
    ratio = pos / neg.replace(0, float("nan"))
    return 100 - (100 / (1 + ratio))


def volume_price_trend(close: pd.Series, volume: pd.Series) -> pd.Series:
    return (volume * close.pct_change()).cumsum()


def chaikin_money_flow(high: pd.Series, low: pd.Series,
                       close: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
    denom = (high - low).replace(0, float("nan"))
    clv = ((close - low) - (high - close)) / denom
    return (clv * volume).rolling(window).sum() / volume.rolling(window).sum().replace(0, float("nan"))
