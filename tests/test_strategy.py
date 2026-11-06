import numpy as np
import pandas as pd

from src.config import StrategyConfig
from src.indicators import add_indicators
from src.data.provider import synthetic_ohlcv, make_multi_tf_pair
from src.strategy import generate_signals, higher_trend


def test_higher_trend_values():
    df = synthetic_ohlcv(n=200, seed=1)
    from src.indicators import add_indicators as ai
    cfg = StrategyConfig()
    d = ai(df, cfg)
    t = higher_trend(d, cfg)
    assert set(t.unique()).issubset({-1, 0, 1})


def test_generate_signals_returns_list():
    frames = make_multi_tf_pair(n_entry=500, seed=7)
    from src.indicators import add_indicators
    cfg = StrategyConfig()
    trend_i = add_indicators(frames["trend"].copy(), cfg)
    entry_i = add_indicators(frames["entry"].copy(), cfg)
    sigs = generate_signals("EURUSD", trend_i, entry_i, cfg)
    assert isinstance(sigs, list)
    for s in sigs:
        assert s.side in (1, -1)
        assert s.stop_loss != s.entry
        assert s.take_profit != s.entry