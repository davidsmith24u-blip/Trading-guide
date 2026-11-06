"""Background paper/MT5 trading runner.

Suitable for cron or systemd. Runs a scan every N minutes, sends Telegram
alerts, reconciles positions, and respects the kill switch.

Usage:
    python scripts/runner.py
    python scripts/runner.py --once
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.broker.factory import create_broker
from src.config import load_config
from src.data.provider import from_yfinance, make_multi_tf_pair
from src.indicators import add_indicators
from src.notify.telegram import format_signal, send_telegram
from src.risk import RiskManager
from src.strategy import generate_signals, regime_filter_reason, trend_state

STATE_PATH = os.getenv("RUNNER_STATE", "data/runner_state.json")
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))


def load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"last_signal": {}, "last_run": None, "expected_tickets": []}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)


def fetch(pair, cfg, broker=None):
    # Prefer MT5 rates when running in MT5 mode for consistency with execution.
    if broker is not None and hasattr(broker, "get_rates") and cfg.mode.startswith("mt5"):
        try:
            trend = broker.get_rates(pair, cfg.trend_tf, 500)
            entry = broker.get_rates(pair, cfg.entry_tf, 2000)
            if not trend.empty and not entry.empty:
                return trend, entry
        except Exception:
            pass
    try:
        trend = from_yfinance(pair, period="60d", interval=cfg.trend_tf.lower().replace("h", "h"))
        entry = from_yfinance(pair, period="5d", interval=cfg.entry_tf.lower())
        if trend.empty or entry.empty:
            raise RuntimeError("empty")
    except Exception:
        frames = make_multi_tf_pair(n_entry=2000, seed=abs(hash(pair)) % 1000)
        trend, entry = frames["trend"], frames["entry"]
    return trend, entry


def run_once(cfg, state) -> None:
    risk = RiskManager(cfg.risk)
    broker = create_broker(cfg, risk)
    if not broker.connect():
        msg = "broker connection failed; aborting scan"
        print(msg)
        if cfg.telegram_enabled:
            send_telegram(cfg.telegram_token, cfg.telegram_chat_id, "🚨 " + msg)
        return

    # kill switch check
    if os.path.exists(cfg.kill_switch_file):
        print("kill switch active; no new orders")
        if cfg.telegram_enabled:
            send_telegram(cfg.telegram_token, cfg.telegram_chat_id, "🛑 Kill switch active; trading blocked")
        broker.disconnect()
        return

    # reconciliation
    expected = state.get("expected_tickets", [])
    recon = broker.reconcile(expected)
    if recon["missing"] or recon["unexpected"]:
        alert = f"⚠️ Position reconciliation mismatch: missing={recon['missing']} unexpected={recon['unexpected']}"
        print(alert)
        if cfg.telegram_enabled:
            send_telegram(cfg.telegram_token, cfg.telegram_chat_id, alert)

    allowed, reason = broker.is_trading_allowed()
    if not allowed:
        print(f"trading blocked: {reason}")
        if cfg.telegram_enabled:
            send_telegram(cfg.telegram_token, cfg.telegram_chat_id, f"⛔ Trading blocked: {reason}")
        # still continue to monitor

    alerts = []
    wd_ok, wd_reason = broker.watchdog() if hasattr(broker, "watchdog") else (True, "ok")
    if not wd_ok:
        alerts.append(f"🔌 Connection issue: {wd_reason}")

    heat = risk.portfolio_heat()
    dd = risk.daily_drawdown_pct()
    wh = risk.weekly_drawdown_pct()
    if dd <= -0.8 * cfg.risk.max_daily_drawdown_pct:
        alerts.append(f"⚠️ Daily drawdown approaching limit: {dd:.2%}")
    if wh <= -0.8 * cfg.risk.max_weekly_drawdown_pct:
        alerts.append(f"⚠️ Weekly drawdown approaching limit: {wh:.2%}")
    if heat >= 0.8 * cfg.risk.max_portfolio_heat_pct:
        alerts.append(f"🔥 Portfolio heat high: {heat:.2%}")

    for pair in cfg.pairs:
        trend, entry = fetch(pair, cfg, broker)
        trend_i = add_indicators(trend.copy(), cfg.strategy)
        entry_i = add_indicators(entry.copy(), cfg.strategy)
        sigs = generate_signals(pair, trend_i, entry_i, cfg.strategy)
        ts_state = trend_state(trend_i, cfg.strategy)
        ok, regime_reason = regime_filter_reason(trend_i, cfg.strategy)

        if not sigs:
            print(f"{pair}: no signal (trend={ts_state})")
            continue
        last = sigs[-1]
        if last.timestamp != entry_i.index[-1]:
            continue
        if not ok:
            print(f"{pair}: signal rejected - {regime_reason}")
            continue

        key = f"{pair}:{last.timestamp}"
        if state["last_signal"].get(pair) == str(last.timestamp):
            print(f"{pair}: duplicate signal, skipped")
            continue

        state["last_signal"][pair] = str(last.timestamp)
        save_state(state)

        # rate/volume normalization handled by broker
        size = risk.position_size(pair, last.entry, last.stop_loss)
        print(f"{pair}: {last.reason} -> size={size} heat={heat:.2%}")
        if size > 0 and allowed:
            res = broker.place_order(last, size)
            if res.success:
                print(f"  order placed ticket={res.ticket} price={res.price}")
                if res.ticket is not None:
                    state.setdefault("expected_tickets", []).append(res.ticket)
                    save_state(state)
                if cfg.telegram_enabled:
                    msg = format_signal(pair, last.side, res.price or last.entry, last.stop_loss, last.take_profit, last.reason, heat)
                    send_telegram(cfg.telegram_token, cfg.telegram_chat_id, msg)
            else:
                print(f"  order failed: {res.message}")
                if cfg.telegram_enabled:
                    send_telegram(cfg.telegram_token, cfg.telegram_chat_id, f"❌ Order failed {pair}: {res.message}")
        else:
            print(f"  no size or trading blocked")

    if cfg.telegram_enabled:
        for a in alerts:
            send_telegram(cfg.telegram_token, cfg.telegram_chat_id, a)

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    broker.disconnect()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    state = load_state()

    if args.once:
        run_once(cfg, state)
        return

    while True:
        try:
            run_once(cfg, state)
        except Exception as e:
            print(f"runner error: {e}")
            if cfg.telegram_enabled:
                send_telegram(cfg.telegram_token, cfg.telegram_chat_id, f"🚨 Runner error: {e}")
        time.sleep(SCAN_INTERVAL * 60)


if __name__ == "__main__":
    main()