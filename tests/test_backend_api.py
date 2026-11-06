"""Backend API tests (auth, config, backtest, journal, positions)."""

import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# Use a temp database before importing app.
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ENVIRONMENT"] = "development"

from backend.main import app  # noqa: E402

client = TestClient(app)


import uuid

@pytest.fixture
def auth_headers():
    username = f"tester_{uuid.uuid4().hex[:8]}"
    r = client.post("/register", json={"username": username, "password": "password123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_protected_requires_token():
    r = client.get("/signals")
    assert r.status_code == 401


def test_register_login():
    uname = f"u2_{uuid.uuid4().hex[:6]}"
    r = client.post("/register", json={"username": uname, "password": "password123"})
    assert r.status_code == 200
    r = client.post("/login", json={"username": uname, "password": "password123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_config_roundtrip(auth_headers):
    r = client.get("/config", headers=auth_headers)
    assert r.status_code == 200
    r = client.post("/config", json={"account": {"risk_per_trade_pct": 0.01}}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["config"]["account"]["risk_per_trade_pct"] == 0.01


def test_backtest(auth_headers):
    payload = {"pairs": ["EURUSD"], "n_bars": 3000}
    r = client.post("/backtest", json=payload, headers=auth_headers, timeout=120)
    assert r.status_code == 200
    data = r.json()
    assert "metrics" in data
    assert "equity_curve" in data
    assert "trades" in data


def test_backtest_log_journal(auth_headers):
    payload = {"pairs": ["EURUSD"], "n_bars": 3000, "log_journal": True}
    r = client.post("/backtest", json=payload, headers=auth_headers, timeout=120)
    assert r.status_code == 200
    jr = client.get("/journal", headers=auth_headers)
    assert jr.status_code == 200
    assert "stats" in jr.json()


def test_risk_status(auth_headers):
    r = client.get("/risk-status", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "portfolio_heat_pct" in data
    assert "trading_allowed" in data


def test_positions(auth_headers):
    r = client.get("/positions", headers=auth_headers)
    assert r.status_code == 200
    assert "items" in r.json()


def test_signals(auth_headers):
    r = client.get("/signals", params={"pairs": "EURUSD"}, headers=auth_headers, timeout=60)
    assert r.status_code == 200
    assert "signals" in r.json()


def test_walk_forward(auth_headers):
    payload = {"pairs": ["EURUSD"], "n_bars": 4000, "train_days": 30, "test_days": 10, "step_days": 10}
    r = client.post("/walk-forward", json=payload, headers=auth_headers, timeout=180)
    assert r.status_code == 200
    assert "consistency" in r.json()


def test_admin_stats_admin_access():
    uname = f"admin_{uuid.uuid4().hex[:6]}"
    r = client.post("/register", json={"username": uname, "password": "password123"})
    assert r.status_code == 200
    # promote to admin
    import sqlite3, os

    conn = sqlite3.connect(os.environ["DATABASE_PATH"])
    conn.execute("UPDATE users SET role='admin' WHERE username=?", (uname,))
    conn.commit()
    conn.close()
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/admin/stats", headers=h)
    assert r.status_code == 200
    assert "users" in r.json()

def test_admin_stats_forbidden():
    # ensure an admin exists first
    aname = f"admin_{uuid.uuid4().hex[:6]}"
    r = client.post("/register", json={"username": aname, "password": "password123"})
    token = r.json()["access_token"]
    import sqlite3, os

    conn = sqlite3.connect(os.environ["DATABASE_PATH"])
    conn.execute("UPDATE users SET role='admin' WHERE username=?", (aname,))
    conn.commit()
    conn.close()
    # register a regular user
    r2 = client.post("/register", json={"username": f"reg_{uuid.uuid4().hex[:6]}", "password": "password123"})
    h = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    r = client.get("/admin/stats", headers=h)
    assert r.status_code == 403