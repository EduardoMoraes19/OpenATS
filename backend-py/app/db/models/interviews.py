"""candidate_interviews - equivalent to backend/src/db/schema/interviews.ts.

`status` and `event_type` are deliberately plain varchar in the source
schema (semi-open state machines), not Postgres enums - preserved as
String columns here, not "upgraded" to native enums.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import InterviewOutcome, MeetingProvider, pg_enum
from app.db.models.mixins import TimestampsMixin


class CandidateInterview(Base, TimestampsMixin):
    __tablename__ = "candidate_interviews"
    __table_args__ = (
        Index("idx_candidate_interviews_candidate_id", "candidate_id"),
        Index("idx_candidate_interviews_job_id", "job_id"),
        Index("idx_candidate_interviews_stage_id", "stage_id"),
        Index("idx_candidate_interviews_interviewer_id", "interviewer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    stage_id: Mapped[int] = mapped_column(
        ForeignKey("job_pipeline_stages.id", ondelete="RESTRICT"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False)

    event_name: Mapped[str | None] = mapped_column(String(255))
    event_type: Mapped[str | None] = mapped_column(String(20), default="virtual")
    meeting_url: Mapped[str | None] = mapped_column(String(1000))
    meeting_provider: Mapped[MeetingProvider | None] = mapped_column(
        pg_enum(MeetingProvider, "meeting_provider")
    )
    location: Mapped[str | None] = mapped_column(String(500))
    body_text: Mapped[str | None] = mapped_column(Text)
    interviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    time_slots: Mapped[Any | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_schedule")
    outcome: Mapped[InterviewOutcome | None] = mapped_column(
        pg_enum(InterviewOutcome, "interview_outcome"), default=InterviewOutcome.pending
    )
    public_token: Mapped[str | None] = mapped_column(String(100), unique=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    google_event_id: Mapped[str | None] = mapped_column(String(255))
    provider_meeting_id: Mapped[str | None] = mapped_column(String(255))

    # Legacy columns, superseded by time_slots/status but kept for parity.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
