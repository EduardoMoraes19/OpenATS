from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.db.models.enums import CandidateStatus
from app.shared.schema import ApiModel, ApiOutModel


class CustomAnswerIn(ApiModel):
    question_id: int
    answer_text: str | None = None
    option_ids: list[int] = Field(default_factory=list)


class CandidateApplyIn(ApiModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = None
    resume_url: str | None = None
    custom_answers: list[CustomAnswerIn] = Field(default_factory=list)


class UpdateCandidateBasicIn(ApiModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = None


class MoveStageIn(ApiModel):
    new_stage_id: int


class BulkDeleteCandidatesIn(ApiModel):
    job_id: int | None = None
    stage_id: int | None = None
    search: str | None = None
    status: CandidateStatus | None = None


class CandidateOut(ApiOutModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone: str | None
    resume_url: str | None
    job_id: int
    current_stage_id: int | None
    status: CandidateStatus
    applied_at: datetime
    updated_at: datetime



class CandidateListItemOut(CandidateOut):
    """The list endpoint's row shape: candidate.service.ts's `getAll` joins
    in the current stage's name and the job's title alongside the
    candidate's own columns - the single-candidate endpoints (`getById`,
    `apply`, etc.) do not carry these two extra fields."""

    stage_name: str | None = None
    job_title: str | None = None


class StageAutomationFlags(ApiModel):
    """Mirrors candidate.service.ts's StageAutomationFlags exactly: the only
    automation ever reported to the client is the assessment invite outcome.
    Offer-draft creation is never surfaced in the response."""

    assessment_invite: Literal["sent", "skipped_active_invite"] | None = None
