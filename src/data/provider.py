"""Data providers.

We support:
  - CSV files (offline, reproducible, great for backtests)
  - yfinance (optional, for quick experimentation)
  - A synthetic data generator so the skeleton runs out of the box.

All providers return a DataFrame with columns: open, high, low, close, volume
and a DatetimeIndex, sorted ascending.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


REQUIRED_COLS = ["open", "high", "low", "close"]


def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in REQUIRED_COLS:
        if c not in df.columns:
            raise ValueError(f"missing column: {c}")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    if not isinstance(df.index, pd.DatetimeIndex):
        # try common date columns
        for cand in ("date", "time", "datetime", "timestamp"):
            if cand in df.columns:
                df.index = pd.to_datetime(df[cand])
                df = df.drop(columns=[cand])
                break
        else:
            df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return validate_ohlcv(df)


def from_yfinance_range(pair: str, start: str, end: str, interval: str = "15m") -> pd.DataFrame:
    """Fetch via yfinance between start/end dates."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("yfinance not installed") from e
    ticker = pair
    if pair.endswith("USD") and len(pair) == 6 and pair not in ("XAUUSD",):
        ticker = pair[:3] + pair[3:] + "=X"
    df = yf.download(ticker, start=start, end=end, interval=interval, auto_adjust=True, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"no data for {pair}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    return validate_ohlcv(df)


def from_oanda(pair: str, granularity: str = "M15", count: int = 5000) -> pd.DataFrame:
    """Fetch candles from OANDA v20 (requires OANDA_API_TOKEN and OANDA_ACCOUNT_ID env)."""
    import os

    import requests

    token = os.getenv("OANDA_API_TOKEN")
    account = os.getenv("OANDA_ACCOUNT_ID")
    if not token:
        raise RuntimeError("OANDA_API_TOKEN not set")
    host = os.getenv("OANDA_HOST", "https://api-fxpractice.oanda.com")
    # OANDA instrument format EUR_USD
    instrument = pair[:3] + "_" + pair[3:]
    url = f"{host}/v3/instruments/{instrument}/candles"
    params = {"granularity": granularity, "count": count, "price": "MBA"}
    r = requests.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    candles = r.json().get("candles", [])
    rows = []
    for c in candles:
        if not c.get("complete", True):
            continue
        mid = c.get("mid", {})
        rows.append(
            {
                "timestamp": c["time"],
                "open": float(mid["o"]),
                "high": float(mid["h"]),
                "low": float(mid["l"]),
                "close": float(mid["c"]),
                "volume": float(c.get("volume", 0)),
            }
        )
    if not rows:
        raise RuntimeError("no oanda data")
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["timestamp"])
    df = df.drop(columns=["timestamp"])
    return validate_ohlcv(df)


def from_alpha_vantage(pair: str, interval: str = "15min", outputsize: str = "full") -> pd.DataFrame:
    """Fetch FX intraday from Alpha Vantage (requires ALPHA_VANTAGE_API_KEY env)."""
    import os

    import requests

    key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not key:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY not set")
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "FX_INTRADAY",
        "from_symbol": pair[:3],
        "to_symbol": pair[3:],
        "interval": interval,
        "outputsize": outputsize,
        "apikey": key,
        "datatype": "json",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    key_name = [k for k in data if "Time Series" in k]
    if not key_name:
        raise RuntimeError("alpha vantage error: " + str(data.get("Note") or data.get("Error Message")))
    ts = data[key_name[0]]
    rows = []
    for t, v in ts.items():
        rows.append(
            {
                "timestamp": t,
                "open": float(v["1. open"]),
                "high": float(v["2. high"]),
                "low": float(v["3. low"]),
                "close": float(v["4. close"]),
                "volume": 0.0,
            }
        )
    if not rows:
        raise RuntimeError("no alpha vantage data")
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["timestamp"])
    df = df.drop(columns=["timestamp"])
    df = df.sort_index()
    return validate_ohlcv(df)


def cache_path(key: str) -> str:
    import hashlib

    os.makedirs("data/cache", exist_ok=True)
    h = hashlib.md5(key.encode()).hexdigest()
    return os.path.join("data", "cache", f"{h}.pkl")


def cached_fetch(key: str, fetcher, *args, **kwargs):
    """Simple disk cache for data frames."""
    import pickle

    p = cache_path(key)
    if os.path.exists(p):
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    df = fetcher(*args, **kwargs)
    try:
        with open(p, "wb") as f:
            pickle.dump(df, f)
    except Exception:
        pass
    return df


def from_yfinance(pair: str, period: str = "60d", interval: str = "15m") -> pd.DataFrame:
    """Fetch via yfinance. Forex pairs use =X suffix; XAU uses GC=F-ish (approx)."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("yfinance not installed") from e
    ticker = pair
    if pair.endswith("USD") and len(pair) == 6 and pair not in ("XAUUSD",):
        ticker = pair[:3] + pair[3:] + "=X"
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
    if df.empty:
        raise RuntimeError(f"no data for {pair}")
    # flatten multiindex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    return validate_ohlcv(df)


def synthetic_ohlcv(
    n: int = 2000,
    start: str = "2024-01-01",
    freq: str = "15min",
    seed: int = 42,
    trend: float = 0.0003,    volatility: float = 0.0008,) -> pd.DataFrame:
    """Generate a random-walk OHLCV series with a gentle drift and regime changes.

    Useful so the skeleton runs end-to-end without network access.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n, freq=freq)
    # regime: switch drift sign every ~n/3 bars for clearer trends
    regime_len = max(n // 3, 10)
    drifts = np.array([trend] * n)
    for k in range(1, 4):
        drifts[k * regime_len:] = -trend if k % 2 else trend

    rets = drifts + rng.normal(0, volatility, n)
    close = 1.1000 * np.exp(np.cumsum(rets))
    # build OHLC around close
    high = close * (1 + np.abs(rng.normal(0, volatility * 0.5, n)))
    low = close * (1 - np.abs(rng.normal(0, volatility * 0.5, n)))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.integers(100, 1000, n).astype(float)
    df = pd.DataFrame(
        {"open": open_, "high": np.maximum(high, close), "low": np.minimum(low, close),
         "close": close, "volume": volume},
        index=idx,
    )
    # ensure high>=low and open within range
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)
    return df


def make_multi_tf_pair(
    n_entry: int = 4000,
    trend_factor: int = 8,
    seed: int = 42,
) -> dict:
    """Build trend + entry frames for one synthetic pair."""
    entry = synthetic_ohlcv(n=n_entry, freq="15min", seed=seed)
    trend = (
        entry.resample("4h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    return {"trend": trend, "entry": entry}