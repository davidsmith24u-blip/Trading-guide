"""Hard deterministic risk. Model cannot override."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class RiskLimits:
    max_drawdown_pct: float = 15.0
    max_position_usd: float = 5000.0
    max_daily_loss_usd: float = 500.0
    max_portfolio_heat_pct: float = 0.03
    kill_switch_file: str = "KILL_SWITCH"


class RiskManager:
    def __init__(self, limits: RiskLimits, equity_start: float):
        self.limits = limits
        self.equity_peak = equity_start
        self.equity = equity_start
        self.daily_loss = 0.0
        self.daily_reset = datetime.now(timezone.utc).date()

    def kill_switch_active(self) -> bool:
        import os

        return os.path.exists(self.limits.kill_switch_file)

    def check(self, proposed_size_usd: float, current_position_usd: float) -> tuple[bool, str]:
        today = datetime.now(timezone.utc).date()
        if today != self.daily_reset:
            self.daily_loss = 0.0
            self.daily_reset = today

        if self.kill_switch_active():
            return False, "kill switch active"
        dd = (self.equity / self.equity_peak - 1) * 100
        if dd <= -self.limits.max_drawdown_pct:
            return False, f"max drawdown breached ({dd:.2f}%)"
        if self.daily_loss >= self.limits.max_daily_loss_usd:
            return False, "daily loss limit hit"
        if abs(current_position_usd) + proposed_size_usd > self.limits.max_position_usd:
            return False, "max position exceeded"
        heat = (abs(current_position_usd) + proposed_size_usd) / self.equity
        if heat > self.limits.max_portfolio_heat_pct:
            return False, f"portfolio heat {heat:.2%} exceeds limit"
        return True, "ok"

    def update_equity(self, equity: float):
        self.equity = equity
        self.equity_peak = max(self.equity_peak, equity)

    def record_loss(self, loss: float):
        if loss < 0:
            self.daily_loss += -loss