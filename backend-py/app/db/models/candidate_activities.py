"""candidate_activities - equivalent to backend/src/db/schema/candidate-activities.ts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import CandidateActivityType, pg_enum


class CandidateActivity(Base):
    __tablename__ = "candidate_activities"
    __table_args__ = (
        Index("idx_candidate_activities_candidate_id", "candidate_id"),
        Index("idx_candidate_activities_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id", ondelete="SET NULL"))
    stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_pipeline_stages.id", ondelete="SET NULL")
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[CandidateActivityType] = mapped_column(
        pg_enum(CandidateActivityType, "candidate_activity_type"), nullable=False
    )
    metadata_: Mapped[Any | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
