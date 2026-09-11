"""Google OAuth callback, equivalent to backend/src/modules/integrations/oauth.routes.ts.

Mounted at /oauth (not /api) with no auth dependency at all - Google
redirects the user's browser here directly, with no app credentials
attached, so this must be publicly reachable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.logging import get_logger
from app.settings import settings
from app.shared.integrations import connection_service

logger = get_logger(__name__)

oauth_router = APIRouter()


@oauth_router.get("/google/callback")
async def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not code or not state:
        return RedirectResponse(f"{settings.frontend_url}/settings/integrations?error=google_meet")

    try:
        await connection_service.handle_callback(db, code, state)
    except Exception:  # noqa: BLE001
        logger.exception("google oauth callback failed")
        return RedirectResponse(f"{settings.frontend_url}/settings/integrations?error=google_meet")

    return RedirectResponse(
        f"{settings.frontend_url}/settings/integrations?connected=google_meet"
    )
