"""Run a backtest on synthetic (or CSV) data and print metrics.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --csv-dir data/sample
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.config import load_config
from src.data.provider import make_multi_tf_pair
from src.backtest.engine import run_backtest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default=None, help="directory with <PAIR>_trend.csv and <PAIR>_entry.csv")
    args = parser.parse_args()

    cfg = load_config("config.example.yaml")

    if args.csv_dir:
        import glob
        data = {}
        for pair in cfg.pairs:
            tp = os.path.join(args.csv_dir, f"{pair}_trend.csv")
            ep = os.path.join(args.csv_dir, f"{pair}_entry.csv")
            if not (os.path.exists(tp) and os.path.exists(ep)):
                print(f"skip {pair}: csv not found")
                continue
            from src.data.provider import load_csv
            data[pair] = {"trend": load_csv(tp), "entry": load_csv(ep)}
    else:
        data = {}
        for i, pair in enumerate(cfg.pairs):
            data[pair] = make_multi_tf_pair(n_entry=8000, seed=42 + i)

    res = run_backtest(data, cfg)
    m = res["metrics"]
    print("\n===== BACKTEST RESULTS =====")
    for k, v in m.items():
        if isinstance(v, float):
            print(f"{k:22s}: {v:,.4f}")
        else:
            print(f"{k:22s}: {v}")
    print(f"open positions at end: {len(res['open_positions'])}")

    os.makedirs("logs", exist_ok=True)
    res["equity_curve"].to_csv("logs/equity_curve.csv")
    # trade log
    rows = []
    for t in res["trades"]:
        rows.append({
            "pair": t.pair, "side": t.side, "entry": t.entry, "exit": t.exit_price,
            "sl": t.stop_loss, "tp": t.take_profit, "units": t.units, "pnl": t.pnl,
            "r": t.r_multiple, "opened": t.opened_at, "closed": t.closed_at, "reason": t.reason,
        })
    pd.DataFrame(rows).to_csv("logs/trades.csv", index=False)
    print("\nSaved logs/equity_curve.csv and logs/trades.csv")


if __name__ == "__main__":
    main()