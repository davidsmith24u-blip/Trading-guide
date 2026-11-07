"""Execution: paper (default) and live (ccxt)."""

from __future__ import annotations

from typing import Any, Dict

from .schemas import Direction, JevDecision


class PaperBroker:
    def __init__(self):
        self.positions = {}

    def place_order(self, symbol, d: JevDecision, size: float) -> Dict[str, Any]:
        side = "buy" if d.direction == Direction.long else "sell"
        print(f"[PAPER] {side.upper()} {size} {symbol} @ market (conf={d.direction_confidence})")
        self.positions[symbol] = {"side": side, "size": size}
        return {"id": "paper-1", "status": "filled", "side": side, "size": size}

    def get_positions(self):
        return self.positions


class LiveBroker:
    def __init__(self, exchange_id, api_key, api_secret):
        try:
            import ccxt

            self.ex = getattr(ccxt, exchange_id)({"apiKey": api_key, "secret": api_secret, "enableRateLimit": True})
        except Exception as e:
            raise RuntimeError(f"ccxt unavailable: {e}")

    def place_order(self, symbol, d: JevDecision, size: float) -> Dict[str, Any]:
        side = "buy" if d.direction == Direction.long else "sell"
        try:
            return self.ex.create_order(symbol, "market", side, size)
        except Exception as e:
            print(f"[LIVE] order failed: {e}")
            return {}