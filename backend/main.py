"""FastAPI application for the Trading Guardian."""

from __future__ import annotations

import os
import sys

# make project root importable when running `uvicorn backend.main:app`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import backtest, config, ohlc, risk, signals

app = FastAPI(
    title="Trading Guardian API",
    description="Paper-trading-only forex assistant. Not financial advice.",
    version="0.2.0",
)

# Permissive CORS for local development / Streamlit frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backtest.router, tags=["backtest"])
app.include_router(signals.router, tags=["signals"])
app.include_router(risk.router, tags=["risk"])
app.include_router(config.router, tags=["config"])
app.include_router(ohlc.router, tags=["ohlc"])


@app.get("/")
def root():
    return {
        "name": "Trading Guardian API",
        "paper_trading_only": True,
        "warning": "Paper trading only. Not financial advice.",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}