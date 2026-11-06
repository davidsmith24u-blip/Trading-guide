"""OHLC data endpoint for charting."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user

from backend.config_store import load
from src.data.provider import from_yfinance

router = APIRouter()


@router.get("/ohlc")
def get_ohlc(pair: str = "EURUSD", period: str = "5d", interval: str = "15m", current_user=Depends(get_current_user)):
    try:
        df = from_yfinance(pair, period=period, interval=interval)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if df.empty:
        raise HTTPException(status_code=404, detail="no data")
    out = []
    for ts, row in df.iterrows():
        out.append(
            {
                "timestamp": str(ts),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    return {"pair": pair, "interval": interval, "bars": out}