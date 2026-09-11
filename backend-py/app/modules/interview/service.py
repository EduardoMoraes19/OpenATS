"""Equivalent to backend/src/modules/interview/interview.service.ts."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidates import Candidate
from app.db.models.interview_feedback import InterviewFeedback
from app.db.models.interviews import CandidateInterview
from app.db.models.jobs import Job
from app.db.models.pipeline import JobPipelineStage
from app.db.models.users import User
from app.logging import get_logger
from app.settings import settings
from app.shared.integrations import connection_service
from app.shared.integrations.registry import get_provider_client
from app.shared.integrations.types import CreateMeetingInput
from app.shared.services import google_calendar_service, mail_service
from app.shared.time import to_naive_utc

logger = get_logger(__name__)

SCHEDULE_TOKEN_TTL_DAYS = 5


class SlotTakenError(Exception):
    """Raised by select_slot() when the chosen time collides with another
    interview - see _taken_times(). Carries no HTTP semantics itself; the
    public router translates it into the 409 SLOT_TAKEN response shape."""


async def _sync_calendar_create(
    db: AsyncSession, interview: CandidateInterview, *, attendee_emails: list[str] | None = None
) -> None:
    """Best-effort, non-fatal Google Calendar sync via the service account."""
    if interview.scheduled_at is None:
        return
    try:
        candidate = await db.get(Candidate, interview.candidate_id)
        job = await db.get(Job, interview.job_id)
        stage = await db.get(JobPipelineStage, interview.stage_id)
        assert candidate is not None and job is not None, "guaranteed by the FKs on candidate_interviews"
        event_input = google_calendar_service.CalendarEventInput(
            candidate_name=f"{candidate.first_name} {candidate.last_name}",
            job_title=job.title,
            stage_name=stage.name if stage else None,
            notes=interview.notes or interview.body_text,
            meeting_url=interview.meeting_url,
            scheduled_at=interview.scheduled_at,
            duration_minutes=interview.duration_minutes or 30,
            attendee_emails=attendee_emails,
        )
        interview.google_event_id = google_calendar_service.create_calendar_event(event_input)
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("failed to sync interview=%s to Google Calendar", interview.id)


async def _sync_calendar_update(db: AsyncSession, interview: CandidateInterview) -> None:
    if not interview.google_event_id or interview.scheduled_at is None:
        return
    try:
        candidate = await db.get(Candidate, interview.candidate_id)
        job = await db.get(Job, interview.job_id)
        assert candidate is not None and job is not None, "guaranteed by the FKs on candidate_interviews"
        event_input = google_calendar_service.CalendarEventInput(
            candidate_name=f"{candidate.first_name} {candidate.last_name}",
            job_title=job.title,
            stage_name=None,
            notes=None,
            meeting_url=interview.meeting_url,
            scheduled_at=interview.scheduled_at,
            duration_minutes=interview.duration_minutes or 30,
        )
        google_calendar_service.update_calendar_event(interview.google_event_id, event_input)
    except Exception:  # noqa: BLE001
        logger.exception("failed to re-sync interview=%s to Google Calendar", interview.id)


async def create_interview(db: AsyncSession, candidate_id: int, *, data: dict, created_by: int) -> CandidateInterview:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # attendee_emails is calendar-invite-only - candidate_interviews has no
    # such column, matching the TS schema.
    attendee_emails = data.pop("attendee_emails", None) or []
    # Falls back to the candidate's current stage, then a literal 0 - ported
    # verbatim from interview.service.ts's `input.stageId || row.currentStageId || 0`.
    data["stage_id"] = data.get("stage_id") or candidate.current_stage_id or 0
    data["duration_minutes"] = data.get("duration_minutes") or 30
    if data.get("scheduled_at") is not None:
        data["scheduled_at"] = to_naive_utc(data["scheduled_at"])

    interview = CandidateInterview(candidate_id=candidate_id, job_id=candidate.job_id, created_by=created_by, **data)
    if interview.scheduled_at is not None:
        interview.status = "scheduled"
    db.add(interview)
    await db.commit()
    await db.refresh(interview)

    await _sync_calendar_create(db, interview, attendee_emails=attendee_emails)

    if interview.scheduled_at is not None:
        try:
            job = await db.get(Job, candidate.job_id)
            assert job is not None, "guaranteed by the jobs.id FK on candidates"
            mail_service.send_interview_invite_email(
                to=candidate.email,
                candidate_name=f"{candidate.first_name} {candidate.last_name}",
                job_title=job.title,
                scheduled_at=interview.scheduled_at,
                meeting_url=interview.meeting_url,
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to send interview invite email for interview=%s", interview.id)

    return interview


async def list_for_candidate(db: AsyncSession, candidate_id: int) -> list[CandidateInterview]:
    result = await db.execute(
        select(CandidateInterview)
        .where(CandidateInterview.candidate_id == candidate_id)
        .order_by(CandidateInterview.created_at.desc())
    )
    return list(result.scalars().all())


async def list_interviews(
    db: AsyncSession, *, job_id: int | None, search: str | None, from_: datetime | None, to: datetime | None
) -> list[CandidateInterview]:
    query = select(CandidateInterview)
    if job_id is not None:
        query = query.where(CandidateInterview.job_id == job_id)
    if from_ is not None:
        query = query.where(CandidateInterview.scheduled_at >= to_naive_utc(from_))
    if to is not None:
        query = query.where(CandidateInterview.scheduled_at <= to_naive_utc(to))
    result = await db.execute(query.order_by(CandidateInterview.scheduled_at))
    return list(result.scalars().all())


async def allocated_slots(db: AsyncSession) -> list[tuple[datetime, int | None]]:
    """Confirmed upcoming interview times - `{datetime, interviewerId}` pairs,
    matching interviews.routes.ts's `/interviews/allocated-slots` shape."""
    now = datetime.now(UTC).replace(tzinfo=None)
    result = await db.execute(
        select(CandidateInterview.scheduled_at, CandidateInterview.interviewer_id).where(
            CandidateInterview.status == "scheduled", CandidateInterview.scheduled_at >= now
        )
    )
    return [(scheduled_at, interviewer_id) for scheduled_at, interviewer_id in result.all() if scheduled_at is not None]


