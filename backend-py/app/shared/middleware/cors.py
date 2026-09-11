"""Dynamic, DB-backed CORS middleware for /api/* and friends, equivalent to
the `cors(...)` callback in backend/src/app.ts.

FastAPI's built-in CORSMiddleware only accepts a static origin list; the
allow-list here is DB-backed (`public_page_settings.allowed_origins`), so a
custom Starlette middleware is required. FRONTEND_URL is checked first as a
fast-path that never touches the database.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.settings import settings
from app.shared.origins import get_allowed_origins, normalize_origin


class DynamicCorsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        origin = request.headers.get("origin")
        origin_allowed = origin is None  # no Origin header (server-to-server, curl) => allowed

        if origin is not None:
            normalized = normalize_origin(origin)
            if normalized == normalize_origin(settings.frontend_url):
                origin_allowed = True
            else:
                allowed_origins = await get_allowed_origins()
                origin_allowed = any(
                    normalized == normalize_origin(candidate) for candidate in allowed_origins
                )

        if request.method == "OPTIONS":
            response = Response(status_code=204)
        else:
            response = await call_next(request)

        if origin is not None and origin_allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
        if request.method == "OPTIONS":
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            requested_headers = request.headers.get("access-control-request-headers")
            if requested_headers:
                response.headers["Access-Control-Allow-Headers"] = requested_headers

        return response
