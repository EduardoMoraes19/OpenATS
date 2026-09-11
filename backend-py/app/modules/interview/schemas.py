from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, EmailStr, Field, model_validator

from app.db.models.enums import InterviewOutcome, MeetingProvider
from app.shared.schema import ApiModel, ApiOutModel, UtcDatetime
from app.shared.time import to_naive_utc


class CreateInterviewIn(ApiModel):
    """`POST /candidates/:id/interviews` - interviews.routes.ts's
    `createInterviewSchema`. Deliberately has none of the event/meeting
    fields update/schedule carry - `interviewerId` is required here."""

    stage_id: int | None = None
    scheduled_at: UtcDatetime | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    notes: str | None = None
    attendee_emails: list[EmailStr] | None = None
    interviewer_id: int


class UpdateInterviewIn(ApiModel):
    """`PATCH /interviews/:id` - interviews.routes.ts's `updateInterviewSchema`."""

    scheduled_at: UtcDatetime | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    notes: str | None = None
    outcome: InterviewOutcome | None = None
    status: Literal["pending_schedule", "scheduled", "completed", "cancelled"] | None = None
    event_name: str | None = Field(default=None, min_length=1)
    event_type: Literal["virtual", "onsite"] | None = None
    meeting_url: str | None = None
    meeting_provider: MeetingProvider | None = None
    interviewer_id: int | None = None
    location: str | None = None
    body_text: str | None = None
    attendee_emails: list[EmailStr] | None = None


def _must_be_future(value: UtcDatetime) -> UtcDatetime:
    if to_naive_utc(value) <= datetime.now(UTC).replace(tzinfo=None):
        raise ValueError("Each time slot must be a valid date in the future")
    return value


class TimeSlotIn(ApiModel):
    datetime: Annotated[UtcDatetime, AfterValidator(_must_be_future)]
    selected: bool = False


class ScheduleInterviewIn(ApiModel):
    """`POST /candidates/:id/schedule` - interviews.routes.ts's `scheduleSchema`.
    Unlike create/update, `eventName`/`eventType`/`interviewerId` are all
    required and slots are `{datetime, selected}` objects, not bare strings."""

    event_name: str = Field(min_length=1)
    event_type: Literal["virtual", "onsite"]
    meeting_url: str | None = None
    meeting_provider: MeetingProvider | None = None
    interviewer_id: int
    location: str | None = None
    body_text: str | None = None
    stage_id: int | None = None
    time_slots: list[TimeSlotIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_meeting_url_for_virtual_without_provider(self) -> ScheduleInterviewIn:
        if self.event_type == "virtual" and self.meeting_provider is None and not self.meeting_url:
            raise ValueError(
                "meeting_url is required for a virtual event unless a meeting_provider "
                "will auto-generate one"
            )
        return self


class InterviewOut(ApiOutModel):
    id: int
    candidate_id: int
    stage_id: int
    job_id: int
    event_name: str | None
    event_type: str | None
    meeting_url: str | None
    meeting_provider: MeetingProvider | None
    location: str | None
    body_text: str | None
    interviewer_id: int | None
    time_slots: list[dict] | None
    status: str
    outcome: InterviewOutcome | None
    public_token: str | None
    token_expires_at: UtcDatetime | None
    google_event_id: str | None
    provider_meeting_id: str | None
    scheduled_at: UtcDatetime | None
    duration_minutes: int | None
    notes: str | None
    created_by: int | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class PublicInterviewOut(ApiModel):
    """`GET /public/interview/:token` - public.routes.ts lines 162-225. Note
    this is a different, narrower field set than `InterviewOut`: no
    `location`/`durationMinutes` (candidates don't need them here), but it
    does surface `id`, `meetingUrl` and `tokenExpiresAt`, which the internal
    shape also has."""

    id: int
    event_name: str | None
    event_type: str | None
    meeting_url: str | None
    body_text: str | None
    time_slots: list[dict]
    status: str
    token_expires_at: UtcDatetime | None
    candidate_name: str
    job_title: str


class AllocatedSlotOut(ApiModel):
    """`GET /interviews/allocated-slots` - interviews.routes.ts returns an
    array of `{datetime, interviewerId}`, not bare datetimes, so the
    frontend can restrict the "already taken" check to the same interviewer."""

    datetime: UtcDatetime
    interviewer_id: int | None


class SelectSlotIn(ApiModel):
    """`PATCH /public/interview/:token/select` body - an index into the
    interview's stored `time_slots` array, not a raw datetime."""

    slot_index: int = Field(ge=0)


class FeedbackIn(ApiModel):
    content: str = Field(min_length=1)
    rating: int | None = Field(default=None, ge=1, le=5)


class FeedbackOut(ApiOutModel):
    id: int
    interview_id: int
    author_id: int
    content: str
    rating: int | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
