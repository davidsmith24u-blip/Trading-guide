"""Risk status endpoint."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from backend.config_store import from_dict, to_dict
from backend.db import get_user_config, load_open_positions, set_user_config
from backend.schemas import RiskStatusResponse
from src.risk import RiskManager

router = APIRouter()

PAPER_WARNING = "PAPER TRADING ONLY. Risk status reflects the configured account."


@router.get("/risk-status", response_model=RiskStatusResponse)
def risk_status(current_user=Depends(get_current_user)):
    user_cfg = get_user_config(current_user["id"])
    if user_cfg is None:
        from backend.config_store import load as load_global

        user_cfg = to_dict(load_global())
        set_user_config(current_user["id"], user_cfg)
    cfg = from_dict(user_cfg)
    open_positions = load_open_positions(current_user["id"])
    open_risks = [float(p.get("risk_pct", cfg.risk.risk_per_trade_pct)) for p in open_positions]
    rm = RiskManager(cfg.risk, open_risk_pcts=open_risks)
    allowed, reason = rm.trading_allowed(datetime.now(timezone.utc))
    # also block if heat at limit? heat only matters for new trades; still report
    return RiskStatusResponse(
        equity=rm.state.equity,
        daily_drawdown_pct=rm.daily_drawdown_pct(),
        weekly_drawdown_pct=rm.weekly_drawdown_pct(),
        consecutive_losses=rm.state.consecutive_losses,
        cooldown_until=(rm.state.cooldown_until.isoformat() if rm.state.cooldown_until else None),
        trading_allowed=allowed,
        reason=reason,
        warning=PAPER_WARNING,
        portfolio_heat_pct=rm.portfolio_heat(),
        max_portfolio_heat_pct=cfg.risk.max_portfolio_heat_pct,
        open_positions_count=len(open_positions),
    )