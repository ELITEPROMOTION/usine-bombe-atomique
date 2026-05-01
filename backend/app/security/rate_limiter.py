"""Rate limiter token-bucket in-memory.

Dependency FastAPI : `enforce_rate_limit(max_per_minute, scope_key)`.

Pour la prod multi-worker, remplacer par un Redis Lua script. Pour V9J
(stopgap securite), un dict in-memory par worker suffit pour bloquer le
flood naif.

Usage :
    @router.post("/sensitive")
    async def x(
        _: Annotated[None, Depends(enforce_rate_limit(max=30, window_s=60))],
    ): ...

Le scope est par defaut l'IP client (`request.client.host`). Personnalisable
via `scope_fn`.
"""
from __future__ import annotations

import collections
import hashlib
import logging
import time
from collections.abc import Callable
from typing import Final

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


MAX_BUCKETS: Final[int] = 4096          # eviction LRU si depasse
DEFAULT_MAX: Final[int] = 60
DEFAULT_WINDOW_S: Final[int] = 60


def _hash_scope(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class TokenBucketLimiter:
    """Bucket par scope, eviction LRU au-dela de MAX_BUCKETS."""

    def __init__(
        self,
        *,
        max_requests: int = DEFAULT_MAX,
        window_seconds: int = DEFAULT_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests >= 1 requis")
        if window_seconds < 1:
            raise ValueError("window_seconds >= 1 requis")
        self._max = max_requests
        self._window = window_seconds
        self._clock = clock
        self._buckets: collections.OrderedDict[str, collections.deque[float]] = (
            collections.OrderedDict()
        )

    def _evict_old(self, deque: collections.deque[float]) -> None:
        cutoff = self._clock() - self._window
        while deque and deque[0] < cutoff:
            deque.popleft()

    def _track(self, scope: str) -> collections.deque[float]:
        if scope in self._buckets:
            self._buckets.move_to_end(scope)
            return self._buckets[scope]
        if len(self._buckets) >= MAX_BUCKETS:
            self._buckets.popitem(last=False)
        bucket: collections.deque[float] = collections.deque(maxlen=self._max + 1)
        self._buckets[scope] = bucket
        return bucket

    def check(self, scope: str) -> tuple[bool, int]:
        """Retourne (allowed, remaining).

        Si allowed=False, on ne consomme pas le slot — l'appelant peut
        soit raise soit logger.
        """
        bucket = self._track(scope)
        self._evict_old(bucket)
        if len(bucket) >= self._max:
            return False, 0
        bucket.append(self._clock())
        remaining = self._max - len(bucket)
        return True, remaining

    @property
    def stats(self) -> dict[str, int]:
        return {scope: len(b) for scope, b in self._buckets.items()}

    def reset(self, scope: str | None = None) -> None:
        if scope is None:
            self._buckets.clear()
        else:
            self._buckets.pop(scope, None)


def _client_ip(request: Request) -> str:
    """Extrait l'IP client (X-Forwarded-For ou request.client.host)."""
    # Trust ONE proxy (nginx). Plus fin = a configurer ailleurs.
    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        return xff.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def enforce_rate_limit(
    *,
    max_requests: int = DEFAULT_MAX,
    window_seconds: int = DEFAULT_WINDOW_S,
    scope_fn: Callable[[Request], str] = _client_ip,
):
    """Factory de dependency FastAPI."""
    limiter = TokenBucketLimiter(
        max_requests=max_requests, window_seconds=window_seconds,
    )

    async def _dep(request: Request) -> None:
        scope = _hash_scope(scope_fn(request))
        allowed, remaining = limiter.check(scope)
        if not allowed:
            logger.warning(
                "rate_limit_blocked scope=%s path=%s",
                scope, request.url.path,
            )
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit : {max_requests}/{window_seconds}s",
                headers={"Retry-After": str(window_seconds)},
            )
        return None

    # Expose le limiter pour tests/inspection
    _dep.limiter = limiter   # type: ignore[attr-defined]
    return _dep
