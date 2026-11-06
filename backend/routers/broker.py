"""Broker status endpoint (paper/MT5)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from backend.config_store import from_dict, to_dict
from backend.db import get_user_config, set_user_config
from src.broker.factory import create_broker
from src.risk import RiskManager

router = APIRouter()


@router.get("/broker-status")
def broker_status(current_user=Depends(get_current_user)):
    user_cfg = get_user_config(current_user["id"])
    if user_cfg is None:
        from backend.config_store import load as load_global

        user_cfg = to_dict(load_global())
        set_user_config(current_user["id"], user_cfg)
    cfg = from_dict(user_cfg)
    risk = RiskManager(cfg.risk)
    broker = create_broker(cfg, risk)
    connected = broker.connect() if cfg.mode != "paper" else True
    info = broker.get_account_info() if connected else {}
    positions = broker.get_positions() if connected else []
    allowed, reason = broker.is_trading_allowed()
    if cfg.mode != "paper":
        broker.disconnect()
    return {
        "mode": cfg.mode,
        "connected": connected,
        "trading_allowed": allowed,
        "reason": reason,
        "account": info,
        "open_positions": len(positions),
        "kill_switch": getattr(cfg, "kill_switch_file", "STOP_TRADING"),
    }