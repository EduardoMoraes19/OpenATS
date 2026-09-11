"""candidate_rejections - equivalent to backend/src/db/schema/rejections.ts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import RejectionEmailStatus, pg_enum


class CandidateRejection(Base):
    __tablename__ = "candidate_rejections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False)
    from_stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_pipeline_stages.id", ondelete="SET NULL")
    )
    rejected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(String(255))
    internal_note: Mapped[str | None] = mapped_column(Text)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    email_status: Mapped[RejectionEmailStatus] = mapped_column(
        pg_enum(RejectionEmailStatus, "rejection_email_status"),
        nullable=False,
        default=RejectionEmailStatus.not_sent,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
