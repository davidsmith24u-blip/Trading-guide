"""Pure-pandas technical indicators.

All functions accept a DataFrame with columns: open, high, low, close (and
optionally volume) and return a Series or DataFrame aligned to the input index.
Keeping them dependency-light makes the rules auditable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder smoothing)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder smoothing = EMA with alpha = 1/period
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index (trend strength, 0-100)."""
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    tr = atr(df, 1)  # raw true range
    # Wilder smoothing of TR and DM
    atr_s = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr_s)
    minus_di = 100 * (minus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr_s)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return adx_val.fillna(0.0)


def pip_size(pair: str) -> float:
    """Pip size for a pair (XAUUSD uses 0.01, JPY pairs 0.01, others 0.0001)."""
    p = pair.upper()
    if "XAU" in p or "JPY" in p:
        return 0.01
    return 0.0001


def add_indicators(df: pd.DataFrame, cfg_strategy) -> pd.DataFrame:
    """Attach all indicators needed by the strategy to a copy of df."""
    out = df.copy()
    out["ema_fast"] = ema(out["close"], cfg_strategy.trend_ema_fast)
    out["ema_slow"] = ema(out["close"], cfg_strategy.trend_ema_slow)
    out["ema_entry"] = ema(out["close"], cfg_strategy.entry_ema)
    out["rsi"] = rsi(out["close"], cfg_strategy.rsi_period)
    out["atr"] = atr(out, cfg_strategy.atr_period)
    out["adx"] = adx(out, cfg_strategy.adx_period)
    return out