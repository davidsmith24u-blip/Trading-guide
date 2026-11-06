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
            """
        )
        # migrate older databases that lack the role column
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "role" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")


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