"""Shared helpers for the DB-backed allowed-origins allow-list
(`public_page_settings.allowed_origins`), used by both the dynamic CORS
middleware and the /public/* checkOrigins gate.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.base import session_scope
from app.db.models.page_settings import PublicPageSettings


def normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/")


async def get_allowed_origins() -> list[str]:
    async with session_scope() as db:
        result = await db.execute(select(PublicPageSettings.allowed_origins).limit(1))
        row = result.scalar_one_or_none()
        return row or []
