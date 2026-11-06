"""Create the appropriate broker from config."""

from __future__ import annotations

from .base import BrokerInterface
from .mt5 import MT5Broker
from ..config import AppConfig
from ..risk import RiskManager


def create_broker(cfg: AppConfig, risk: RiskManager, store=None, user_id=None) -> BrokerInterface:
    mode = (cfg.mode or "paper").lower()
    if mode == "paper":
        from ..execution import PaperBroker

        return PaperBroker(cfg, risk, store=store, user_id=user_id)
    if mode in ("mt5_demo", "mt5_live"):
        return MT5Broker(cfg, risk, store=store, user_id=user_id)
    raise ValueError(f"unknown execution mode: {mode}")