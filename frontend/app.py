"""Streamlit dashboard for the Trading Guardian (paper trading only)."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
PAPER_WARNING = "PAPER TRADING ONLY. Not financial advice."


def api_headers():
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def login_screen():
    st.title("Trading Guardian — Login")
    st.caption(PAPER_WARNING)
    tab_login, tab_reg = st.tabs(["Login", "Register"])
    with tab_login:
        u = st.text_input("Username", key="li_user")
        p = st.text_input("Password", type="password", key="li_pass")
        if st.button("Login"):
            try:
                r = requests.post(f"{API_BASE}/login", json={"username": u, "password": p}, timeout=10)
                if r.ok:
                    st.session_state["token"] = r.json()["access_token"]
                    st.session_state["username"] = r.json()["username"]
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "login failed"))
            except Exception as e:
                st.error(str(e))
    with tab_reg:
        u = st.text_input("Username", key="rg_user")
        p = st.text_input("Password", type="password", key="rg_pass")
        if st.button("Register"):
            try:
                r = requests.post(f"{API_BASE}/register", json={"username": u, "password": p}, timeout=10)
                if r.ok:
                    st.session_state["token"] = r.json()["access_token"]
                    st.session_state["username"] = r.json()["username"]
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "register failed"))
            except Exception as e:
                st.error(str(e))


if "token" not in st.session_state:
    login_screen()
    st.stop()

# ---------- Authenticated app ----------
st.set_page_config(page_title="Trading Guardian", layout="wide")
st.title(f"Trading Guardian — {st.session_state.get('username')}")
st.caption(PAPER_WARNING)
if st.sidebar.button("Logout"):
    for k in ("token", "username", "backtest"):
        st.session_state.pop(k, None)
    st.rerun()

with st.sidebar:
    st.header("Controls")
    pairs_input = st.multiselect(
        "Pairs",
        ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD"],
        default=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
    )
    risk_pct = st.slider("Risk per trade (%)", 0.1, 2.0, 0.5, 0.1) / 100.0
    daily_dd = st.slider("Max daily drawdown (%)", 1.0, 5.0, 2.0, 0.5) / 100.0
    weekly_dd = st.slider("Max weekly drawdown (%)", 2.0, 10.0, 5.0, 0.5) / 100.0
    n_bars = st.number_input("Synthetic bars (backtest)", 1000, 20000, 8000, 1000)
    col1, col2 = st.columns(2)
    run_bt = col1.button("Run Backtest")
    refresh_sig = col2.button("Refresh Signals")
    st.divider()
    chart_pair = st.selectbox("Chart pair", pairs_input if pairs_input else ["EURUSD"])

# ---------- Saved configs ----------
st.sidebar.divider()
st.sidebar.subheader("Saved Configs")
saved_names = []
try:
    r = requests.get(f"{API_BASE}/configs/saved", headers=api_headers(), timeout=5)
    if r.ok:
        saved_names = [x["name"] for x in r.json().get("items", [])]
except Exception:
    pass
selected_saved = st.sidebar.selectbox("Load saved config", ["(none)"] + saved_names)
colA, colB, colC = st.sidebar.columns(3)
if colA.button("Load") and selected_saved != "(none)":
    try:
        r = requests.post(f"{API_BASE}/configs/saved/{selected_saved}/activate", headers=api_headers(), timeout=5)
        if r.ok:
            st.success(f"Activated {selected_saved}")
            st.rerun()
    except Exception as e:
        st.error(str(e))
save_name = st.sidebar.text_input("Save current as")
if colB.button("Save") and save_name.strip():
    try:
        r = requests.post(f"{API_BASE}/configs/saved", json={"name": save_name.strip()}, headers=api_headers(), timeout=5)
        if r.ok:
            st.success(f"Saved {save_name}")
            st.rerun()
    except Exception as e:
        st.error(str(e))
if colC.button("Delete") and selected_saved != "(none)":
    try:
        r = requests.delete(f"{API_BASE}/configs/saved/{selected_saved}", headers=api_headers(), timeout=5)
        if r.ok:
            st.success(f"Deleted {selected_saved}")
            st.rerun()
    except Exception as e:
        st.error(str(e))

# Admin stats (optional)
try:
    me = requests.get(f"{API_BASE}/me", headers=api_headers(), timeout=5)
    if me.ok and me.json().get("role") == "admin":
        st.sidebar.divider()
        st.sidebar.subheader("Admin")
        stt = requests.get(f"{API_BASE}/admin/stats", headers=api_headers(), timeout=5)
        if stt.ok:
            s = stt.json()
            st.sidebar.write(f"Users: {s['users']} | Configs: {s['active_configs']} | Saved: {s['saved_configs']}")
except Exception:
    pass

# sync config
try:
    requests.post(
        f"{API_BASE}/config",
        json={
            "pairs": pairs_input,
            "account": {
                "risk_per_trade_pct": risk_pct,
                "max_daily_drawdown_pct": daily_dd,
                "max_weekly_drawdown_pct": weekly_dd,
            },
        },
        headers=api_headers(),
        timeout=5,
    )
except Exception:
    pass

# Signals
st.subheader("Current Signals")
signals = []
try:
    r = requests.get(
        f"{API_BASE}/signals",
        params={"pairs": ",".join(pairs_input)},
        headers=api_headers(),
        timeout=10,
    )
    if r.status_code == 401:
        st.session_state.pop("token", None)
        st.rerun()
    if r.ok:
        signals = r.json().get("signals", [])
except Exception as e:
    st.error(f"Backend unreachable: {e}")

if signals:
    sdf = pd.DataFrame(signals)
    cols = ["pair", "direction", "entry", "stop_loss", "take_profit", "reason", "trend", "timestamp"]
    st.dataframe(sdf[cols], use_container_width=True, hide_index=True)
else:
    st.info("No signals returned.")

# Risk status
st.subheader("Risk Status")
risk = {}
try:
    r = requests.get(f"{API_BASE}/risk-status", headers=api_headers(), timeout=5)
    if r.ok:
        risk = r.json()
except Exception:
    pass
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Equity", f"{risk.get('equity', 0):,.2f}")
c2.metric("Daily DD", f"{risk.get('daily_drawdown_pct', 0):.2%}")
c3.metric("Weekly DD", f"{risk.get('weekly_drawdown_pct', 0):.2%}")
c4.metric("Portfolio Heat", f"{risk.get('portfolio_heat_pct', 0):.2%} / {risk.get('max_portfolio_heat_pct', 0):.2%}")
c5.metric("Trading Allowed", "YES" if risk.get("trading_allowed") else "NO")
st.caption(f"Open positions: {risk.get('open_positions_count', 0)} | Cooldown: {risk.get('cooldown_until') or 'none'} | {risk.get('reason', '')}")

# Backtest
if run_bt:
    with st.spinner("Running backtest..."):
        payload = {
            "pairs": pairs_input,
            "n_bars": int(n_bars),
            "config_overrides": {
                "account": {
                    "risk_per_trade_pct": risk_pct,
                    "max_daily_drawdown_pct": daily_dd,
                    "max_weekly_drawdown_pct": weekly_dd,
                }
            },
        }
        try:
            r = requests.post(f"{API_BASE}/backtest", json=payload, headers=api_headers(), timeout=180)
            if r.ok:
                st.session_state["backtest"] = r.json()
            else:
                st.error(r.text)
        except Exception as e:
            st.error(str(e))

bt = st.session_state.get("backtest")
if bt:
    st.subheader("Backtest Metrics")
    m = bt["metrics"]
    mc = st.columns(4)
    mc[0].metric("Trades", m.get("n_trades", 0))
    mc[1].metric("Win Rate", f"{m.get('win_rate', 0):.2%}")
    mc[2].metric("Profit Factor", f"{m.get('profit_factor', 0):.2f}")
    mc[3].metric("Max DD", f"{m.get('max_drawdown_pct', 0):.2f}%")
    mc2 = st.columns(4)
    mc2[0].metric("Expectancy (R)", f"{m.get('expectancy_r', 0):.3f}")
    mc2[1].metric("Total Return", f"{m.get('total_return_pct', 0):.2f}%")
    mc2[2].metric("Avg Win (R)", f"{m.get('avg_win_r', 0):.2f}")
    mc2[3].metric("Sharpe", f"{m.get('sharpe', 0):.2f}")

    st.subheader("Equity Curve")
    eq = bt.get("equity_curve", [])
    if eq:
        edf = pd.DataFrame(eq)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=edf["timestamp"], y=edf["equity"], mode="lines", name="Equity"))
        fig.update_layout(height=400, xaxis_title="Time", yaxis_title="Equity")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Trades")
    trades = bt.get("trades", [])
    if trades:
        tdf = pd.DataFrame(trades)
        st.dataframe(tdf, use_container_width=True, hide_index=True)
    st.warning(bt.get("warning", PAPER_WARNING))

# Walk-Forward
st.subheader("Walk-Forward Analysis")
if st.button("Run Walk-Forward"):
    with st.spinner("Running walk-forward..."):
        payload = {
            "pairs": pairs_input,
            "n_bars": int(n_bars),
            "train_days": 180,
            "test_days": 60,
            "step_days": 60,
            "config_overrides": {
                "account": {
                    "risk_per_trade_pct": risk_pct,
                    "max_daily_drawdown_pct": daily_dd,
                    "max_weekly_drawdown_pct": weekly_dd,
                }
            },
        }
        try:
            r = requests.post(f"{API_BASE}/walk-forward", json=payload, headers=api_headers(), timeout=300)
            if r.ok:
                st.session_state["wf"] = r.json()
            else:
                st.error(r.text)
        except Exception as e:
            st.error(str(e))

wf = st.session_state.get("wf")
if wf:
    st.write("Out-of-sample aggregate:")
    st.json(wf.get("aggregate_oos", {}))
    st.write("Consistency:")
    st.json(wf.get("consistency", {}))

# Trade Journal
st.subheader("Trade Journal")
try:
    r = requests.get(f"{API_BASE}/journal", params={"limit": 50}, headers=api_headers(), timeout=10)
    if r.ok:
        jd = r.json()
        st.write("Stats:", jd.get("stats", {}))
        jdf = pd.DataFrame(jd.get("items", []))
        if not jdf.empty:
            st.dataframe(jdf, use_container_width=True, hide_index=True)
except Exception as e:
    st.info(f"Journal unavailable: {e}")

# Candlestick
st.subheader(f"Candlestick — {chart_pair}")
try:
    r = requests.get(
        f"{API_BASE}/ohlc",
        params={"pair": chart_pair, "period": "5d", "interval": "15m"},
        headers=api_headers(),
        timeout=10,
    )
    if r.ok:
        bars = r.json().get("bars", [])
        if bars:
            odf = pd.DataFrame(bars)
            fig = go.Figure(data=[go.Candlestick(
                x=odf["timestamp"], open=odf["open"], high=odf["high"],
                low=odf["low"], close=odf["close"], name=chart_pair)])
            fig.update_layout(height=400, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.info(f"OHLC unavailable: {e}")