"""pipeline_stage_templates, job_pipeline_stages, job_hiring_team -
equivalent to backend/src/db/schema/pipeline.ts.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import StageType, pg_enum
from app.db.models.mixins import TimestampsMixin

if TYPE_CHECKING:
    from app.db.models.jobs import Job
    from app.db.models.users import User


class PipelineStageTemplate(Base, TimestampsMixin):
    """The global, seeded master list job creation clones from."""

    __tablename__ = "pipeline_stage_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_type: Mapped[StageType] = mapped_column(
        pg_enum(StageType, "stage_type"), nullable=False, default=StageType.screening
    )
    is_deletable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class JobPipelineStage(Base, TimestampsMixin):
    __tablename__ = "job_pipeline_stages"
    __table_args__ = (UniqueConstraint("job_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_type: Mapped[StageType] = mapped_column(
        pg_enum(StageType, "stage_type"), nullable=False, default=StageType.screening
    )
    source_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("pipeline_stage_templates.id", ondelete="SET NULL")
    )

    job: Mapped[Job] = relationship()


class JobHiringTeam(Base):
    __tablename__ = "job_hiring_team"
    __table_args__ = (
        UniqueConstraint("job_id", "user_id"),
        Index("idx_job_hiring_team_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship()
    user: Mapped[User] = relationship()
