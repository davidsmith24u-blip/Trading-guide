"""Tiny SQLite persistence for users, roles, configs, and saved strategies."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.getenv("DATABASE_PATH", "data/trading_guardian.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_configs (
                user_id INTEGER PRIMARY KEY,
                config_json TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS user_saved_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, name),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS trade_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                source TEXT NOT NULL DEFAULT 'paper',
                pair TEXT NOT NULL,
                side INTEGER NOT NULL,
                entry REAL NOT NULL,
                exit_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                units REAL NOT NULL,
                pnl REAL NOT NULL,
                r_multiple REAL NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT NOT NULL,
                reason TEXT,
                tags TEXT,
                notes TEXT
            );
            """
        )
        # migrate older databases that lack the role column
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "role" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

        # open positions table
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS open_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pair TEXT NOT NULL,
                side INTEGER NOT NULL,
                units REAL NOT NULL,
                entry REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                orig_stop REAL NOT NULL,
                opened_at TEXT NOT NULL,
                reason TEXT,
                atr REAL NOT NULL,
                risk_pct REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )


def _user_count() -> int:
    with _conn() as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"])


def create_user(username: str, password_hash: str, role: str = "user") -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, datetime.now(timezone.utc).isoformat()),
        )
        return int(cur.lastrowid)


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_config(user_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT config_json FROM user_configs WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return None
        return json.loads(row["config_json"])


def set_user_config(user_id: int, config: Dict[str, Any]) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO user_configs (user_id, config_json) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET config_json = excluded.config_json
            """,
            (user_id, json.dumps(config)),
        )


def list_saved_configs(user_id: int) -> List[Dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT name, created_at FROM user_saved_configs WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_saved_config(user_id: int, name: str) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT config_json FROM user_saved_configs WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        if not row:
            return None
        return json.loads(row["config_json"])


def save_saved_config(user_id: int, name: str, config: Dict[str, Any]) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO user_saved_configs (user_id, name, config_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, name) DO UPDATE SET config_json = excluded.config_json
            """,
            (user_id, name, json.dumps(config), datetime.now(timezone.utc).isoformat()),
        )


def delete_saved_config(user_id: int, name: str) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM user_saved_configs WHERE user_id = ? AND name = ?", (user_id, name)
        )
        return cur.rowcount > 0


def count_users() -> int:
    return _user_count()


def count_configs() -> int:
    with _conn() as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM user_configs").fetchone()["c"])


def count_saved_configs() -> int:
    with _conn() as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM user_saved_configs").fetchone()["c"])


# ---- open positions (paper) ----
def init_open_positions_table() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS open_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pair TEXT NOT NULL,
                side INTEGER NOT NULL,
                units REAL NOT NULL,
                entry REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                orig_stop REAL NOT NULL,
                opened_at TEXT NOT NULL,
                reason TEXT,
                atr REAL NOT NULL,
                risk_pct REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )


def save_open_position(user_id: int, pos) -> int:
    init_open_positions_table()
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO open_positions
            (user_id, pair, side, units, entry, stop_loss, take_profit, orig_stop, opened_at, reason, atr, risk_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                pos.pair,
                pos.side,
                pos.units,
                pos.entry,
                pos.stop_loss,
                pos.take_profit,
                pos.orig_stop,
                str(pos.opened_at),
                pos.reason,
                pos.atr,
                pos.risk_pct,
            ),
        )
        return int(cur.lastrowid)


def load_open_positions(user_id: int) -> list:
    init_open_positions_table()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM open_positions WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_open_position(position_id: int) -> None:
    init_open_positions_table()
    with _conn() as conn:
        conn.execute("DELETE FROM open_positions WHERE id = ?", (position_id,))


# ---- trade journal ----
def log_trade(user_id, trade: dict, source: str = "paper", notes: str = "", tags: str = "") -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO trade_journal
            (user_id, source, pair, side, entry, exit_price, stop_loss, take_profit, units, pnl, r_multiple, opened_at, closed_at, reason, tags, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                source,
                trade["pair"],
                trade["side"],
                trade["entry"],
                trade["exit_price"],
                trade["stop_loss"],
                trade["take_profit"],
                trade["units"],
                trade["pnl"],
                trade["r_multiple"],
                str(trade["opened_at"]),
                str(trade["closed_at"]),
                trade.get("reason", ""),
                tags,
                notes,
            ),
        )
        return int(cur.lastrowid)


def list_trades(user_id=None, limit: int = 100, source: str = None) -> list:
    with _conn() as conn:
        q = "SELECT * FROM trade_journal"
        params = []
        conds = []
        if user_id is not None:
            conds.append("user_id = ?")
            params.append(user_id)
        if source is not None:
            conds.append("source = ?")
            params.append(source)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY closed_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]


def update_trade_journal(trade_id: int, notes: str = None, tags: str = None) -> bool:
    with _conn() as conn:
        fields = []
        params = []
        if notes is not None:
            fields.append("notes = ?")
            params.append(notes)
        if tags is not None:
            fields.append("tags = ?")
            params.append(tags)
        if not fields:
            return False
        params.append(trade_id)
        cur = conn.execute(f"UPDATE trade_journal SET {', '.join(fields)} WHERE id = ?", params)
        return cur.rowcount > 0


def trade_stats(user_id=None, source: str = None) -> dict:
    trades = list_trades(user_id=user_id, limit=10000, source=source)
    if not trades:
        return {"n_trades": 0, "win_rate": 0.0, "total_pnl": 0.0, "avg_r": 0.0}
    pnls = [t["pnl"] for t in trades]
    rs = [t["r_multiple"] for t in trades]
    wins = [p for p in pnls if p > 0]
    return {
        "n_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "total_pnl": sum(pnls),
        "avg_r": sum(rs) / len(rs),
    }