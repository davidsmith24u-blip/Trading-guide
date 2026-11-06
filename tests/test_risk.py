import datetime

from src.config import RiskConfig
from src.risk import RiskManager, TradeResult
import pandas as pd


def test_position_size_positive():
    rm = RiskManager(RiskConfig(balance=10000, risk_per_trade_pct=0.01))
    size = rm.position_size("EURUSD", 1.1000, 1.0950)
    assert size > 0


def test_drawdown_block():
    rm = RiskManager(RiskConfig(balance=10000, max_daily_drawdown_pct=0.02))
    rm.trading_allowed()  # roll calendar
    rm.state.day_start_equity = 10000.0
    rm.state.equity = 9700.0
    ok, msg = rm.trading_allowed()
    assert ok is False
    assert "drawdown" in msg


def test_consecutive_loss_cooldown():
    rm = RiskManager(RiskConfig(balance=10000, max_consecutive_losses=2, cooldown_hours=1))
    now = datetime.datetime.now(datetime.timezone.utc)
    for _ in range(2):
        rm.record_trade(TradeResult("EURUSD", 1, 1.1, 1.09, 1.09, 1.12, 0.1, -100, -1,
                                    pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01"), "sl"),
                        now=now)
    assert rm.state.cooldown_until is not None
    ok, msg = rm.trading_allowed(now)
    assert ok is False
    assert "cooldown" in msg