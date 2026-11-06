"""Walk-forward testing: rolling train/test windows.

Reuses the existing backtest engine. For each window we run the strategy on the
train slice (in-sample) and then on the unseen test slice (out-of-sample), and
aggregate the out-of-sample results to estimate real-world performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List

import pandas as pd

from ..config import AppConfig
from .engine import run_backtest
from .metrics import compute_metrics


@dataclass
class WindowResult:
    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    is_metrics: Dict[str, Any]
    oos_metrics: Dict[str, Any]
    oos_trades: int


def _slice_frames(data: Dict[str, dict], start: pd.Timestamp, end: pd.Timestamp) -> Dict[str, dict]:
    out = {}
    for pair, frames in data.items():
        tr = frames["trend"]
        en = frames["entry"]
        tr_s = tr[(tr.index >= start) & (tr.index < end)]
        en_s = en[(en.index >= start) & (en.index < end)]
        if tr_s.empty or en_s.empty:
            continue
        out[pair] = {"trend": tr_s, "entry": en_s}
    return out


def walk_forward(
    data: Dict[str, dict],
    cfg: AppConfig,
    train_days: int = 180,
    test_days: int = 60,
    step_days: int = 60,
) -> Dict[str, Any]:
    """Run rolling walk-forward analysis.

    Returns dict with list of windows, aggregate in-sample/out-of-sample metrics,
    and a consistency summary.
    """
    # determine global time range from entry frames
    all_ts = sorted(set().union(*[set(f["entry"].index) for f in data.values()]))
    if not all_ts:
        return {"windows": [], "aggregate_oos": {}, "aggregate_is": {}, "consistency": {}}

    start = pd.Timestamp(all_ts[0])
    end = pd.Timestamp(all_ts[-1])

    train_td = timedelta(days=train_days)
    test_td = timedelta(days=test_days)
    step_td = timedelta(days=step_days)

    windows: List[WindowResult] = []
    cursor = start
    idx = 0
    while cursor + train_td + test_td <= end:
        train_start = cursor
        train_end = cursor + train_td
        test_start = train_end
        test_end = train_end + test_td

        train_data = _slice_frames(data, train_start, train_end)
        test_data = _slice_frames(data, test_start, test_end)

        if train_data and test_data:
            is_res = run_backtest(train_data, cfg)
            oos_res = run_backtest(test_data, cfg)
            windows.append(
                WindowResult(
                    index=idx,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    is_metrics=is_res["metrics"],
                    oos_metrics=oos_res["metrics"],
                    oos_trades=oos_res["metrics"].get("n_trades", 0),
                )
            )
            idx += 1
        cursor = cursor + step_td

    # aggregate out-of-sample
    oos_returns = [w.oos_metrics.get("total_return_pct", 0.0) for w in windows]
    oos_dds = [w.oos_metrics.get("max_drawdown_pct", 0.0) for w in windows]
    oos_pfs = [w.oos_metrics.get("profit_factor", 0.0) for w in windows]
    oos_exps = [w.oos_metrics.get("expectancy_r", 0.0) for w in windows]
    oos_trades_total = sum(w.oos_metrics.get("n_trades", 0) for w in windows)

    # compounded total return
    compounded = 1.0
    for r in oos_returns:
        compounded *= (1 + r / 100.0)
    total_return = (compounded - 1) * 100.0

    profitable_windows = sum(1 for r in oos_returns if r > 0)
    consistency = {
        "n_windows": len(windows),
        "profitable_windows": profitable_windows,
        "profitable_pct": (profitable_windows / len(windows)) if windows else 0.0,
        "avg_window_return_pct": (sum(oos_returns) / len(oos_returns)) if oos_returns else 0.0,
        "std_window_return_pct": float(pd.Series(oos_returns).std()) if len(oos_returns) > 1 else 0.0,
    }

    aggregate_oos = {
        "total_return_pct": total_return,
        "max_drawdown_pct": min(oos_dds) if oos_dds else 0.0,
        "profit_factor": (sum(oos_pfs) / len(oos_pfs)) if oos_pfs else 0.0,
        "expectancy_r": (sum(oos_exps) / len(oos_exps)) if oos_exps else 0.0,
        "n_trades": oos_trades_total,
        "n_windows": len(windows),
    }

    is_returns = [w.is_metrics.get("total_return_pct", 0.0) for w in windows]
    aggregate_is = {
        "avg_window_return_pct": (sum(is_returns) / len(is_returns)) if is_returns else 0.0,
        "max_drawdown_pct": min([w.is_metrics.get("max_drawdown_pct", 0.0) for w in windows]) if windows else 0.0,
        "avg_profit_factor": (sum(w.is_metrics.get("profit_factor", 0.0) for w in windows) / len(windows)) if windows else 0.0,
        "avg_expectancy_r": (sum(w.is_metrics.get("expectancy_r", 0.0) for w in windows) / len(windows)) if windows else 0.0,
    }

    return {
        "windows": [
            {
                "index": w.index,
                "train_start": str(w.train_start),
                "train_end": str(w.train_end),
                "test_start": str(w.test_start),
                "test_end": str(w.test_end),
                "is": w.is_metrics,
                "oos": w.oos_metrics,
            }
            for w in windows
        ],
        "aggregate_is": aggregate_is,
        "aggregate_oos": aggregate_oos,
        "consistency": consistency,
    }