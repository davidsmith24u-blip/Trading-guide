"""Nightly review: calibration + schema rewrite (placeholder)."""

from __future__ import annotations

from .journal import brier_score, load_day


def nightly_review(date_str: str):
    trades = load_day(date_str)
    brier = brier_score(trades)
    print(f"review {date_str}: {len(trades)} trades, brier={brier}")
    # Opus 5.5 would rewrite Jev schema here; ship via AgenKit
    return {"date": date_str, "n_trades": len(trades), "brier": brier}