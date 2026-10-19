"""API rate limiting and API-key scope enforcement.

Two gaps are closed here, both of which the schema already promised but nothing
implemented:

* ``AppApiKey.rate_limit_per_minute`` was stored and never read. A token-bucket
  limiter now enforces it, keyed on the API key (or the user, or the client IP for
  unauthenticated traffic), and every response carries the standard
  ``X-RateLimit-*`` headers plus ``Retry-After`` when it rejects.
* ``AppApiKey.scopes`` was written once and never checked. A key's scopes are now
  intersected with its owner's role rights, and a route that needs a right the key
  does not carry returns 403 rather than silently succeeding.

The limiter is in-process and thread-safe, which is correct for a single-node
deployment. A multi-node deployment would move the counters to Redis; the
interface would not change.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import sqlalchemy as sa
from fastapi import Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import PermissionDeniedError
from app.core.logging import get_logger
from app.models.app_users import AppApiKey, AppUser

log = get_logger(__name__)


@dataclass
class Bucket:
    """A sliding-window counter for one key."""

    limit: int
    window_seconds: int = 60
    hits: deque[float] = field(default_factory=deque)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, now: float, cost: int = 1) -> tuple[bool, int, float]:
        """Consume `cost` units. Returns `(allowed, remaining, retry_after_seconds)`."""
        with self.lock:
            cutoff = now - self.window_seconds
            while self.hits and self.hits[0] <= cutoff:
                self.hits.popleft()
            used = len(self.hits)
            if used + cost > self.limit:
                oldest = self.hits[0] if self.hits else now
                return False, 0, max(0.0, oldest + self.window_seconds - now)
            for _ in range(cost):
                self.hits.append(now)
            return True, max(0, self.limit - used - cost), 0.0

    def reset(self) -> None:
        with self.lock:
            self.hits.clear()


class RateLimiter:
    """In-process sliding-window limiter with a bounded number of tracked keys."""

    def __init__(self, max_keys: int = 10_000) -> None:
        self._buckets: OrderedDict[str, Bucket] = OrderedDict()
        self._lock = threading.Lock()
        self.max_keys = max_keys

    def bucket(self, key: str, limit: int) -> Bucket:
        with self._lock:
            existing = self._buckets.get(key)
            if existing is None or existing.limit != limit:
                existing = Bucket(limit=limit)
                self._buckets[key] = existing
                # Evict the least recently used key so a burst of distinct client
                # addresses cannot grow the map without bound.
                while len(self._buckets) > self.max_keys:
                    self._buckets.popitem(last=False)
            else:
                self._buckets.move_to_end(key)
            return existing

    def check(self, key: str, limit: int, cost: int = 1) -> tuple[bool, int, float]:
        now = time.monotonic()
        return self.bucket(key, limit).allow(now, cost)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            elif key in self._buckets:
                self._buckets[key].reset()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"tracked_keys": len(self._buckets), "max_keys": self.max_keys}


#: Process-wide limiter.
limiter = RateLimiter()


# --------------------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------------------
def client_ip(request: Request) -> str:
    """Best-effort client address, honouring one layer of reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def identify(session: Session, request: Request) -> tuple[str, int, AppApiKey | None, AppUser | None]:
    """Work out which bucket a request belongs to, and whether it is scoped.

    Returns `(bucket_key, limit, api_key_row_or_None, user_or_None)`. The caller
    already authenticated, so this only re-reads the token to find the key row.
    """
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    limit = settings.api_rate_limit_per_minute

    if token.startswith("pip_"):
        from app.api.security import hash_api_key

        row = (
            session.execute(sa.select(AppApiKey).where(AppApiKey.hashed_key == hash_api_key(token)))
            .scalars()
            .first()
        )
        if row is not None:
            per_key = int(row.rate_limit_per_minute or limit)
            return f"key:{row.key_id}", per_key, row, None
        return f"key:{hash_api_key(token)[:16]}", limit, None, None

    # A session token: budget per user when we can identify one, otherwise per IP.
    user_id = request.scope.get("user_id")
    if user_id:
        return f"user:{user_id}", limit, None, None
    return f"ip:{client_ip(request)}", limit, None, None


# --------------------------------------------------------------------------------------
# Scopes
# --------------------------------------------------------------------------------------
def effective_scopes(key: AppApiKey, owner: AppUser | None) -> set[str]:
    """Scopes a request may exercise: the key's list, capped by the owner's role."""
    from app.api.security import ROLE_RIGHTS

    role_rights = ROLE_RIGHTS.get(owner.role if owner else "viewer", set())
    granted = set(key.scopes or [])
    # An empty or missing list means "whatever the owner can do", which keeps keys
    # created before scopes existed working.
    return (granted & role_rights) if granted else set(role_rights)


def enforce_scope(key: AppApiKey | None, owner: AppUser | None, required: str | None) -> None:
    if key is None or not required:
        return
    granted = effective_scopes(key, owner)
    if required not in granted:
        raise PermissionDeniedError(
            f"this API key does not carry the '{required}' scope",
            details={"required_scope": required, "granted_scopes": sorted(granted)},
        )


# --------------------------------------------------------------------------------------
# Middleware
# --------------------------------------------------------------------------------------
#: Paths that must always answer, even when the caller is over budget.
EXEMPT_PATHS = frozenset(
    {
        "/api/v1/health",
        "/api/v1/health/ready",
        "/api/v1/meta",
        "/api/v1/meta/features",
        "/api/v1/meta/tables",
        "/api/v1/version",
        "/api/v1/ping",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/demo-accounts",
    }
)


async def rate_limit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Sliding-window rate limiting with standard `X-RateLimit-*` headers."""
    from fastapi.responses import JSONResponse

    from app.core.db import read_session

    path = request.url.path
    if not settings.rate_limit_enabled or path in EXEMPT_PATHS:
        return await call_next(request)

    try:
        with read_session() as session:
            bucket_key, limit, key_row, user_row = identify(session, request)
    except Exception as exc:  # noqa: BLE001 - never block a request because of the limiter
        log.debug("rate limiter could not identify the caller: %s", exc)
        return await call_next(request)

    allowed, remaining, retry_after = limiter.check(bucket_key, limit)
    if not allowed:
        retry = max(1, int(retry_after) or 1)
        return JSONResponse(
            status_code=429,
            headers={
                "Retry-After": str(retry),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(retry),
            },
            content={
                "error": "rate_limited",
                "message": f"rate limit of {limit} requests/minute exceeded",
                "details": {"limit": limit, "retry_after_seconds": retry, "scope": bucket_key.split(":")[0]},
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
    return response


def api_key_summary(session: Session, key_id: int) -> dict[str, object]:
    """Usage summary for one key, used by the Account screen."""
    row = session.get(AppApiKey, key_id)
    if row is None:
        return {}
    return {
        "key_id": row.key_id,
        "name": row.name,
        "prefix": row.prefix,
        "scopes": sorted(row.scopes or []),
        "rate_limit_per_minute": row.rate_limit_per_minute,
        "usage_count": row.usage_count,
        "last_used_at": row.last_used_at,
        "expires_at": row.expires_at,
        "is_active": row.is_active,
        "expired": bool(row.expires_at and row.expires_at < dt.datetime.now(dt.timezone.utc)),
    }


__all__ = [
    "Bucket",
    "EXEMPT_PATHS",
    "RateLimiter",
    "api_key_summary",
    "client_ip",
    "effective_scopes",
    "enforce_scope",
    "identify",
    "limiter",
    "rate_limit_middleware",
]
