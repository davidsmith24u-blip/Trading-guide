"""Rule-based, transparent multi-timeframe strategy.

Design (kept deliberately simple and auditable):

HIGHER timeframe (trend filter), e.g. 4H:
  - Trend is UP   if EMA(fast) > EMA(slow) AND ADX >= threshold
  - Trend is DOWN if EMA(fast) < EMA(slow) AND ADX >= threshold
  - Otherwise FLAT (no trading)

LOWER timeframe (entry), e.g. 15m:
  - LONG setup  : higher trend UP
                  AND close > EMA(entry)   (price above entry EMA)
                  AND RSI >= rsi_long_min
                  AND a bullish price-action trigger (engulfing or pin bar)
  - SHORT setup : higher trend DOWN
                  AND close < EMA(entry)
                  AND RSI <= rsi_short_max
                  AND a bearish price-action trigger
  - Otherwise HOLD/FLAT

No machine learning. Every rule is a plain boolean you can read and change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .indicators import pip_size


@dataclass
class Signal:
    """A single trading decision emitted by the strategy."""
    timestamp: pd.Timestamp
    pair: str
    side: int            # +1 long, -1 short, 0 flat
    entry: float
    stop_loss: float
    take_profit: float
    reason: str


def _bullish_trigger(df: pd.DataFrame, i: int) -> bool:
    """Bullish engulfing OR bullish pin bar (hammer) at bar i."""
    o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
    po, pc = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    body = abs(c - o)
    rng = h - l
    # bullish engulfing
    engulf = (pc < po) and (c > o) and (c >= po) and (o <= pc)
    # hammer: small body near top, long lower wick
    hammer = rng > 0 and body <= 0.35 * rng and (min(o, c) - l) >= 0.6 * rng
    return bool(engulf or hammer)


def _bearish_trigger(df: pd.DataFrame, i: int) -> bool:
    """Bearish engulfing OR bearish pin bar (shooting star)."""
    o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
    po, pc = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    body = abs(c - o)
    rng = h - l
    engulf = (pc > po) and (c < o) and (c <= po) and (o >= pc)
    star = rng > 0 and body <= 0.35 * rng and (h - max(o, c)) >= 0.6 * rng
    return bool(engulf or star)


def higher_trend(trend_df: pd.DataFrame, cfg: StrategyConfig) -> pd.Series:
    """Return a Series of +1/-1/0 trend state indexed like trend_df."""
    up = (trend_df["ema_fast"] > trend_df["ema_slow"]) & (trend_df["adx"] >= cfg.adx_threshold)
    down = (trend_df["ema_fast"] < trend_df["ema_slow"]) & (trend_df["adx"] >= cfg.adx_threshold)
    out = pd.Series(0, index=trend_df.index, dtype=int)
    out[up] = 1
    out[down] = -1
    return out


def generate_signals(
    pair: str,
    trend_df: pd.DataFrame,
    entry_df: pd.DataFrame,
    cfg: StrategyConfig,
) -> list[Signal]:
    """Generate list of Signal objects from aligned trend/entry frames.

    trend_df and entry_df must already contain indicators (via add_indicators).
    trend_df is resampled/forward-filled onto entry_df's index by the caller
    OR this function aligns by nearest prior trend bar.
    """
    if trend_df.empty or entry_df.empty:
        return []

    # Align higher-TF trend onto entry index: use last completed trend bar.
    t_trend = higher_trend(trend_df, cfg)
    aligned = t_trend.reindex(entry_df.index, method="ffill")
    aligned = aligned.shift(1).fillna(0).astype(int)

    # Regime filter series (additional, transparent): clear trend + expanding ATR
    atr_ma = trend_df["atr"].rolling(cfg.regime_atr_lookback).mean()
    regime_ok_series = (
        (trend_df["adx"] >= cfg.regime_adx_threshold)
        & (trend_df["atr"] >= atr_ma * cfg.regime_atr_expansion)
    ).fillna(False)
    regime_aligned = regime_ok_series.reindex(entry_df.index, method="ffill").shift(1).fillna(False).astype(bool)

    signals: list[Signal] = []
    ps = pip_size(pair)
    for i in range(1, len(entry_df)):
        row = entry_df.iloc[i]
        atr_val = row.get("atr", np.nan)
        if not np.isfinite(atr_val) or atr_val <= 0:
            continue
        trend = int(aligned.iloc[i])
        if not bool(regime_aligned.iloc[i]):
            continue  # no-trade zone (choppy / non-expanding)
        close = float(row["close"])
        rsi_val = float(row["rsi"])
        ema_entry = float(row["ema_entry"])

        side = 0
        reason = ""
        if trend == 1 and close > ema_entry and rsi_val >= cfg.rsi_long_min:
            if _bullish_trigger(entry_df, i):
                side = 1
                reason = "HTF uptrend + regime ok + pullback reclaim + bullish PA trigger"
        elif trend == -1 and close < ema_entry and rsi_val <= cfg.rsi_short_max:
            if _bearish_trigger(entry_df, i):
                side = -1
                reason = "HTF downtrend + regime ok + pullback rejection + bearish PA trigger"

        if side == 0:
            continue

        stop_distance = cfg.stop_atr_mult * float(atr_val)
        if side == 1:
            sl = close - stop_distance
            tp = close + cfg.takeprofit_rr * stop_distance
        else:
            sl = close + stop_distance
            tp = close - cfg.takeprofit_rr * stop_distance

        signals.append(
            Signal(
                timestamp=entry_df.index[i],
                pair=pair,
                side=side,
                entry=close,
                stop_loss=sl,
                take_profit=tp,
                reason=reason,
            )
        )
    return signals


def trend_state(trend_df: pd.DataFrame, cfg: StrategyConfig) -> int:
    """Convenience: latest trend state (+1/-1/0) from a trend frame."""
    if trend_df.empty:
        return 0
    t = higher_trend(trend_df, cfg)
    return int(t.iloc[-1])


def regime_filter_reason(trend_df: pd.DataFrame, cfg: StrategyConfig) -> tuple[bool, str]:
    """Transparent regime check: returns (ok, reason)."""
    if trend_df.empty:
        return False, "regime: no trend data"
    last = trend_df.iloc[-1]
    adx_val = float(last.get("adx", 0.0))
    atr_val = float(last.get("atr", 0.0))
    atr_ma = float(trend_df["atr"].tail(cfg.regime_atr_lookback).mean())
    if adx_val < cfg.regime_adx_threshold:
        return False, f"regime rejected: ADX {adx_val:.1f} < {cfg.regime_adx_threshold}"
    if atr_ma <= 0 or atr_val < atr_ma * cfg.regime_atr_expansion:
        return False, (
            f"regime rejected: ATR {atr_val:.5f} < {atr_ma * cfg.regime_atr_expansion:.5f} "
            f"(not expanding)"
        )
    return True, "regime ok"