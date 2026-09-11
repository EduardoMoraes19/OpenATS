"""Equivalent to backend/src/modules/settings/page-settings.service.ts.

Single-row `public_page_settings` table driving both the dynamic CORS
allow-list (app/shared/middleware/cors.py) and the /public/* origin gate
(app/shared/middleware/allowed_origins.py).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.page_settings import PublicPageSettings


async def _get_or_create(db: AsyncSession) -> PublicPageSettings:
    result = await db.execute(select(PublicPageSettings).limit(1))
    row = result.scalar_one_or_none()
    if row is None:
        row = PublicPageSettings(allowed_origins=[])
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def get_allowed_origins(db: AsyncSession) -> list[str]:
    row = await _get_or_create(db)
    return row.allowed_origins


async def set_allowed_origins(db: AsyncSession, origins: list[str]) -> list[str]:
    row = await _get_or_create(db)
    row.allowed_origins = origins
    await db.commit()
    return row.allowed_origins
