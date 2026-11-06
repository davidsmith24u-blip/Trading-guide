"""Configuration loading for the trading guardian.

We keep config in YAML so non-developers can tune rules without touching code.
Secrets (Telegram token, etc.) live in config.yaml which is gitignored.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class RiskConfig:
    currency: str = "USD"
    balance: float = 10000.0
    risk_per_trade_pct: float = 0.005
    max_daily_drawdown_pct: float = 0.02
    max_weekly_drawdown_pct: float = 0.05
    max_consecutive_losses: int = 3
    cooldown_hours: int = 24
    max_portfolio_heat_pct: float = 0.025  # total open risk across all pairs


@dataclass
class StrategyConfig:
    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    adx_period: int = 14
    adx_threshold: float = 15.0
    entry_ema: int = 50
    rsi_period: int = 14
    rsi_long_min: float = 40.0
    rsi_short_max: float = 60.0
    atr_period: int = 14
    stop_atr_mult: float = 1.5
    takeprofit_rr: float = 2.0
    trailing_stop: bool = True
    breakeven_at_r: float = 1.0
    # regime filter (additional, transparent)
    regime_adx_threshold: float = 25.0
    regime_atr_lookback: int = 20
    regime_atr_expansion: float = 1.1


@dataclass
class AppConfig:
    risk: RiskConfig = field(default_factory=RiskConfig)
    pairs: List[str] = field(default_factory=lambda: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    trend_tf: str = "4H"
    entry_tf: str = "15m"
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    spreads: Dict[str, float] = field(default_factory=dict)
    slippage_pips: float = 0.5
    commission_per_lot: float = 0.0
    mode: str = "paper"
    confirm_live: bool = False
    kill_switch_file: str = "STOP_TRADING"
    mt5: Dict[str, Any] = field(default_factory=dict)
    telegram_enabled: bool = False
    telegram_token: str = ""
    telegram_chat_id: str = ""
    trade_log: str = "logs/trades.csv"
    equity_log: str = "logs/equity.csv"


def load_config(path: str | os.PathLike = "config.yaml") -> AppConfig:
    """Load config from YAML, falling back to sane defaults if file is missing."""
    p = Path(path)
    if not p.exists():
        # Fall back to example file so the app can still run in demo mode.
        example = Path("config.example.yaml")
        if example.exists():
            p = example
        else:
            return AppConfig()

    with p.open() as f:
        raw: Dict[str, Any] = yaml.safe_load(f) or {}

    cfg = AppConfig()
    acc = raw.get("account", {})
    cfg.risk = RiskConfig(
        currency=acc.get("currency", cfg.risk.currency),
        balance=float(acc.get("balance", cfg.risk.balance)),
        risk_per_trade_pct=float(acc.get("risk_per_trade_pct", cfg.risk.risk_per_trade_pct)),
        max_daily_drawdown_pct=float(acc.get("max_daily_drawdown_pct", cfg.risk.max_daily_drawdown_pct)),
        max_weekly_drawdown_pct=float(acc.get("max_weekly_drawdown_pct", cfg.risk.max_weekly_drawdown_pct)),
        max_consecutive_losses=int(acc.get("max_consecutive_losses", cfg.risk.max_consecutive_losses)),
        cooldown_hours=int(acc.get("cooldown_hours", cfg.risk.cooldown_hours)),
        max_portfolio_heat_pct=float(acc.get("max_portfolio_heat_pct", cfg.risk.max_portfolio_heat_pct)),
    )

    cfg.pairs = raw.get("pairs", cfg.pairs)
    tfs = raw.get("timeframes", {})
    cfg.trend_tf = tfs.get("trend", cfg.trend_tf)
    cfg.entry_tf = tfs.get("entry", cfg.entry_tf)

    s = raw.get("strategy", {})
    cfg.strategy = StrategyConfig(
        trend_ema_fast=int(s.get("trend_ema_fast", cfg.strategy.trend_ema_fast)),
        trend_ema_slow=int(s.get("trend_ema_slow", cfg.strategy.trend_ema_slow)),
        adx_period=int(s.get("adx_period", cfg.strategy.adx_period)),
        adx_threshold=float(s.get("adx_threshold", cfg.strategy.adx_threshold)),
        entry_ema=int(s.get("entry_ema", cfg.strategy.entry_ema)),
        rsi_period=int(s.get("rsi_period", cfg.strategy.rsi_period)),
        rsi_long_min=float(s.get("rsi_long_min", cfg.strategy.rsi_long_min)),
        rsi_short_max=float(s.get("rsi_short_max", cfg.strategy.rsi_short_max)),
        atr_period=int(s.get("atr_period", cfg.strategy.atr_period)),
        stop_atr_mult=float(s.get("stop_atr_mult", cfg.strategy.stop_atr_mult)),
        takeprofit_rr=float(s.get("takeprofit_rr", cfg.strategy.takeprofit_rr)),
        trailing_stop=bool(s.get("trailing_stop", cfg.strategy.trailing_stop)),
        breakeven_at_r=float(s.get("breakeven_at_r", cfg.strategy.breakeven_at_r)),
        regime_adx_threshold=float(s.get("regime_adx_threshold", cfg.strategy.regime_adx_threshold)),
        regime_atr_lookback=int(s.get("regime_atr_lookback", cfg.strategy.regime_atr_lookback)),
        regime_atr_expansion=float(s.get("regime_atr_expansion", cfg.strategy.regime_atr_expansion)),
    )

    ex = raw.get("execution", {})
    cfg.mode = ex.get("mode", cfg.mode)
    cfg.spreads = ex.get("spread_pips", cfg.spreads)
    cfg.slippage_pips = float(ex.get("slippage_pips", cfg.slippage_pips))
    cfg.commission_per_lot = float(ex.get("commission_per_lot", cfg.commission_per_lot))
    cfg.mt5 = raw.get("mt5", {}) or {}
    ex = raw.get("execution", {})
    cfg.confirm_live = bool(ex.get("confirm_live", cfg.confirm_live))
    cfg.kill_switch_file = ex.get("kill_switch_file", cfg.kill_switch_file)

    n = raw.get("notifications", {}).get("telegram", {})
    cfg.telegram_enabled = bool(n.get("enabled", False))
    cfg.telegram_token = n.get("bot_token", "") or ""
    cfg.telegram_chat_id = str(n.get("chat_id", "") or "")

    lg = raw.get("logging", {})
    cfg.trade_log = lg.get("trade_log", cfg.trade_log)
    cfg.equity_log = lg.get("equity_log", cfg.equity_log)

    return cfg