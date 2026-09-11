"""offers - equivalent to backend/src/db/schema/offers.ts."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import EmploymentType, OfferStatus, pg_enum
from app.db.models.mixins import TimestampsMixin


class Offer(Base, TimestampsMixin):
    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id"),
        Index("idx_offers_job_id", "job_id"),
        Index("idx_offers_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    status: Mapped[OfferStatus] = mapped_column(
        pg_enum(OfferStatus, "offer_status"), nullable=False, default=OfferStatus.draft
    )
    salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    employment_type: Mapped[EmploymentType | None] = mapped_column(
        pg_enum(EmploymentType, "employment_type")
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    reporting_manager: Mapped[str | None] = mapped_column(String(255))
    benefits: Mapped[str | None] = mapped_column(Text)
    offer_letter_html: Mapped[str | None] = mapped_column(Text)
    review_token: Mapped[str | None] = mapped_column(String(100), unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
