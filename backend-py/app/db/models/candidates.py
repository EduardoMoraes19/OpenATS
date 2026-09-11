"""candidates and its satellite tables - equivalent to backend/src/db/schema/candidates.ts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import AssessmentStatus, CandidateStatus, CvAnalysisStatus, pg_enum
from app.db.models.mixins import TimestampsMixin

if TYPE_CHECKING:
    from app.db.models.jobs import Job
    from app.db.models.pipeline import JobPipelineStage


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("job_id", "email"),
        Index("idx_candidates_job_id", "job_id"),
        Index("idx_candidates_current_stage_id", "current_stage_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    resume_url: Mapped[str | None] = mapped_column(String(1000))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False)
    current_stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_pipeline_stages.id", ondelete="SET NULL")
    )
    status: Mapped[CandidateStatus] = mapped_column(
        pg_enum(CandidateStatus, "candidate_status"), nullable=False, default=CandidateStatus.active
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[Job] = relationship()
    current_stage: Mapped[JobPipelineStage | None] = relationship()
    cv_analysis: Mapped[CandidateCvAnalysis | None] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class CandidateStageHistory(Base):
    __tablename__ = "candidate_stage_history"
    __table_args__ = (
        Index("idx_candidate_stage_history_candidate_id", "candidate_id"),
        Index("idx_candidate_stage_history_stage_id", "stage_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    stage_id: Mapped[int] = mapped_column(
        ForeignKey("job_pipeline_stages.id", ondelete="RESTRICT"), nullable=False
    )
    moved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )


class CandidateCustomAnswer(Base):
    __tablename__ = "candidate_custom_answers"
    __table_args__ = (UniqueConstraint("candidate_id", "question_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("job_custom_questions.id", ondelete="CASCADE"), nullable=False
    )
    answer_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )


class CandidateCustomAnswerSelection(Base):
    __tablename__ = "candidate_custom_answer_selections"
    __table_args__ = (UniqueConstraint("candidate_id", "question_id", "option_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("job_custom_questions.id", ondelete="CASCADE"), nullable=False
    )
    option_id: Mapped[int] = mapped_column(
        ForeignKey("job_custom_question_options.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )


class CandidateAssessmentAttempt(Base, TimestampsMixin):
    __tablename__ = "candidate_assessment_attempts"
    __table_args__ = (Index("idx_assessment_attempts_candidate_id", "candidate_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[AssessmentStatus] = mapped_column(
        pg_enum(AssessmentStatus, "assessment_status"), nullable=False, default=AssessmentStatus.pending
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    score_raw: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    score_total: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    score_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    passed: Mapped[bool | None] = mapped_column(Boolean)
    candidate_name_input: Mapped[str | None] = mapped_column(String(255))
    candidate_email_input: Mapped[str | None] = mapped_column(String(255))

    answers: Mapped[list[CandidateAssessmentAnswer]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class CandidateAssessmentAnswer(Base):
    __tablename__ = "candidate_assessment_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_assessment_attempts.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("assessment_questions.id", ondelete="CASCADE"), nullable=False
    )
    answer_text: Mapped[str | None] = mapped_column(Text)
    points_earned: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    attempt: Mapped[CandidateAssessmentAttempt] = relationship(back_populates="answers")
    selections: Mapped[list[CandidateAssessmentAnswerSelection]] = relationship(
        back_populates="answer", cascade="all, delete-orphan"
    )


class CandidateAssessmentAnswerSelection(Base):
    __tablename__ = "candidate_assessment_answer_selections"
    __table_args__ = (UniqueConstraint("answer_id", "option_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    answer_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_assessment_answers.id", ondelete="CASCADE"), nullable=False
    )
    option_id: Mapped[int] = mapped_column(
        ForeignKey("assessment_question_options.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    answer: Mapped[CandidateAssessmentAnswer] = relationship(back_populates="selections")


class CandidateCvAnalysis(Base, TimestampsMixin):
    __tablename__ = "candidate_cv_analysis"
    __table_args__ = (UniqueConstraint("candidate_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    matched_skills: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    missing_skills: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    score_breakdown: Mapped[Any | None] = mapped_column(JSONB)
    ai_summary: Mapped[Any | None] = mapped_column(JSONB)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CvAnalysisStatus] = mapped_column(
        pg_enum(CvAnalysisStatus, "cv_analysis_status"), nullable=False, default=CvAnalysisStatus.pending
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped[Candidate] = relationship(back_populates="cv_analysis")