async def get_interview(db: AsyncSession, interview_id: int) -> CandidateInterview:
    interview = await db.get(CandidateInterview, interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


async def update_interview(db: AsyncSession, interview_id: int, *, data: dict) -> CandidateInterview:
    interview = await get_interview(db, interview_id)
    if data.get("scheduled_at") is not None:
        data["scheduled_at"] = to_naive_utc(data["scheduled_at"])
    for key, value in data.items():
        setattr(interview, key, value)
    await db.commit()
    await db.refresh(interview)
    await _sync_calendar_update(db, interview)
    return interview


async def schedule_interview(
    db: AsyncSession, candidate_id: int, *, data: dict, created_by: int
) -> CandidateInterview:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    meeting_provider = data.get("meeting_provider")
    if meeting_provider is not None:
        token = await connection_service.get_valid_access_token(db, data["interviewer_id"])
        if token is None:
            raise HTTPException(
                status_code=422, detail="Selected interviewer has not connected this meeting provider"
            )

    # Falls back to the candidate's current stage, then a literal 0 - the
    # same rule the TS route applies inline (interviews.routes.ts).
    data["stage_id"] = data.get("stage_id") or candidate.current_stage_id or 0

    # Stored as naive-UTC ISO strings so they compare equal to `scheduled_at`
    # (also naive UTC) once a slot is claimed - see get_by_token/select_slot.
    time_slots = [
        {"datetime": to_naive_utc(slot["datetime"]).isoformat(), "selected": slot["selected"]}
        for slot in data.pop("time_slots")
    ]
    public_token = secrets.token_hex(32)

    interview = CandidateInterview(
        candidate_id=candidate_id,
        job_id=candidate.job_id,
        created_by=created_by,
        time_slots=time_slots,
        status="pending_schedule",
        public_token=public_token,
        token_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=SCHEDULE_TOKEN_TTL_DAYS),
        **data,
    )
    db.add(interview)
    await db.commit()
    await db.refresh(interview)

    select_url = f"{settings.frontend_url}/interview/{public_token}"
    try:
        job = await db.get(Job, candidate.job_id)
        assert job is not None, "guaranteed by the jobs.id FK on candidates"
        mail_service.send_interview_slot_email(
            to=candidate.email,
            candidate_name=f"{candidate.first_name} {candidate.last_name}",
            job_title=job.title,
            select_url=select_url,
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to send interview slot-selection email for interview=%s", interview.id)

    return interview


async def _taken_times(
    db: AsyncSession, *, exclude_interview_id: int, interviewer_id: int | None
) -> set[datetime]:
    """The `getTakenTimes` collision check from public.routes.ts: confirmed
    times already claimed by *other* interviews. A row counts as taken
    unless both interviews have a set, *different* interviewer - i.e. same
    interviewer, or no interviewer on either side, both collide."""
    result = await db.execute(
        select(CandidateInterview.scheduled_at, CandidateInterview.interviewer_id).where(
            CandidateInterview.status == "scheduled",
            CandidateInterview.id != exclude_interview_id,
        )
    )
    taken: set[datetime] = set()
    for scheduled_at, row_interviewer_id in result.all():
        if scheduled_at is None:
            continue
        if (
            interviewer_id is not None
            and row_interviewer_id is not None
            and row_interviewer_id != interviewer_id
        ):
            continue
        taken.add(scheduled_at)
    return taken


async def build_public_view(db: AsyncSession, interview: CandidateInterview, taken: set[datetime]) -> dict:
    """Shapes the candidate-facing slot-selection payload - shared by the
    real public route and its /api-mounted "public in name only" duplicate."""
    candidate = await db.get(Candidate, interview.candidate_id)
    job = await db.get(Job, interview.job_id)
    assert candidate is not None and job is not None, "guaranteed by the FKs on candidate_interviews"
    time_slots = [
        {**slot, "taken": datetime.fromisoformat(slot["datetime"]) in taken}
        for slot in (interview.time_slots or [])
    ]
    return {
        "candidate_name": f"{candidate.first_name} {candidate.last_name}",
        "job_title": job.title,
        "event_name": interview.event_name,
        "event_type": interview.event_type,
        "location": interview.location,
        "body_text": interview.body_text,
        "duration_minutes": interview.duration_minutes,
        "time_slots": time_slots,
        "status": interview.status,
    }


async def get_by_token(db: AsyncSession, token: str) -> tuple[CandidateInterview, set[datetime]]:
    result = await db.execute(select(CandidateInterview).where(CandidateInterview.public_token == token))
    interview = result.scalar_one_or_none()
    if interview is None:
        raise HTTPException(status_code=404, detail="Invalid link")

    now = datetime.now(UTC).replace(tzinfo=None)
    if interview.token_expires_at is not None and interview.token_expires_at < now:
        # Quirk preserved from public.routes.ts: an expired link 404s here
        # (unlike the select endpoint below, which 410s) - it just looks gone.
        raise HTTPException(status_code=404, detail="Invalid link")

    taken = await _taken_times(db, exclude_interview_id=interview.id, interviewer_id=interview.interviewer_id)
    return interview, taken


async def select_slot(db: AsyncSession, token: str, *, slot_index: int) -> tuple[CandidateInterview, dict]:
    """`PATCH /public/interview/:token/select` - public.routes.ts lines
    227-445. `slot_index` indexes into the interview's stored `time_slots`
    array (the request contract is `{"slotIndex": n}`, not a raw datetime).
    Raises SlotTakenError (-> 409 SLOT_TAKEN) on a cross-interview collision.
    """
    result = await db.execute(select(CandidateInterview).where(CandidateInterview.public_token == token))
    interview = result.scalar_one_or_none()
    if interview is None or not interview.time_slots:
        raise HTTPException(status_code=404, detail="Invalid link")

    now = datetime.now(UTC).replace(tzinfo=None)
    if interview.token_expires_at is not None and interview.token_expires_at < now:
        raise HTTPException(status_code=410, detail="This scheduling link has expired")

    if interview.status == "scheduled":
        raise HTTPException(status_code=409, detail="This interview has already been scheduled")

    slots: list[dict] = interview.time_slots
    if slot_index < 0 or slot_index >= len(slots):
        raise HTTPException(status_code=400, detail="Invalid slot")

    selected_slot = slots[slot_index]
    scheduled_at = to_naive_utc(datetime.fromisoformat(selected_slot["datetime"]))
    if scheduled_at <= now:
        raise HTTPException(
            status_code=400,
            detail="This time slot has already passed. Please contact the hiring team for new times.",
        )

    taken = await _taken_times(db, exclude_interview_id=interview.id, interviewer_id=interview.interviewer_id)
    if scheduled_at in taken:
        raise SlotTakenError()

    selected_slot["selected"] = True

    # Claim first (atomic UPDATE ... WHERE status='pending_schedule') so
    # concurrent confirms on *this* interview can't double-book it - a
    # separate guard from the cross-interview collision check above.
    claim = await db.execute(
        update(CandidateInterview)
        .where(CandidateInterview.id == interview.id, CandidateInterview.status == "pending_schedule")
        .values(time_slots=slots, status="scheduled", scheduled_at=scheduled_at)
        .returning(CandidateInterview.id)
    )
    if claim.scalar_one_or_none() is None:
        raise HTTPException(status_code=409, detail="This interview has already been scheduled")
    await db.commit()
    await db.refresh(interview)

    candidate = await db.get(Candidate, interview.candidate_id)
    job = await db.get(Job, interview.job_id)
    assert candidate is not None and job is not None, "guaranteed by the FKs on candidate_interviews"
    interviewer = await db.get(User, interview.interviewer_id) if interview.interviewer_id is not None else None

    original_meeting_url = interview.meeting_url
    meeting_url = interview.meeting_url
    provider_meeting_id: str | None = None
    if interview.meeting_provider is not None and interview.interviewer_id is not None:
        try:
            access_token = await connection_service.get_valid_access_token(db, interview.interviewer_id)
            if access_token is not None:
                provider = get_provider_client(interview.meeting_provider)
                meeting = await provider.create_meeting(
                    access_token,
                    CreateMeetingInput(
                        event_name=interview.event_name or "Interview",
                        scheduled_at=scheduled_at,
                        # Hardcoded to 60 in public.routes.ts for this flow -
                        # deliberately NOT interview.duration_minutes.
                        duration_minutes=60,
                        attendee_emails=[candidate.email],
                    ),
                )
                meeting_url = meeting.meeting_url
                provider_meeting_id = meeting.provider_meeting_id
            else:
                logger.warning(
                    "interview=%s: interviewer=%s no longer has a valid %s connection - "
                    "confirmation will go out without an auto-generated link",
                    interview.id, interview.interviewer_id, interview.meeting_provider,
                )
        except Exception:  # noqa: BLE001
            logger.exception("failed to auto-generate meeting link for interview=%s", interview.id)

    if (interview.event_type or "virtual") == "virtual" and not meeting_url:
        logger.warning("interview=%s confirmed as virtual but has no meeting link", interview.id)

    google_event_id: str | None = None
    if interview.event_name:
        try:
            event_input = google_calendar_service.CalendarEventInput(
                candidate_name=f"{candidate.first_name} {candidate.last_name}",
                # Empty strings are a preserved quirk from public.routes.ts,
                # not a bug to fix.
                job_title="",
                stage_name="",
                notes=interview.body_text,
                meeting_url=meeting_url,
                scheduled_at=scheduled_at,
                duration_minutes=60,
                attendee_emails=[candidate.email] + ([interviewer.email] if interviewer else []),
            )
            google_event_id = google_calendar_service.create_calendar_event(event_input)
        except Exception:  # noqa: BLE001
            logger.exception("failed to create calendar event for interview=%s", interview.id)

    if meeting_url != original_meeting_url or google_event_id or provider_meeting_id:
        interview.meeting_url = meeting_url
        if google_event_id:
            interview.google_event_id = google_event_id
        if provider_meeting_id:
            interview.provider_meeting_id = provider_meeting_id
        await db.commit()

    if interview.event_name:
        try:
            mail_service.send_interview_confirmation_email(
                to=candidate.email,
                candidate_name=f"{candidate.first_name} {candidate.last_name}",
                job_title=job.title,
                scheduled_at=scheduled_at,
                meeting_url=meeting_url,
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to send interview confirmation email for interview=%s", interview.id)

    return interview, selected_slot


async def delete_interview(db: AsyncSession, interview_id: int) -> None:
    interview = await get_interview(db, interview_id)
    was_scheduled = interview.status == "scheduled"

    meeting_provider = interview.meeting_provider
    provider_meeting_id = interview.provider_meeting_id
    interviewer_id = interview.interviewer_id
    if meeting_provider is not None and provider_meeting_id and interviewer_id is not None:
        try:
            access_token = await connection_service.get_valid_access_token(db, interviewer_id)
            if access_token is not None:
                provider = get_provider_client(meeting_provider)
                await provider.delete_meeting(access_token, provider_meeting_id)
        except Exception:  # noqa: BLE001
            logger.exception("failed to cancel provider meeting for interview=%s", interview_id)

    if interview.google_event_id:
        try:
            google_calendar_service.delete_calendar_event(interview.google_event_id)
        except Exception:  # noqa: BLE001
            logger.exception("failed to delete calendar event for interview=%s", interview_id)

    candidate = await db.get(Candidate, interview.candidate_id)
    job = await db.get(Job, interview.job_id)

    await db.delete(interview)
    await db.commit()

    if was_scheduled and candidate is not None and job is not None:
        try:
            mail_service.send_interview_cancellation_email(
                to=candidate.email,
                candidate_name=f"{candidate.first_name} {candidate.last_name}",
                job_title=job.title,
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to send interview cancellation email for interview=%s", interview_id)


async def add_feedback(
    db: AsyncSession, interview_id: int, *, content: str, rating: int | None, author_id: int
) -> InterviewFeedback:
    await get_interview(db, interview_id)
    feedback = InterviewFeedback(
        interview_id=interview_id, author_id=author_id, content=content, rating=rating
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


async def list_feedback(db: AsyncSession, interview_id: int) -> list[InterviewFeedback]:
    result = await db.execute(
        select(InterviewFeedback)
        .where(InterviewFeedback.interview_id == interview_id)
        .order_by(InterviewFeedback.created_at)
    )
    return list(result.scalars().all())


async def delete_feedback(db: AsyncSession, interview_id: int, feedback_id: int) -> None:
    feedback = await db.get(InterviewFeedback, feedback_id)
    if feedback is None or feedback.interview_id != interview_id:
        raise HTTPException(status_code=404, detail="Feedback not found")
    await db.delete(feedback)
    await db.commit()
