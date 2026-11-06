"""Run walk-forward analysis on synthetic (or CSV) data.

Usage:
    python scripts/run_walk_forward.py
    python scripts/run_walk_forward.py --train-days 180 --test-days 60 --step-days 60
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.walk_forward import walk_forward
from src.config import load_config
from src.data.provider import make_multi_tf_pair


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--test-days", type=int, default=40)
    parser.add_argument("--step-days", type=int, default=40)
    parser.add_argument("--n-bars", type=int, default=20000)
    args = parser.parse_args()

    cfg = load_config("config.example.yaml")
    data = {}
    for i, pair in enumerate(cfg.pairs):
        data[pair] = make_multi_tf_pair(n_entry=args.n_bars, seed=42 + i)

    res = walk_forward(data, cfg, args.train_days, args.test_days, args.step_days)

    print("\n===== WALK-FORWARD SUMMARY =====")
    print(f"windows: {res['consistency'].get('n_windows', 0)}")
    print("\n-- In-sample (avg across windows) --")
    for k, v in res["aggregate_is"].items():
        print(f"{k:24s}: {v:,.4f}" if isinstance(v, float) else f"{k:24s}: {v}")
    print("\n-- Out-of-sample (aggregated) --")
    for k, v in res["aggregate_oos"].items():
        print(f"{k:24s}: {v:,.4f}" if isinstance(v, float) else f"{k:24s}: {v}")
    print("\n-- Consistency --")
    for k, v in res["consistency"].items():
        print(f"{k:24s}: {v:,.4f}" if isinstance(v, float) else f"{k:24s}: {v}")

    print("\nPer-window OOS returns:")
    for w in res["windows"]:
        print(f"  window {w['index']}: {w['test_start'][:10]} -> {w['test_end'][:10]}  return={w['oos'].get('total_return_pct',0):.2f}%  trades={w['oos'].get('n_trades',0)}")


if __name__ == "__main__":
    main()