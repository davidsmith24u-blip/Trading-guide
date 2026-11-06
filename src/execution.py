"""Execution layer.

PaperBroker: simulated fills with spread/slippage.
MT5Broker lives in src/broker/mt5.py and shares the same interface.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .broker.base import BrokerInterface, Order, OrderResult, Position
from .config import AppConfig
from .indicators import pip_size
from .risk import RiskManager, TradeResult
from .strategy import Signal


# Re-export for backwards compatibility
__all__ = ["PaperBroker", "Position", "TradeResult"]


class PaperBroker(BrokerInterface):
    def __init__(self, cfg: AppConfig, risk: RiskManager, store=None, user_id=None):
        self.cfg = cfg
        self.risk = risk
        self.store = store
        self.user_id = user_id
        self.positions: List[Position] = []
        self.closed: List[TradeResult] = []
        # load persisted open positions (if any)
        if store is not None and user_id is not None:
            try:
                for row in store.load_open_positions(user_id):
                    self.positions.append(
                        Position(
                            pair=row["pair"],
                            side=row["side"],
                            units=row["units"],
                            entry=row["entry"],
                            stop_loss=row["stop_loss"],
                            take_profit=row["take_profit"],
                            orig_stop=row["orig_stop"],
                            opened_at=pd.Timestamp(row["opened_at"]),
                            reason=row.get("reason", ""),
                            atr=row.get("atr", 0.0),
                            risk_pct=row.get("risk_pct", cfg.risk.risk_per_trade_pct),
                            position_id=row.get("id"),
                        )
                    )
                    self.risk.register_open_position(row.get("risk_pct", cfg.risk.risk_per_trade_pct))
            except Exception:
                pass

    # ---- BrokerInterface ----
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def get_account_info(self) -> Dict[str, Any]:
        return {"balance": self.risk.state.equity, "equity": self.risk.state.equity, "currency": self.cfg.risk.currency}

    def get_positions(self) -> List[Position]:
        return list(self.positions)

    def get_open_orders(self) -> List[Order]:
        return []

    def place_order(self, signal: Signal, size: float) -> OrderResult:
        pos = self.open_position(signal, pd.Timestamp.utcnow(), 0.0)
        if pos is None:
            return OrderResult(success=False, message="blocked by risk/heat")
        return OrderResult(success=True, ticket=pos.position_id, price=pos.entry)

    def modify_position(self, ticket: Any, sl: float, tp: float) -> bool:
        for p in self.positions:
            if p.position_id == ticket:
                p.stop_loss = sl
                p.take_profit = tp
                return True
        return False

    def close_position(self, ticket: Any, volume: Optional[float] = None) -> bool:
        # paper close is handled by update(); this is a manual override
        for p in list(self.positions):
            if p.position_id == ticket:
                self.positions.remove(p)
                self.risk.close_position_risk(p.risk_pct)
                return True
        return False

    def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        return pd.DataFrame()

    def is_trading_allowed(self) -> Tuple[bool, str]:
        return self.risk.trading_allowed()

    # ---- paper simulation helpers (existing) ----
    def _fill_price(self, pair: str, price: float, side: int, is_entry: bool) -> float:
        pip = pip_size(pair)
        spread = self.cfg.spreads.get(pair, 1.0) * pip
        slip = self.cfg.slippage_pips * pip
        if side == 1:
            fill = price + spread / 2 + (slip if is_entry else 0)
        else:
            fill = price - spread / 2 - (slip if is_entry else 0)
        return fill

    def open_position(self, sig: Signal, now: pd.Timestamp, atr: float) -> Optional[Position]:
        allowed, _ = self.risk.trading_allowed(
            now.to_pydatetime() if hasattr(now, "to_pydatetime") else now
        )
        if not allowed:
            return None

        risk_pct = self.cfg.risk.risk_per_trade_pct
        heat_ok, heat_reason = self.risk.can_open_trade(risk_pct)
        if not heat_ok:
            import logging

            logging.getLogger("trading_guardian").warning("trade blocked for %s: %s", sig.pair, heat_reason)
            return None

        fill = self._fill_price(sig.pair, sig.entry, sig.side, True)
        units = self.risk.position_size(sig.pair, fill, sig.stop_loss)
        if units <= 0:
            return None

        pos = Position(
            pair=sig.pair,
            side=sig.side,
            units=units,
            entry=fill,
            stop_loss=sig.stop_loss,
            take_profit=sig.take_profit,
            orig_stop=sig.stop_loss,
            opened_at=now,
            reason=sig.reason,
            atr=atr,
            risk_pct=risk_pct,
        )
        self.positions.append(pos)
        self.risk.register_open_position(risk_pct)
        if self.store is not None and self.user_id is not None:
            try:
                pid = self.store.save_open_position(self.user_id, pos)
                pos.position_id = pid
            except Exception:
                pass
        return pos

    def update(self, pair: str, bar: pd.Series, now: pd.Timestamp, strategy_cfg=None) -> List[TradeResult]:
        closed_now: List[TradeResult] = []
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        still_open: List[Position] = []

        for pos in self.positions:
            if pos.pair != pair:
                still_open.append(pos)
                continue

            risk_price = abs(pos.entry - pos.orig_stop)
            if risk_price > 0:
                if pos.side == 1:
                    if close - pos.entry >= 1.0 * risk_price:
                        pos.stop_loss = max(pos.stop_loss, pos.entry)
                    if strategy_cfg is not None and getattr(strategy_cfg, "trailing_stop", True):
                        trail = close - getattr(strategy_cfg, "stop_atr_mult", 1.5) * pos.atr
                        pos.stop_loss = max(pos.stop_loss, trail)
                else:
                    if pos.entry - close >= 1.0 * risk_price:
                        pos.stop_loss = min(pos.stop_loss, pos.entry)
                    if strategy_cfg is not None and getattr(strategy_cfg, "trailing_stop", True):
                        trail = close + getattr(strategy_cfg, "stop_atr_mult", 1.5) * pos.atr
                        pos.stop_loss = min(pos.stop_loss, trail)

            hit_sl = hit_tp = False
            if pos.side == 1:
                if low <= pos.stop_loss:
                    hit_sl = True
                if high >= pos.take_profit:
                    hit_tp = True
            else:
                if high >= pos.stop_loss:
                    hit_sl = True
                if low <= pos.take_profit:
                    hit_tp = True

            if hit_sl or hit_tp:
                if hit_sl:
                    exit_px = self._fill_price(pos.pair, pos.stop_loss, pos.side, False)
                    outcome = "stop_loss"
                else:
                    exit_px = self._fill_price(pos.pair, pos.take_profit, pos.side, False)
                    outcome = "take_profit"

                pnl_price = (exit_px - pos.entry) if pos.side == 1 else (pos.entry - exit_px)
                contract = 100000.0
                pnl = pnl_price * pos.units * contract
                # commission (per lot, round trip)
                commission = self.cfg.commission_per_lot * pos.units
                pnl -= commission
                risk_price = abs(pos.entry - pos.orig_stop)
                r_mult = (pnl_price / risk_price) if risk_price > 0 else 0.0

                tr = TradeResult(
                    pair=pos.pair,
                    side=pos.side,
                    entry=pos.entry,
                    exit_price=exit_px,
                    stop_loss=pos.orig_stop,
                    take_profit=pos.take_profit,
                    units=pos.units,
                    pnl=pnl,
                    r_multiple=r_mult,
                    opened_at=pos.opened_at,
                    closed_at=now,
                    reason=outcome,
                )
                self.closed.append(tr)
                self.risk.record_trade(tr, now.to_pydatetime() if hasattr(now, "to_pydatetime") else now)
                self.risk.close_position_risk(pos.risk_pct)
                if self.store is not None and pos.position_id is not None:
                    try:
                        self.store.delete_open_position(pos.position_id)
                    except Exception:
                        pass
                closed_now.append(tr)
            else:
                still_open.append(pos)

        self.positions = still_open
        return closed_now