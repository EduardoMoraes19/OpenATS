"""interview_feedback - equivalent to backend/src/db/schema/interview-feedback.ts."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import TimestampsMixin


class InterviewFeedback(Base, TimestampsMixin):
    __tablename__ = "interview_feedback"
    __table_args__ = (
        Index("idx_interview_feedback_interview_id", "interview_id"),
        Index("idx_interview_feedback_author_id", "author_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_interviews.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer)
