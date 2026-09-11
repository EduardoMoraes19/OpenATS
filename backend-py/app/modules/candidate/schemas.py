from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import EmailStr, Field

from app.db.models.enums import (
    CandidateActivityType,
    CandidateStatus,
    CvAnalysisStatus,
    InterviewOutcome,
    StageType,
)
from app.modules.pipeline.schemas import PipelineStageOut
from app.shared.schema import ApiModel, ApiOutModel, UtcDatetime


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
    applied_at: UtcDatetime
    updated_at: UtcDatetime



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


# --- candidate.service.ts's getById composition (GET /candidates/:id) ---
#
# Deliberately NOT importing OfferOut from app.modules.offer.schemas here:
# that module already imports CandidateOut from this file (to embed the
# candidate on an offer), so importing back would be a circular import.
# The `offer` field below is built as a plain dict by the router instead
# (via OfferOut.model_validate(...).model_dump(by_alias=True)), matching
# how offer/router.py already builds nested responses without a shared
# Pydantic type.


class CandidateAnswerOut(ApiModel):
    id: int
    candidate_id: int
    question_id: int
    answer_text: str | None
    created_at: UtcDatetime
    question_title: str | None


class CandidateAnswerSelectionOut(ApiModel):
    id: int
    candidate_id: int
    question_id: int
    option_id: int
    created_at: UtcDatetime
    question_title: str | None
    option_label: str | None


class CandidateStageHistoryOut(ApiOutModel):
    id: int
    candidate_id: int
    stage_id: int
    moved_by: int | None
    moved_at: UtcDatetime


class CandidateCvAnalysisOut(ApiModel):
    """Note the narrower field set vs the `candidate_cv_analysis` table -
    candidate.service.ts's getById does not surface `id`/`candidateId`/
    `jobId`/`extractedText`/`createdAt` here, only these 8 fields."""

    status: CvAnalysisStatus
    match_score: Decimal | None
    matched_skills: list[str] | None
    missing_skills: list[str] | None
    score_breakdown: Any | None
    ai_summary: Any | None
    error_message: str | None
    updated_at: UtcDatetime


class CandidateInterviewSummaryOut(ApiModel):
    """The interview shape embedded in candidate.getById - narrower than
    interview/schemas.py's InterviewOut (no location/meetingProvider/
    tokenExpiresAt/providerMeetingId/interviewerId/notes... wait, notes IS
    included), but adds `stageType` (joined from the interview's stage),
    which InterviewOut does not carry."""

    id: int
    candidate_id: int
    stage_id: int
    job_id: int
    scheduled_at: UtcDatetime | None
    duration_minutes: int | None
    notes: str | None
    outcome: InterviewOutcome | None
    status: str
    event_name: str | None
    event_type: str | None
    meeting_url: str | None
    body_text: str | None
    time_slots: list[dict] | None
    public_token: str | None
    google_event_id: str | None
    created_by: int | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    stage_type: StageType | None


class CandidateActivityOut(ApiModel):
    id: int
    candidate_id: int
    job_id: int
    offer_id: int | None
    stage_id: int | None
    actor_id: int | None
    event_type: CandidateActivityType
    metadata: Any | None
    created_at: UtcDatetime
    stage: PipelineStageOut | None
