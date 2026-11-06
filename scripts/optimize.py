"""Simple grid-search parameter optimization for the backtest.

Usage:
    python scripts/optimize.py
"""

from __future__ import annotations

import copy
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.engine import run_backtest
from src.config import load_config
from src.data.provider import make_multi_tf_pair


def main():
    cfg = load_config("config.example.yaml")
    data = {}
    for i, pair in enumerate(cfg.pairs):
        data[pair] = make_multi_tf_pair(n_entry=4000, seed=42 + i)

    grid = {
        "adx_threshold": [15.0, 25.0],
        "stop_atr_mult": [1.5],
        "takeprofit_rr": [2.0, 3.0],
    }

    results = []
    for combo in itertools.product(*grid.values()):
        params = dict(zip(grid.keys(), combo))
        c = copy.deepcopy(cfg)
        c.strategy.adx_threshold = params["adx_threshold"]
        c.strategy.stop_atr_mult = params["stop_atr_mult"]
        c.strategy.takeprofit_rr = params["takeprofit_rr"]
        res = run_backtest(data, c)
        m = res["metrics"]
        results.append((params, m))

    # sort by profit factor then expectancy
    results.sort(key=lambda x: (x[1].get("profit_factor", 0), x[1].get("expectancy_r", 0)), reverse=True)

    print("\nTop 5 parameter sets:")
    for params, m in results[:5]:
        print(params, "| PF:", round(m.get("profit_factor", 0), 3), "ExpR:", round(m.get("expectancy_r", 0), 3), "Trades:", m.get("n_trades", 0), "MaxDD:", round(m.get("max_drawdown_pct", 0), 2))


if __name__ == "__main__":
    main()