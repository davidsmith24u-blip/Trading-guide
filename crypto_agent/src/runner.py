"""Live loop: state -> Dev -> gate -> risk -> execute -> journal."""

from __future__ import annotations

import time
from typing import Any, Dict

from .execution import PaperBroker
from .jev_client import ask_dev
from .journal import init_db, log_trade
from .policy import gate, size
from .risk import RiskManager, RiskLimits
from .schemas import JevDecision
from .state_engine import build_snapshot, to_prompt


def run_loop(cfg: dict, symbol: str = "BTC/USDT", paper: bool = True):
    init_db()
    risk = RiskManager(RiskLimits(), cfg.get("equity_start", 10000.0))
    broker = PaperBroker() if paper else None
    position = 0.0
    equity_peak = cfg.get("equity_start", 10000.0)
    equity = equity_peak

    while True:
        try:
            # placeholder data fetchers (replace with real exchange)
            orderbook = {"bids": [[100.0, 1.0]], "asks": [[100.01, 1.0]]}
            trades = [{"price": 100.0}]
            snap = build_snapshot(orderbook, trades, position, equity_peak, equity, 0.0, 0.0)
            dev = ask_dev(to_prompt(snap))
            proposed = size(dev, equity)
            risk_ok, reason = risk.check(proposed, position * 100.0)
            if gate(dev, risk_ok):
                res = broker.place_order(symbol, dev, proposed)
                log_trade(snap.ts, dev.model_dump(), "live", proposed)
                position += proposed if dev.direction.value == "long" else -proposed
            else:
                log_trade(snap.ts, dev.model_dump(), "skipped", 0.0, notes=reason)
            # escalation check
            if dev.direction_confidence < 0.60 or dev.regime.value == "crisis":
                print("ESCALATE to Opus 5.5 for deep re-read")
        except Exception as e:
            print(f"loop error: {e}")
        time.sleep(cfg.get("interval_sec", 60))