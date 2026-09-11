"""Equivalent to backend/src/modules/settings/settings.routes.ts."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.settings import service
from app.modules.settings.schemas import AllowedOriginsIn, AllowedOriginsOut
from app.shared.auth.deps import require_manager

router = APIRouter(dependencies=[Depends(require_manager)])


@router.get("/allowed-origins", response_model=AllowedOriginsOut)
async def get_allowed_origins(db: AsyncSession = Depends(get_db)) -> AllowedOriginsOut:
    origins = await service.get_allowed_origins(db)
    return AllowedOriginsOut(origins=origins)


@router.put("/allowed-origins", response_model=AllowedOriginsOut)
async def set_allowed_origins(body: AllowedOriginsIn, db: AsyncSession = Depends(get_db)) -> AllowedOriginsOut:
    origins = await service.set_allowed_origins(db, body.origins)
    return AllowedOriginsOut(origins=origins)
