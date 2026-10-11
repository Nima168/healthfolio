"""In-memory, per-client sliding-window rate limiter.

Works for a single backend process. Running several processes or servers needs a
shared store (e.g. Redis); the `RateLimiter` interface stays the same.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

from app.core.errors import ApiError


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # Behind a proxy, configure uvicorn --forwarded-allow-ips so this is the real client.
    return request.client.host if request.client else "unknown"


def check_user_rate_limit(name: str, user_id: object, limit: int, window_seconds: float) -> None:
    """Per-user limit, for endpoints that already know who the caller is."""
    if not limiter.allow(f"{name}:user:{user_id}", limit, window_seconds):
        raise ApiError(429)


def rate_limit(name: str, limit: int, window_seconds: float) -> Callable[[Request], None]:
    """FastAPI dependency factory: raises 429 when `limit` requests per window are exceeded."""

    def dependency(request: Request) -> None:
        if not limiter.allow(f"{name}:{client_ip(request)}", limit, window_seconds):
            raise ApiError(429)

    return dependency
