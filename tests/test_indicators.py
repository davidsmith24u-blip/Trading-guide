import numpy as np
import pandas as pd

from src.indicators import ema, atr, rsi, adx, pip_size


def _df(n=100):
    rng = np.random.default_rng(0)
    close = 1.1 + np.cumsum(rng.normal(0, 0.001, n))
    high = close + 0.001
    low = close - 0.001
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close})


def test_ema_length():
    s = pd.Series(np.arange(1, 11, dtype=float))
    out = ema(s, 3)
    assert len(out) == 10
    assert out.dropna().iloc[-1] > out.dropna().iloc[0]


def test_atr_positive():
    df = _df(50)
    a = atr(df, 14)
    assert (a.dropna() > 0).all()


def test_rsi_range():
    df = _df(50)
    r = rsi(df["close"], 14)
    assert r.dropna().between(0, 100).all()


def test_adx_range():
    df = _df(50)
    a = adx(df, 14)
    assert a.dropna().between(0, 100).all()


def test_pip_size():
    assert pip_size("EURUSD") == 0.0001
    assert pip_size("USDJPY") == 0.01
    assert pip_size("XAUUSD") == 0.01