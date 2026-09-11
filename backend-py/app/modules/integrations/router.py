"""Authenticated integrations routes, equivalent to
backend/src/modules/integrations/integrations.routes.ts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.integrations.schemas import AuthorizeUrlOut, ConnectionStatusOut
from app.shared.auth.deps import get_current_user, require_manager
from app.shared.auth.verify_token import AuthenticatedUser
from app.shared.integrations import connection_service

router = APIRouter()


@router.get("/status", response_model=list[ConnectionStatusOut])
async def get_my_status(
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ConnectionStatusOut]:
    statuses = await connection_service.get_status(db, user.id)
    return [
        ConnectionStatusOut(
            provider=s.provider.value, connected=s.connected, account_email=s.account_email
        )
        for s in statuses
    ]


@router.get("/status/{user_id}", response_model=list[ConnectionStatusOut])
async def get_user_status(
    user_id: int,
    _: AuthenticatedUser = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectionStatusOut]:
    statuses = await connection_service.get_status(db, user_id)
    return [
        ConnectionStatusOut(
            provider=s.provider.value, connected=s.connected, account_email=s.account_email
        )
        for s in statuses
    ]


@router.get("/google/authorize-url", response_model=AuthorizeUrlOut)
async def get_google_authorize_url(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthorizeUrlOut:
    return AuthorizeUrlOut(url=connection_service.get_auth_url(user.id))


@router.delete("/google")
async def disconnect_google(
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    await connection_service.disconnect(db, user.id)
    return {"disconnected": True}
