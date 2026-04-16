"""Rate limiter token-bucket en memoire (sera remplace par Redis en prod)."""
import time
from collections import defaultdict, deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings

settings = get_settings()


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._limit = settings.RATE_LIMIT_PER_MINUTE
        self._window = 60.0

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/v1/health"):
            return await call_next(request)

        client_id = request.client.host if request.client else "unknown"
        bucket = self._buckets[client_id]
        now = time.monotonic()
        cutoff = now - self._window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self._limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "limit": self._limit},
            )
        bucket.append(now)
        return await call_next(request)
