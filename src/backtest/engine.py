"""Event-driven backtester.

Input: a dict {pair: {"trend": DataFrame, "entry": DataFrame}} where each
DataFrame has OHLCV columns and a DatetimeIndex. Indicators are added internally.

The engine processes bars in chronological order across all pairs so that the
global risk manager (daily/weekly drawdown, cooldown) behaves realistically.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..config import AppConfig
from ..execution import PaperBroker
from ..indicators import add_indicators
from ..risk import RiskManager
from ..strategy import generate_signals


def _unrealized(broker, price_map: dict) -> float:
    total = 0.0
    contract = 100000.0
    for pos in broker.positions:
        px = price_map.get(pos.pair, pos.entry)
        diff = (px - pos.entry) if pos.side == 1 else (pos.entry - px)
        total += diff * pos.units * contract
    return total


def run_backtest(data: Dict[str, dict], cfg: AppConfig) -> dict:
    """Run a backtest. Returns dict with trades, equity_curve, metrics."""
    risk = RiskManager(cfg.risk)
    broker = PaperBroker(cfg, risk)

    # Prepare indicators + signals per pair
    pair_entry: dict = {}
    pair_signals: dict = {}  # timestamp -> Signal
    for pair, frames in data.items():
        trend_df = add_indicators(frames["trend"].copy(), cfg.strategy)
        entry_df = add_indicators(frames["entry"].copy(), cfg.strategy)
        pair_entry[pair] = entry_df
        sigs = generate_signals(pair, trend_df, entry_df, cfg.strategy)
        for s in sigs:
            pair_signals.setdefault(s.timestamp, []).append(s)

    # Unified timeline
    all_ts = sorted(set().union(*[set(df.index) for df in pair_entry.values()]))
    equity_points = []
    for ts in all_ts:
        # 1) update open positions with this bar (SL/TP)
        for pair, df in pair_entry.items():
            if ts in df.index:
                bar = df.loc[ts]
                broker.update(pair, bar, pd.Timestamp(ts), cfg.strategy)

        # 2) act on signals at this timestamp
        for sig in pair_signals.get(ts, []):
            # only one open position per pair
            if any(p.pair == sig.pair for p in broker.positions):
                continue
            df = pair_entry[sig.pair]
            atr_val = float(df.loc[ts, "atr"]) if ts in df.index else float("nan")
            broker.open_position(sig, pd.Timestamp(ts), atr_val)

        # 3) equity snapshot
        price_map = {}
        for pair, df in pair_entry.items():
            if ts in df.index:
                price_map[pair] = float(df.loc[ts, "close"])
        eq = risk.state.equity + _unrealized(broker, price_map)
        equity_points.append((ts, eq))

    equity_curve = pd.Series({ts: eq for ts, eq in equity_points}).sort_index()
    trades = broker.closed

    from .metrics import compute_metrics
    metrics = compute_metrics(trades, equity_curve, cfg.risk.balance)

    return {
        "trades": trades,
        "open_positions": broker.positions,
        "equity_curve": equity_curve,
        "metrics": metrics,
    }