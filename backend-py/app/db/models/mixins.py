"""Shared column mixins to avoid repeating the same declarations across models.

All timestamps in the source Drizzle schema are `timestamp` WITHOUT time zone
(no column opts into `withTimezone`) - DateTime(timezone=False) everywhere
here matches that exactly.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )


class TimestampsMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
