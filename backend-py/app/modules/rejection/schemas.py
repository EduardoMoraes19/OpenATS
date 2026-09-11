from __future__ import annotations

from pydantic import Field, model_validator

from app.db.models.enums import RejectionEmailStatus
from app.shared.schema import ApiModel, ApiOutModel, UtcDatetime


class RejectCandidateIn(ApiModel):
    reason: str = Field(min_length=1, max_length=255)
    internal_note: str | None = Field(default=None, max_length=2000)
    template_id: int | None = None
    email_status: RejectionEmailStatus = RejectionEmailStatus.not_sent

    @model_validator(mode="after")
    def _validate_send_requires_template(self) -> RejectCandidateIn:
        if self.email_status == RejectionEmailStatus.sent and self.template_id is None:
            raise ValueError("template_id is required when email_status is 'sent'")
        return self


class RejectionOut(ApiOutModel):
    id: int
    candidate_id: int
    job_id: int
    from_stage_id: int | None
    rejected_by: int | None
    reason: str | None
    internal_note: str | None
    template_id: int | None
    email_status: RejectionEmailStatus
    sent_at: UtcDatetime | None
    rejected_at: UtcDatetime

