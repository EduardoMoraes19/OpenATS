"""Equivalent to the zod schemas in backend/src/modules/job/job.routes.ts."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from app.db.models.enums import EmploymentType, JobStatus, PayFrequency, SalaryType
from app.shared.schema import ApiModel, ApiOutModel, UtcDatetime


class JobBaseIn(ApiModel):
    title: str = Field(min_length=1, max_length=255)
    department_id: int
    employment_type: EmploymentType
    location: str | None = None
    description: str | None = None
    skills: list[str] = Field(default_factory=list)
    salary_type: SalaryType | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    pay_frequency: PayFrequency | None = None
    salary_fixed: Decimal | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    status: JobStatus = JobStatus.draft

    @model_validator(mode="after")
    def _validate_salary(self) -> JobBaseIn:
        if self.salary_type is not None and (self.currency is None or self.pay_frequency is None):
            raise ValueError("currency and pay_frequency are required when salary_type is set")
        if self.salary_type == SalaryType.range:
            if self.salary_min is None or self.salary_max is None:
                raise ValueError("salary_min and salary_max are required for a range salary")
            if self.salary_max < self.salary_min:
                raise ValueError("salary_max must be >= salary_min")
        if self.salary_type == SalaryType.fixed and self.salary_fixed is None:
            raise ValueError("salary_fixed is required for a fixed salary")
        return self


class CreateJobIn(JobBaseIn):
    pass


class UpdateJobIn(JobBaseIn):
    pass


class JobSkillOut(ApiOutModel):
    skill: str



class JobOut(ApiOutModel):
    id: int
    slug: str
    title: str
    department_id: int
    employment_type: EmploymentType
    location: str | None
    description: str | None
    salary_type: SalaryType | None
    currency: str | None
    pay_frequency: PayFrequency | None
    salary_fixed: Decimal | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    status: JobStatus
    application_email_template_id: int | None
    created_by: int
    created_at: UtcDatetime
    updated_at: UtcDatetime



class JobListItemOut(JobOut):
    skills: list[str] = Field(default_factory=list)


class JobAssessmentAttachmentIn(ApiModel):
    assessment_id: int
    trigger_stage_id: int


class JobAssessmentAttachmentOut(ApiOutModel):
    id: int
    job_id: int
    assessment_id: int
    trigger_stage_id: int
    created_at: UtcDatetime



class PublicJobOut(ApiOutModel):
    """`getPublicJobById` in job.controller.ts: the full internal job row
    minus hiringTeam/pipelineStages/createdBy - unlike the careers list
    below, this does NOT curate down to a minimal shape."""

    id: int
    slug: str
    title: str
    department_id: int
    employment_type: EmploymentType
    location: str | None
    description: str | None
    salary_type: SalaryType | None
    currency: str | None
    pay_frequency: PayFrequency | None
    salary_fixed: Decimal | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    status: JobStatus
    application_email_template_id: int | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    skills: list[str] = Field(default_factory=list)


class PublicJobListItemOut(ApiOutModel):
    """`listPublishedForCareers` in job.service.ts: a deliberately minimal,
    curated shape for the public careers index - it does not leak
    departmentId, description, or the salary breakdown, and joins in the
    department's name instead of its id."""

    id: int
    slug: str
    title: str
    employment_type: EmploymentType
    location: str | None
    department_name: str
    created_at: UtcDatetime

