"""checkOrigins equivalent for /public/* routes, equivalent to
middlewares/allowedOrigins.middleware.ts.

This is an app-level 403 gate, not CORS preflight: it reads the same
DB-backed allow-list as the dynamic CORS middleware, but fails open when the
list is empty or no origin can be determined at all.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.shared.origins import get_allowed_origins, normalize_origin


def _resolve_request_origin(request: Request) -> str | None:
    """Priority: x-openats-browser-origin -> Origin -> parsed Referer."""
    custom = request.headers.get("x-openats-browser-origin")
    if custom:
        return custom
    origin = request.headers.get("origin")
    if origin:
        return origin
    referer = request.headers.get("referer")
    if referer:
        # Reduce a full referer URL down to its origin (scheme://host[:port]).
        parts = referer.split("/")
        if len(parts) >= 3:
            return f"{parts[0]}//{parts[2]}"
    return None


async def check_origins(request: Request) -> None:
    allowed_origins = await get_allowed_origins()
    if not allowed_origins:
        return  # empty allow-list => allow all

    origin = _resolve_request_origin(request)
    if origin is None:
        return  # fail-open: no origin could be determined at all

    normalized = normalize_origin(origin)
    if not any(normalized == normalize_origin(candidate) for candidate in allowed_origins):
        raise HTTPException(status_code=403, detail="Origin not allowed")
