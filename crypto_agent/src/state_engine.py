"""Deterministic state snapshot (<400 tokens). Causal timestamps only."""

from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass
class StateSnapshot:
    ts: int
    mid: float
    spread_bps: float
    imbalance: float
    rv_1m: float
    rv_5m: float
    inventory: float
    drawdown_pct: float
    regime_hint: str
    funding: float
    oi_delta_1h: float


def _realized_vol(prices: List[float]) -> float:
    if len(prices) < 2:
        return 0.0
    rets = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
    return statistics.pstdev(rets)


def build_snapshot(orderbook, trades, position, equity_peak, equity_now, funding, oi) -> StateSnapshot:
    bids = orderbook["bids"]
    asks = orderbook["asks"]
    mid = (bids[0][0] + asks[0][0]) / 2
    spread_bps = (asks[0][0] - bids[0][0]) / mid * 10000
    bid_vol = sum(b[1] for b in bids[:10])
    ask_vol = sum(a[1] for a in asks[:10])
    imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-9)
    prices = [t["price"] for t in trades[-60:]]
    rv_1m = _realized_vol(prices[-12:]) if len(prices) >= 12 else 0.0
    rv_5m = _realized_vol(prices) if len(prices) >= 2 else 0.0
    dd = (equity_now / equity_peak - 1) * 100 if equity_peak > 0 else 0.0
    regime_hint = "high_vol" if rv_5m > 0.02 else ("crisis" if spread_bps > 20 else "trending")
    return StateSnapshot(
        ts=int(time.time() * 1000),
        mid=round(mid, 6),
        spread_bps=round(spread_bps, 2),
        imbalance=round(imbalance, 4),
        rv_1m=round(rv_1m, 6),
        rv_5m=round(rv_5m, 6),
        inventory=round(position, 6),
        drawdown_pct=round(dd, 2),
        regime_hint=regime_hint,
        funding=round(funding, 6),
        oi_delta_1h=round(oi, 4),
    )


def to_prompt(s: StateSnapshot) -> str:
    d = asdict(s)
    return "STATE " + " ".join(f"{k}={v}" for k, v in d.items())