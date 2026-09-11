"""jobs, job_skills - equivalent to backend/src/db/schema/jobs.ts.

The four CHECK constraints and both indexes are ported verbatim from
backend/drizzle/0000_powerful_trish_tilby.sql and 0027_gifted_tony_stark.sql.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import EmploymentType, JobStatus, PayFrequency, SalaryType, pg_enum
from app.db.models.mixins import TimestampsMixin

if TYPE_CHECKING:
    from app.db.models.company import Department


class Job(Base, TimestampsMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "salary_type != 'range' OR (salary_min IS NOT NULL AND salary_max IS NOT NULL)",
            name="chk_salary_range",
        ),
        CheckConstraint(
            "salary_type != 'fixed' OR salary_fixed IS NOT NULL",
            name="chk_salary_fixed",
        ),
        CheckConstraint(
            "salary_type IS NULL OR currency IS NOT NULL",
            name="chk_salary_currency",
        ),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_max >= salary_min",
            name="chk_salary_min_max",
        ),
        Index("idx_jobs_department_id", "department_id"),
        Index("idx_jobs_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    employment_type: Mapped[EmploymentType] = mapped_column(
        pg_enum(EmploymentType, "employment_type"), nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    salary_type: Mapped[SalaryType | None] = mapped_column(pg_enum(SalaryType, "salary_type"))
    currency: Mapped[str | None] = mapped_column(String(3))
    pay_frequency: Mapped[PayFrequency | None] = mapped_column(
        pg_enum(PayFrequency, "pay_frequency")
    )
    salary_fixed: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), nullable=False, default=JobStatus.draft
    )
    application_email_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    department: Mapped[Department] = relationship(back_populates="jobs")
    skills: Mapped[list[JobSkill]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    skill: Mapped[str] = mapped_column(String(100), nullable=False)

    job: Mapped[Job] = relationship(back_populates="skills")
