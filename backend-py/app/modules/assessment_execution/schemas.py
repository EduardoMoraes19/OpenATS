from __future__ import annotations

from decimal import Decimal

from pydantic import Field, field_validator

from app.db.models.enums import AssessmentStatus
from app.shared.schema import ApiModel, ApiOutModel, UtcDatetime


class InviteCandidateIn(ApiModel):
    candidate_id: int
    assessment_id: int
    expiry_days: int = 7


class InviteCandidateOut(ApiModel):
    attempt_id: int
    token: str
    did_send_invite: bool


class AttemptOut(ApiOutModel):
    id: int
    candidate_id: int
    assessment_id: int
    status: AssessmentStatus
    expires_at: UtcDatetime
    started_at: UtcDatetime | None
    completed_at: UtcDatetime | None
    score_raw: Decimal | None
    score_total: Decimal | None
    score_percentage: Decimal | None
    passed: bool | None
    created_at: UtcDatetime
    updated_at: UtcDatetime



class CompleteAssessmentIn(ApiModel):
    auto_submit_reason: str | None = Field(default=None, max_length=500)

    @field_validator("auto_submit_reason")
    @classmethod
    def _trim(cls, v: str | None) -> str | None:
        if v is None:
            return v
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("String must contain at least 1 character(s)")
        return trimmed


class AnswerIn(ApiModel):
    question_id: int
    answer_text: str | None = None
    option_ids: list[int] = Field(default_factory=list)


class QuestionForCandidateOut(ApiModel):
    id: int
    title: str
    description: str | None
    question_type: str
    points: Decimal
    position: int
    options: list[dict] = Field(default_factory=list)


class AttemptDetailOut(ApiModel):
    attempt: AttemptOut
    questions: list[QuestionForCandidateOut]


class GradedAnswerOut(ApiModel):
    question_id: int
    answer_text: str | None
    selected_option_ids: list[int]
    correct_option_ids: list[int]
    points_earned: Decimal | None
    points_possible: Decimal


class AttemptResultsOut(ApiModel):
    attempt: AttemptOut
    answers: list[GradedAnswerOut]
