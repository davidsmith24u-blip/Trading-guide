"""FastAPI application for the Trading Guardian."""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Callable

# Load .env for local development (no-op in production where env is injected).
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.db import init_db
from backend.rate_limit import RateLimitMiddleware
from backend.routers import admin, auth, backtest, config, ohlc, risk, saved_configs, signals

# ---- environment validation ----
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
SECRET_KEY = os.getenv("SECRET_KEY", "")
if ENVIRONMENT == "production" and (not SECRET_KEY or SECRET_KEY.startswith("dev-")):
    raise RuntimeError("SECRET_KEY must be set to a strong value in production")
if not SECRET_KEY:
    SECRET_KEY = "dev-secret-change-me-in-production"
os.environ.setdefault("SECRET_KEY", SECRET_KEY)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("trading_guardian")

app = FastAPI(
    title="Trading Guardian API",
    description="Paper-trading-only forex assistant. Not financial advice.",
    version="0.4.0",
)

# ---- database ----
init_db()

# ---- CORS ----
cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8501").split(",") if o.strip()]
allow_credentials = True
if cors_origins == ["*"]:
    allow_credentials = False
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- rate limiting ----
app.add_middleware(RateLimitMiddleware)


# ---- request logging ----
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        start = time.time()
        response = await call_next(request)
        duration = (time.time() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1f ms) client=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration,
            request.client.host if request.client else "-",
        )
        return response


app.add_middleware(RequestLoggingMiddleware)

# ---- routers ----
app.include_router(auth.router, tags=["auth"])
app.include_router(backtest.router, tags=["backtest"])
app.include_router(signals.router, tags=["signals"])
app.include_router(risk.router, tags=["risk"])
app.include_router(config.router, tags=["config"])
app.include_router(saved_configs.router, tags=["saved_configs"])
app.include_router(admin.router, tags=["admin"])
app.include_router(ohlc.router, tags=["ohlc"])

logger.info("Trading Guardian API started (env=%s)", ENVIRONMENT)


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
    return {"status": "ok", "environment": ENVIRONMENT}