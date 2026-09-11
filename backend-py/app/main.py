"""FastAPI app factory + ASGI mount of python-socketio, equivalent to
backend/src/app.ts + backend/src/server.ts.

Socket.IO and HTTP share the same ASGI app/port here exactly as they share
one http.Server in the TS code. `asgi_app` (not `fastapi_app`) is what
uvicorn should serve: `uvicorn app.main:asgi_app`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.base import engine
from app.logging import get_logger
from app.routes.api_router import api_router
from app.routes.public_router import public_router
from app.settings import settings
from app.shared.middleware.cors import DynamicCorsMiddleware
from app.shared.middleware.envelope import EnvelopeMiddleware
from app.shared.middleware.error_handlers import register_error_handlers
from app.shared.rate_limit import redis_client
from app.sockets.events import start_cv_analysis_bridge, stop_cv_analysis_bridge
from app.sockets.server import sio

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await start_cv_analysis_bridge()
    logger.info("openats api starting on port %s", settings.port)
    yield
    await stop_cv_analysis_bridge()


fastapi_app = FastAPI(title="OpenATS API", lifespan=_lifespan)
fastapi_app.add_middleware(EnvelopeMiddleware)
fastapi_app.add_middleware(DynamicCorsMiddleware)
register_error_handlers(fastapi_app)

fastapi_app.include_router(api_router, prefix="/api")
fastapi_app.include_router(public_router, prefix="/public")

# /oauth/google/callback is mounted outside /api on purpose - Google redirects
# the browser here without any app auth header, so it must not require auth.
from app.modules.integrations.oauth_router import oauth_router  # noqa: E402

fastapi_app.include_router(oauth_router, prefix="/oauth")


@fastapi_app.get("/health")
async def health() -> JSONResponse:
    checks = {"db": "ok", "redis": "ok"}
    healthy = True

    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
    except Exception:  # noqa: BLE001
        checks["db"] = "error"
        healthy = False

    try:
        pong = await redis_client.ping()
        if not pong:
            raise RuntimeError("no pong")
    except Exception:  # noqa: BLE001
        checks["redis"] = "error"
        healthy = False

    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )


# Socket.IO wraps the FastAPI app so both HTTP and WS traffic share one port,
# matching http.createServer(app) + socketService.initialize(server) today.
asgi_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
