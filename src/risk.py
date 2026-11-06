"""Risk management: the heart of the guardian.

Rules enforced here:
  - Fixed fractional sizing: risk % of current equity per trade.
  - Mandatory stop loss (position size derived from stop distance).
  - Daily and weekly drawdown limits (hard stop trading when breached).
  - Consecutive-loss cooldown.
  - Optional trailing stop / break-even helpers.

This module is intentionally stateful but tiny so you can audit every rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from .config import RiskConfig
from .indicators import pip_size


@dataclass
class TradeResult:
    pair: str
    side: int
    entry: float
    exit_price: float
    stop_loss: float
    take_profit: float
    units: float
    pnl: float
    r_multiple: float
    opened_at: pd.Timestamp
    closed_at: pd.Timestamp
    reason: str


@dataclass
class RiskState:
    equity: float
    day_start_equity: float
    week_start_equity: float
    day_key: Optional[str] = None
    week_key: Optional[str] = None
    consecutive_losses: int = 0
    cooldown_until: Optional[datetime] = None
    trades_today: int = 0


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self.state = RiskState(
            equity=cfg.balance,
            day_start_equity=cfg.balance,
            week_start_equity=cfg.balance,
        )

    # ------------------------------------------------------------------ #
    # Calendar / drawdown bookkeeping
    # ------------------------------------------------------------------ #
    def _roll_calendars(self, now: datetime) -> None:
        day_key = now.strftime("%Y-%m-%d")
        # ISO week key
        week_key = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
        if self.state.day_key != day_key:
            self.state.day_key = day_key
            self.state.day_start_equity = self.state.equity
            self.state.trades_today = 0
        if self.state.week_key != week_key:
            self.state.week_key = week_key
            self.state.week_start_equity = self.state.equity

    def daily_drawdown_pct(self) -> float:
        base = self.state.day_start_equity
        if base <= 0:
            return 0.0
        return (self.state.equity - base) / base

    def weekly_drawdown_pct(self) -> float:
        base = self.state.week_start_equity
        if base <= 0:
            return 0.0
        return (self.state.equity - base) / base

    def trading_allowed(self, now: Optional[datetime] = None) -> tuple[bool, str]:
        now = now or datetime.now(timezone.utc)
        self._roll_calendars(now)

        if self.state.cooldown_until and now < self.state.cooldown_until:
            return False, f"cooldown until {self.state.cooldown_until.isoformat()}"

        dd_day = self.daily_drawdown_pct()
        if dd_day <= -self.cfg.max_daily_drawdown_pct:
            return False, f"daily drawdown limit hit ({dd_day:.2%})"

        dd_week = self.weekly_drawdown_pct()
        if dd_week <= -self.cfg.max_weekly_drawdown_pct:
            return False, f"weekly drawdown limit hit ({dd_week:.2%})"

        return True, "ok"

    # ------------------------------------------------------------------ #
    # Position sizing
    # ------------------------------------------------------------------ #
    def position_size(
        self,
        pair: str,
        entry: float,
        stop_loss: float,
        pip_value: float = 10.0,
    ) -> float:
        """Fixed-fractional sizing: units = (equity * risk%) / (stop_distance * pip_value_per_unit).

        For simplicity we treat `pip_value` as USD per pip per standard lot
        (100k units). Returns lots (fractional allowed). Never negative.
        """
        risk_amount = self.state.equity * self.cfg.risk_per_trade_pct
        stop_distance_price = abs(entry - stop_loss)
        if stop_distance_price <= 0:
            return 0.0

        ps = pip_size(pair)
        stop_pips = stop_distance_price / ps
        if stop_pips <= 0:
            return 0.0

        # value per pip for one standard lot
        value_per_pip_per_lot = pip_value
        risk_per_lot = stop_pips * value_per_pip_per_lot
        if risk_per_lot <= 0:
            return 0.0

        lots = risk_amount / risk_per_lot
        # safety cap: never more than 10 lots for a retail account
        lots = min(lots, 10.0)
        return round(max(lots, 0.0), 4)

    # ------------------------------------------------------------------ #
    # Trade accounting
    # ------------------------------------------------------------------ #
    def record_trade(self, result: TradeResult, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._roll_calendars(now)
        self.state.equity += result.pnl
        self.state.trades_today += 1

        if result.pnl < 0:
            self.state.consecutive_losses += 1
            if self.state.consecutive_losses >= self.cfg.max_consecutive_losses:
                self.state.cooldown_until = now + timedelta(hours=self.cfg.cooldown_hours)
                self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses = 0

    # ------------------------------------------------------------------ #
    # Stop-management helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def update_stop(
        side: int,
        entry: float,
        current_stop: float,
        current_price: float,
        atr: float,
        cfg_strategy,
    ) -> float:
        """Apply break-even and trailing-stop rules. Returns new stop."""
        risk = abs(entry - current_stop) if current_stop else 0.0
        if risk <= 0:
            return current_stop

        # break-even: once price moves +breakeven_at_r * R, move SL to entry
        if side == 1:
            if current_price - entry >= cfg_strategy.breakeven_at_r * risk:
                current_stop = max(current_stop, entry)
            # trailing: keep stop at (price - 1.5*ATR) once in profit
            if cfg_strategy.trailing_stop and current_price > entry:
                trail = current_price - cfg_strategy.stop_atr_mult * atr
                current_stop = max(current_stop, trail)
        else:
            if entry - current_price >= cfg_strategy.breakeven_at_r * risk:
                current_stop = min(current_stop, entry)
            if cfg_strategy.trailing_stop and current_price < entry:
                trail = current_price + cfg_strategy.stop_atr_mult * atr
                current_stop = min(current_stop, trail)
        return current_stop