"""Pydantic request/response models for the API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    pairs: List[str] = Field(default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    start: Optional[str] = None   # ISO date; None -> synthetic recent data
    end: Optional[str] = None
    n_bars: Optional[int] = None  # override number of synthetic bars
    config_overrides: Optional[Dict[str, Any]] = None
    log_journal: bool = False


class EquityPoint(BaseModel):
    timestamp: str
    equity: float


class TradeOut(BaseModel):
    pair: str
    side: int
    entry: float
    exit_price: float
    stop_loss: float
    take_profit: float
    units: float
    pnl: float
    r_multiple: float
    opened_at: str
    closed_at: str
    reason: str


class BacktestResponse(BaseModel):
    metrics: Dict[str, Any]
    equity_curve: List[EquityPoint]
    trades: List[TradeOut]
    warning: str


class SignalOut(BaseModel):
    timestamp: Optional[str] = None
    pair: str
    side: int
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    reason: str
    trend: int


class SignalsResponse(BaseModel):
    signals: List[SignalOut]
    warning: str


class RiskStatusResponse(BaseModel):
    equity: float
    daily_drawdown_pct: float
    weekly_drawdown_pct: float
    consecutive_losses: int
    cooldown_until: Optional[str]
    trading_allowed: bool
    reason: str
    warning: str
    portfolio_heat_pct: float = 0.0
    max_portfolio_heat_pct: float = 0.0
    open_positions_count: int = 0


class WalkForwardRequest(BaseModel):
    pairs: List[str] = Field(default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    start: Optional[str] = None
    end: Optional[str] = None
    n_bars: Optional[int] = None
    train_days: int = 180
    test_days: int = 60
    step_days: int = 60
    config_overrides: Optional[Dict[str, Any]] = None


class ConfigResponse(BaseModel):
    config: Dict[str, Any]