"""FastAPI application for the Trading Guardian."""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import init_db
from backend.rate_limit import RateLimitMiddleware
from backend.routers import admin, auth, backtest, config, ohlc, risk, saved_configs, signals

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("trading_guardian")

app = FastAPI(
    title="Trading Guardian API",
    description="Paper-trading-only forex assistant. Not financial advice.",
    version="0.3.0",
)

# init db
init_db()

cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware)

app.include_router(auth.router, tags=["auth"])
app.include_router(backtest.router, tags=["backtest"])
app.include_router(signals.router, tags=["signals"])
app.include_router(risk.router, tags=["risk"])
app.include_router(config.router, tags=["config"])
app.include_router(saved_configs.router, tags=["saved_configs"])
app.include_router(admin.router, tags=["admin"])
app.include_router(ohlc.router, tags=["ohlc"])

logger.info("Trading Guardian API started")


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