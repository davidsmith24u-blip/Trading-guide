"""Minimal Telegram notifier using the Bot API directly (no heavy SDK)."""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(bot_token: str, chat_id: str, text: str, timeout: int = 10) -> bool:
    """Send a message. Returns True on success. Never raises (logs instead)."""
    if not bot_token or not chat_id:
        logger.warning("Telegram not configured; skipping message: %s", text[:80])
        return False
    try:
        r = requests.post(
            TELEGRAM_API.format(token=bot_token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=timeout,
        )
        if r.status_code != 200:
            logger.error("Telegram send failed: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:  # network errors must not crash trading loop
        logger.exception("Telegram exception: %s", e)
        return False


def format_signal(pair: str, side: int, entry: float, sl: float, tp: float, reason: str, portfolio_heat: float = 0.0) -> str:
    direction = "BUY / LONG" if side == 1 else "SELL / SHORT"
    emoji = "🟢" if side == 1 else "🔴"
    heat_line = f"Portfolio heat: {portfolio_heat:.2%}\n" if portfolio_heat else ""
    return (
        f"{emoji} <b>{direction} {pair}</b>\n"
        f"Entry: {entry:.5f}\n"
        f"Stop Loss: {sl:.5f}\n"
        f"Take Profit: {tp:.5f}\n"
        f"R:R: 1:{2.0:.1f}\n"
        f"{heat_line}"
        f"Reason: {reason}\n"
        f"<i>Paper trading only. Not financial advice.</i>"
    )