"""Performance metrics for a backtest."""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from ..risk import TradeResult


def compute_metrics(trades: List[TradeResult], equity_curve: pd.Series, initial_balance: float) -> dict:
    if not trades:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy_r": 0.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_win_r": 0.0,
            "avg_loss_r": 0.0,
            "sharpe": 0.0,
        }

    pnls = np.array([t.pnl for t in trades], dtype=float)
    rs = np.array([t.r_multiple for t in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    win_rate = (pnls > 0).mean()
    gross_profit = wins.sum() if len(wins) else 0.0
    gross_loss = -losses.sum() if len(losses) else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    expectancy_r = float(rs.mean()) if len(rs) else 0.0

    total_return_pct = (equity_curve.iloc[-1] / initial_balance - 1) * 100 if len(equity_curve) else 0.0

    # max drawdown
    roll_max = equity_curve.cummax()
    dd = (equity_curve - roll_max) / roll_max
    max_dd_pct = float(dd.min() * 100) if len(dd) else 0.0

    avg_win_r = float(rs[rs > 0].mean()) if (rs > 0).any() else 0.0
    avg_loss_r = float(rs[rs < 0].mean()) if (rs < 0).any() else 0.0

    # daily returns sharpe (annualized, assuming ~252 trading days)
    daily = equity_curve.resample("D").last().dropna()
    rets = daily.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else 0.0

    return {
        "n_trades": len(trades),
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor),
        "expectancy_r": expectancy_r,
        "total_return_pct": float(total_return_pct),
        "max_drawdown_pct": max_dd_pct,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "sharpe": sharpe,
    }