"""Execution layer.

v1 implements a PAPER broker only: it simulates fills with configurable spread
and slippage and tracks open positions, closing them when SL/TP is touched.
Live broker adapters (MT5, OANDA, IBKR) should implement the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from .config import AppConfig
from .indicators import pip_size
from .risk import RiskManager, TradeResult
from .strategy import Signal


@dataclass
class Position:
    pair: str
    side: int
    units: float
    entry: float
    stop_loss: float
    take_profit: float
    orig_stop: float
    opened_at: pd.Timestamp
    reason: str
    atr: float = 0.0
    risk_pct: float = 0.0
    position_id: Optional[int] = None


class PaperBroker:
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
                    # keep risk in sync
                    self.risk.register_open_position(row.get("risk_pct", cfg.risk.risk_per_trade_pct))
            except Exception:
                pass

    def _fill_price(self, pair: str, price: float, side: int, is_entry: bool) -> float:
        pip = pip_size(pair)
        spread = self.cfg.spreads.get(pair, 1.0) * pip
        slip = self.cfg.slippage_pips * pip
        if side == 1:  # long: pay ask
            fill = price + spread / 2 + (slip if is_entry else 0)
        else:          # short: receive bid
            fill = price - spread / 2 - (slip if is_entry else 0)
        return fill

    def open_position(self, sig: Signal, now: pd.Timestamp, atr: float) -> Optional[Position]:
        allowed, _ = self.risk.trading_allowed(
            now.to_pydatetime() if hasattr(now, "to_pydatetime") else now
        )
        if not allowed:
            return None

        risk_pct = self.cfg.risk.risk_per_trade_pct
        allowed, heat_reason = self.risk.can_open_trade(risk_pct)
        if not allowed:
            import logging

            logging.getLogger("trading_guardian").warning(
                "trade blocked for %s: %s", sig.pair, heat_reason
            )
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

            # trailing / break-even
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
                # conservative: SL wins if both touched
                if hit_sl:
                    exit_px = self._fill_price(pos.pair, pos.stop_loss, pos.side, False)
                    outcome = "stop_loss"
                else:
                    exit_px = self._fill_price(pos.pair, pos.take_profit, pos.side, False)
                    outcome = "take_profit"

                pnl_price = (exit_px - pos.entry) if pos.side == 1 else (pos.entry - exit_px)
                contract = 100000.0
                pnl = pnl_price * pos.units * contract
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