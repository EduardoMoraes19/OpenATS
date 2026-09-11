from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.db.models.enums import EmploymentType, OfferStatus
from app.modules.candidate.schemas import CandidateOut
from app.modules.company.schemas import DepartmentOut
from app.modules.job.schemas import JobOut
from app.modules.pipeline.schemas import PipelineStageOut
from app.modules.template.schemas import TemplateOut
from app.shared.schema import ApiModel, ApiOutModel, UtcDatetime


class OfferInputIn(ApiModel):
    candidate_id: int
    job_id: int
    template_id: int | None = None
    salary: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    employment_type: EmploymentType | None = None
    start_date: date | None = None
    reporting_manager: str | None = None
    benefits: str | None = None
    offer_letter_html: str | None = None


class OfferUpdateIn(ApiModel):
    template_id: int | None = None
    salary: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    employment_type: EmploymentType | None = None
    start_date: date | None = None
    reporting_manager: str | None = None
    benefits: str | None = None
    offer_letter_html: str | None = None
    status: OfferStatus | None = None


class OfferOut(ApiOutModel):
    id: int
    candidate_id: int
    job_id: int
    template_id: int | None
    status: OfferStatus
    salary: Decimal | None
    currency: str | None
    employment_type: EmploymentType | None
    start_date: date | None
    reporting_manager: str | None
    benefits: str | None
    offer_letter_html: str | None
    review_token: str | None
    sent_at: UtcDatetime | None
    viewed_at: UtcDatetime | None
    accepted_at: UtcDatetime | None
    declined_at: UtcDatetime | None
    created_by: int
    created_at: UtcDatetime
    updated_at: UtcDatetime



class OfferCandidateOut(CandidateOut):
    current_stage: PipelineStageOut | None = None


class OfferJobOut(JobOut):
    department: DepartmentOut | None = None


class OfferDetailOut(OfferOut):
    """offer.service.ts's `getById`: candidate/job/template embedded one
    level deep, with no further nesting on candidate/job."""

    candidate: CandidateOut | None = None
    job: JobOut | None = None
    template: TemplateOut | None = None


class OfferListItemOut(OfferOut):
    """offer.service.ts's `getAllDetails`/`getPaginated`: same embedding as
    `OfferDetailOut`, but the candidate also carries its current stage and
    the job also carries its department - the extra level `getById` omits."""

    candidate: OfferCandidateOut | None = None
    job: OfferJobOut | None = None
    template: TemplateOut | None = None


class PublicOfferOut(ApiModel):
    candidate_name: str
    job_title: str
    salary: Decimal | None
    currency: str | None
    employment_type: EmploymentType | None
    start_date: date | None
    reporting_manager: str | None
    benefits: str | None
    offer_letter_html: str | None
    status: OfferStatus
