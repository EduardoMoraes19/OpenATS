"""public_page_settings - equivalent to backend/src/db/schema/page-settings.ts.

Single-row table driving both the dynamic CORS allow-list on /api/* and the
checkOrigins gate on /public/*. Read/update-only, no seed rows.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PublicPageSettings(Base):
    __tablename__ = "public_page_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    allowed_origins: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now()
    )
