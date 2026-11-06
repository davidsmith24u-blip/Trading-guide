"""Signals endpoint."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from backend.config_store import from_dict, to_dict
from backend.db import get_user_config, set_user_config
from backend.schemas import SignalOut, SignalsResponse
from src.data.provider import from_yfinance, make_multi_tf_pair
from src.indicators import add_indicators
from src.strategy import generate_signals, trend_state

router = APIRouter()

PAPER_WARNING = "PAPER TRADING ONLY. Signals are rule-based and not financial advice."


def _fetch_latest(pair, cfg):
    trend_tf = cfg.trend_tf
    entry_tf = cfg.entry_tf
    try:
        trend = from_yfinance(pair, period="60d", interval=trend_tf.lower().replace("h", "h"))
        entry = from_yfinance(pair, period="5d", interval=entry_tf.lower())
        if trend.empty or entry.empty:
            raise RuntimeError("empty")
    except Exception:
        frames = make_multi_tf_pair(n_entry=2000, seed=abs(hash(pair)) % 1000)
        trend, entry = frames["trend"], frames["entry"]
    return trend, entry


@router.get("/signals", response_model=SignalsResponse)
def get_signals(pairs: str = "", current_user=Depends(get_current_user)):
    user_cfg = get_user_config(current_user["id"])
    if user_cfg is None:
        from backend.config_store import load as load_global

        user_cfg = to_dict(load_global())
        set_user_config(current_user["id"], user_cfg)
    cfg = from_dict(user_cfg)
    requested = [p.strip().upper() for p in pairs.split(",") if p.strip()] if pairs else cfg.pairs

    out = []
    for pair in requested:
        trend, entry = _fetch_latest(pair, cfg)
        trend_i = add_indicators(trend.copy(), cfg.strategy)
        entry_i = add_indicators(entry.copy(), cfg.strategy)
        sigs = generate_signals(pair, trend_i, entry_i, cfg.strategy)
        ts = trend_state(trend_i, cfg.strategy)

        if sigs:
            last = sigs[-1]
            # only report if on latest bar
            if last.timestamp == entry_i.index[-1]:
                direction = "BUY/LONG" if last.side == 1 else "SELL/SHORT"
                out.append(
                    SignalOut(
                        timestamp=str(last.timestamp),
                        pair=pair,
                        side=last.side,
                        direction=direction,
                        entry=last.entry,
                        stop_loss=last.stop_loss,
                        take_profit=last.take_profit,
                        reason=last.reason,
                        trend=ts,
                    )
                )
                continue
        # HOLD
        last_close = float(entry_i["close"].iloc[-1]) if not entry_i.empty else 0.0
        out.append(
            SignalOut(
                timestamp=str(entry_i.index[-1]) if not entry_i.empty else None,
                pair=pair,
                side=0,
                direction="HOLD/FLAT",
                entry=last_close,
                stop_loss=0.0,
                take_profit=0.0,
                reason=f"No setup (HTF trend={ts})",
                trend=ts,
            )
        )
    return SignalsResponse(signals=out, warning=PAPER_WARNING)