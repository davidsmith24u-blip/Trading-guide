"""Simple in-memory rate limiter (per client IP)."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
WINDOW = 60.0
_buckets: dict[str, Deque[float]] = defaultdict(deque)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # /health is cheap; still counted but generous
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = _buckets[ip]
        # drop old entries
        while bucket and bucket[0] < now - WINDOW:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded, try again later"},
            )
        bucket.append(now)
        return await call_next(request)