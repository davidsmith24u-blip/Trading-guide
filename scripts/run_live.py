"""Paper-trading scan: fetch latest data, generate signals, size positions, notify.

This is a SKELETON. Wire a real broker adapter before any live use.
Run on a schedule (cron / task scheduler) at your entry timeframe cadence.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.data.provider import from_yfinance, synthetic_ohlcv
from src.indicators import add_indicators
from src.strategy import generate_signals, trend_state
from src.risk import RiskManager
from src.execution import PaperBroker
from src.notify.telegram import send_telegram, format_signal


def main():
    cfg = load_config()
    risk = RiskManager(cfg.risk)
    broker = PaperBroker(cfg, risk)

    for pair in cfg.pairs:
        try:
            trend = from_yfinance(pair, period="60d", interval=cfg.trend_tf.lower())
            entry = from_yfinance(pair, period="5d", interval=cfg.entry_tf.lower().replace("m", "m"))
        except Exception as e:
            print(f"{pair}: data fetch failed ({e}); using synthetic fallback")
            from src.data.provider import make_multi_tf_pair
            frames = make_multi_tf_pair(n_entry=500, seed=1)
            trend, entry = frames["trend"], frames["entry"]

        trend_i = add_indicators(trend, cfg.strategy)
        entry_i = add_indicators(entry, cfg.strategy)
        sigs = generate_signals(pair, trend_i, entry_i, cfg.strategy)

        # act only on the latest bar's signal
        if not sigs:
            print(f"{pair}: no signal (trend={trend_state(trend_i, cfg.strategy)})")
            continue
        last = sigs[-1]
        if last.timestamp != entry_i.index[-1]:
            print(f"{pair}: last signal not on latest bar")
            continue

        atr = float(entry_i["atr"].iloc[-1])
        pos = broker.open_position(last, entry_i.index[-1], atr)
        if pos is None:
            print(f"{pair}: signal not traded (risk/cooldown/drawdown)")
            continue

        print(f"{pair}: {last.reason} -> units={pos.units}")
        if cfg.telegram_enabled:
            msg = format_signal(pair, last.side, pos.entry, pos.stop_loss, pos.take_profit, last.reason)
            send_telegram(cfg.telegram_token, cfg.telegram_chat_id, msg)

    print("equity:", risk.state.equity)


if __name__ == "__main__":
    main()