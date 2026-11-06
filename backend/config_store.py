"""Load / save / merge application configuration.

Wraps src.config so the API layer can read and update config.yaml without
touching core logic.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

from src.config import AppConfig, load_config

CONFIG_PATH = Path("config.yaml")
EXAMPLE_PATH = Path("config.example.yaml")


def get_config_path() -> Path:
    return CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH


def load() -> AppConfig:
    return load_config(str(get_config_path()))


def to_dict(cfg: AppConfig) -> Dict[str, Any]:
    """Serialize AppConfig back into the YAML-shaped dict."""
    return {
        "account": {
            "currency": cfg.risk.currency,
            "balance": cfg.risk.balance,
            "risk_per_trade_pct": cfg.risk.risk_per_trade_pct,
            "max_daily_drawdown_pct": cfg.risk.max_daily_drawdown_pct,
            "max_weekly_drawdown_pct": cfg.risk.max_weekly_drawdown_pct,
            "max_consecutive_losses": cfg.risk.max_consecutive_losses,
            "cooldown_hours": cfg.risk.cooldown_hours,
            "max_portfolio_heat_pct": cfg.risk.max_portfolio_heat_pct,
        },
        "pairs": cfg.pairs,
        "timeframes": {"trend": cfg.trend_tf, "entry": cfg.entry_tf},
        "strategy": {
            "trend_ema_fast": cfg.strategy.trend_ema_fast,
            "trend_ema_slow": cfg.strategy.trend_ema_slow,
            "adx_period": cfg.strategy.adx_period,
            "adx_threshold": cfg.strategy.adx_threshold,
            "entry_ema": cfg.strategy.entry_ema,
            "rsi_period": cfg.strategy.rsi_period,
            "rsi_long_min": cfg.strategy.rsi_long_min,
            "rsi_short_max": cfg.strategy.rsi_short_max,
            "atr_period": cfg.strategy.atr_period,
            "stop_atr_mult": cfg.strategy.stop_atr_mult,
            "takeprofit_rr": cfg.strategy.takeprofit_rr,
            "trailing_stop": cfg.strategy.trailing_stop,
            "breakeven_at_r": cfg.strategy.breakeven_at_r,
        },
        "execution": {
            "mode": cfg.mode,
            "spread_pips": cfg.spreads,
            "slippage_pips": cfg.slippage_pips,
        },
        "notifications": {
            "telegram": {
                "enabled": cfg.telegram_enabled,
                "bot_token": cfg.telegram_token,
                "chat_id": cfg.telegram_chat_id,
            }
        },
        "logging": {"trade_log": cfg.trade_log, "equity_log": cfg.equity_log},
    }


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def from_dict(data: Dict[str, Any]) -> AppConfig:
    """Build an AppConfig from a YAML-shaped dict."""
    import tempfile

    import yaml

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(data or {}, f, sort_keys=False)
        path = f.name
    return load_config(path)


def apply_overrides(cfg: AppConfig, overrides: Dict[str, Any]) -> AppConfig:
    """Return a new AppConfig with overrides merged, without persisting."""
    import tempfile

    import yaml

    merged = deep_merge(to_dict(cfg), overrides or {})
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(merged, f, sort_keys=False)
        path = f.name
    return load_config(path)


def save_dict(data: Dict[str, Any]) -> AppConfig:
    """Merge `data` into the current config dict, persist, and return AppConfig."""
    import yaml

    current = to_dict(load())
    merged = deep_merge(current, data)
    path = CONFIG_PATH
    with path.open("w") as f:
        yaml.safe_dump(merged, f, sort_keys=False)
    return load_config(str(path))