"""SQLite trade journal."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

DB_PATH = os.getenv("JOURNAL_DB", "crypto_agent/journal.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER,
                symbol TEXT,
                decision TEXT,
                action TEXT,
                size REAL,
                pnl REAL,
                brier REAL,
                notes TEXT
            )"""
        )


def log_trade(ts, decision, action, size=0.0, pnl=0.0, notes=""):
    with _conn() as c:
        c.execute(
            "INSERT INTO trades (ts, symbol, decision, action, size, pnl, notes) VALUES (?,?,?,?,?,?,?)",
            (ts, decision.get("symbol", ""), json.dumps(decision), action, size, pnl, notes),
        )


def load_day(date_str: str) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM trades WHERE date(ts/1000,'unixepoch')=?", (date_str,)).fetchall()
        return [dict(r) for r in rows]


def brier_score(trades: List[Dict[str, Any]]) -> float:
    # placeholder: requires calibrated_prob vs outcome
    return 0.0