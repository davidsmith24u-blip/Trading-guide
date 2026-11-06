"""Backtest endpoint."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

# ensure project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, HTTPException

from backend.config_store import apply_overrides, load
from backend.schemas import BacktestRequest, BacktestResponse, EquityPoint, TradeOut
from src.backtest.engine import run_backtest
from src.data.provider import from_yfinance_range, make_multi_tf_pair

router = APIRouter()

PAPER_WARNING = (
    "PAPER TRADING ONLY. Backtests are historical simulations and do not "
    "guarantee future results. Spreads, slippage and overfitting may reduce "
    "live performance. Not financial advice."
)


def _map_tf(tf: str) -> str:
    t = tf.lower()
    if t == "4h":
        return "1h"  # yfinance has no 4h; 1h is closest
    return t


def _fetch_frames(pair, cfg, req):
    if req.start and req.end:
        try:
            trend = from_yfinance_range(pair, req.start, req.end, _map_tf(cfg.trend_tf))
            entry = from_yfinance_range(pair, req.start, req.end, _map_tf(cfg.entry_tf))
            if not trend.empty and not entry.empty:
                return trend, entry
        except Exception:
            pass
    n = req.n_bars or 4000
    frames = make_multi_tf_pair(n_entry=n, seed=abs(hash(pair)) % 1000)
    return frames["trend"], frames["entry"]


@router.post("/backtest", response_model=BacktestResponse)
def run_backtest_endpoint(req: BacktestRequest):
    try:
        cfg = load()
        if req.config_overrides:
            cfg = apply_overrides(cfg, req.config_overrides)

        pairs = req.pairs or cfg.pairs
        data: Dict[str, Dict[str, Any]] = {}
        for pair in pairs:
            trend, entry = _fetch_frames(pair, cfg, req)
            data[pair] = {"trend": trend, "entry": entry}

        result = run_backtest(data, cfg)
        m = result["metrics"]
        eq = result["equity_curve"]
        equity_points = [
            EquityPoint(timestamp=str(ts), equity=float(val)) for ts, val in eq.items()
        ]
        trades = []
        for t in result["trades"]:
            trades.append(
                TradeOut(
                    pair=t.pair,
                    side=t.side,
                    entry=t.entry,
                    exit_price=t.exit_price,
                    stop_loss=t.stop_loss,
                    take_profit=t.take_profit,
                    units=t.units,
                    pnl=t.pnl,
                    r_multiple=t.r_multiple,
                    opened_at=str(t.opened_at),
                    closed_at=str(t.closed_at),
                    reason=t.reason,
                )
            )
        return BacktestResponse(
            metrics=m, equity_curve=equity_points, trades=trades, warning=PAPER_WARNING
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))