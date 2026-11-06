"""Extra core tests: regime filter, risk heat, broker factory, walk-forward."""

import os
import tempfile

import pytest

from src.config import load_config
from src.data.provider import make_multi_tf_pair
from src.indicators import add_indicators
from src.risk import RiskManager
from src.strategy import regime_filter_reason
from src.broker.factory import create_broker


def test_regime_filter_reason_returns_tuple():
    cfg = load_config("config.example.yaml")
    frames = make_multi_tf_pair(n_entry=2000, seed=1)
    trend_i = add_indicators(frames["trend"].copy(), cfg.strategy)
    ok, reason = regime_filter_reason(trend_i, cfg.strategy)
    assert isinstance(ok, bool)
    assert isinstance(reason, str)


def test_risk_heat_blocks():
    cfg = load_config("config.example.yaml")
    rm = RiskManager(cfg.risk)
    rm.cfg.max_portfolio_heat_pct = 0.009
    # first trade uses 0.005 -> ok
    assert rm.can_open_trade(0.005)[0] is True
    rm.register_open_position(0.005)
    # second would exceed
    assert rm.can_open_trade(0.005)[0] is False
    assert rm.portfolio_heat() == 0.005


def test_broker_factory_paper():
    cfg = load_config("config.example.yaml")
    cfg.mode = "paper"
    risk = RiskManager(cfg.risk)
    broker = create_broker(cfg, risk)
    assert broker.connect() is True
    assert broker.get_account_info()["currency"] == cfg.risk.currency


def test_walk_forward_basic():
    from src.backtest.walk_forward import walk_forward

    cfg = load_config("config.example.yaml")
    data = {}
    for i, pair in enumerate(cfg.pairs[:1]):
        data[pair] = make_multi_tf_pair(n_entry=6000, seed=10 + i)
    res = walk_forward(data, cfg, train_days=30, test_days=10, step_days=10)
    assert "consistency" in res
    assert "aggregate_oos" in res
    assert res["consistency"]["n_windows"] >= 0