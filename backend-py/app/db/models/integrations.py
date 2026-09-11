"""integration_connections - equivalent to backend/src/db/schema/integrations.ts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import MeetingProvider, pg_enum
from app.db.models.mixins import TimestampsMixin


class IntegrationConnection(Base, TimestampsMixin):
    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[MeetingProvider] = mapped_column(
        pg_enum(MeetingProvider, "meeting_provider"), nullable=False
    )
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    scopes: Mapped[Any | None] = mapped_column(JSONB)
    provider_account_email: Mapped[str | None] = mapped_column(String(255))
