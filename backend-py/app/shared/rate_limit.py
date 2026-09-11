"""Redis fixed-window rate limiter, equivalent to middlewares/rate-limit.middleware.ts
and the per-route limiters in public.routes.ts.

Not using slowapi: it is IP-first and fights the user-keyed requirement on
the authenticated API. Keying: `user_<id>` when request.state.user is set
(i.e. after get_current_user has run), else the client IP - matching
userKey()'s fallback to ipKeyGenerator().
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request
from redis.asyncio import Redis

from app.settings import settings

redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limit_key(request: Request, *, limiter_name: str) -> str:
    user = getattr(request.state, "user", None)
    identity = f"user_{user.id}" if user is not None else _client_ip(request)
    return f"ratelimit:{limiter_name}:{identity}"


def rate_limiter(*, name: str, limit: int, window_seconds: int, message: str) -> Callable:
    """FastAPI dependency factory for a named fixed-window limiter."""

    async def _dependency(request: Request) -> None:
        key = _rate_limit_key(request, limiter_name=name)
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, window_seconds)
        if current > limit:
            ttl = await redis_client.ttl(key)
            raise HTTPException(
                status_code=429,
                detail=message,
                headers={"Retry-After": str(max(ttl, 1))},
            )

    return _dependency


# Instances matching every limiter in the TS code exactly.
api_limiter = rate_limiter(
    name="api",
    limit=settings.rate_limit_api,
    window_seconds=15 * 60,
    message="Too many requests. Please slow down and try again.",
)
expensive_limiter = rate_limiter(
    name="expensive",
    limit=settings.rate_limit_expensive,
    window_seconds=15 * 60,
    message="Too many requests for this operation. Please try again later.",
)
apply_limiter = rate_limiter(
    name="apply",
    limit=5,
    window_seconds=15 * 60,
    message="Too many applications submitted. Please try again later.",
)
public_write_limiter = rate_limiter(
    name="public_write",
    limit=30,
    window_seconds=15 * 60,
    message="Too many requests. Please try again later.",
)
public_read_limiter = rate_limiter(
    name="public_read",
    limit=100,
    window_seconds=15 * 60,
    message="Too many requests. Please try again later.",
)
