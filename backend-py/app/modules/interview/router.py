"""Equivalent to backend/src/modules/interview/interviews.routes.ts, mounted
at API root (absolute paths hang off /candidates/:id/... and /interviews),
matching the TS router's root mount.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.interview import service
from app.modules.interview.schemas import (
    AllocatedSlotOut,
    CreateInterviewIn,
    FeedbackIn,
    FeedbackOut,
    InterviewOut,
    PublicInterviewOut,
    ScheduleInterviewIn,
    UpdateInterviewIn,
)
from app.shared.auth.deps import get_current_user, require_manager
from app.shared.auth.jwt_auth import AuthenticatedUser
from app.sockets.server import notify_interview_changed

router = APIRouter()


@router.post(
    "/candidates/{candidate_id}/interviews", response_model=InterviewOut, status_code=201,
    dependencies=[Depends(require_manager)],
)
async def create_interview(
    candidate_id: int,
    body: CreateInterviewIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewOut:
    interview = await service.create_interview(db, candidate_id, data=body.model_dump(), created_by=user.id)
    await notify_interview_changed(interview.id, candidate_id)
    return InterviewOut.model_validate(interview)


@router.get("/candidates/{candidate_id}/interviews", response_model=list[InterviewOut])
async def list_candidate_interviews(candidate_id: int, db: AsyncSession = Depends(get_db)) -> list[InterviewOut]:
    interviews = await service.list_for_candidate(db, candidate_id)
    return [InterviewOut.model_validate(i) for i in interviews]


@router.get("/interviews", response_model=list[InterviewOut])
async def list_interviews(
    job_id: int | None = None,
    search: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[InterviewOut]:
    interviews = await service.list_interviews(db, job_id=job_id, search=search, from_=from_, to=to)
    return [InterviewOut.model_validate(i) for i in interviews]


@router.get("/interviews/allocated-slots", response_model=list[AllocatedSlotOut])
async def allocated_slots(db: AsyncSession = Depends(get_db)) -> list[AllocatedSlotOut]:
    rows = await service.allocated_slots(db)
    return [AllocatedSlotOut(datetime=dt, interviewer_id=interviewer_id) for dt, interviewer_id in rows]


@router.patch(
    "/interviews/{interview_id}", response_model=InterviewOut, dependencies=[Depends(require_manager)]
)
async def update_interview(
    interview_id: int, body: UpdateInterviewIn, db: AsyncSession = Depends(get_db)
) -> InterviewOut:
    # exclude_unset (not exclude_none) mirrors cleanObject() in the TS
    # controller: an omitted field is left alone, but an explicit null
    # (e.g. clearing meetingUrl) is still applied.
    interview = await service.update_interview(db, interview_id, data=body.model_dump(exclude_unset=True))
    await notify_interview_changed(interview.id, interview.candidate_id)
    return InterviewOut.model_validate(interview)


@router.post(
    "/candidates/{candidate_id}/schedule", response_model=InterviewOut, status_code=201,
    dependencies=[Depends(require_manager)],
)
async def schedule_interview(
    candidate_id: int,
    body: ScheduleInterviewIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InterviewOut:
    interview = await service.schedule_interview(db, candidate_id, data=body.model_dump(), created_by=user.id)
    return InterviewOut.model_validate(interview)


@router.get("/public/interview/{token}", response_model=PublicInterviewOut)
async def get_interview_by_token_authed(token: str, db: AsyncSession = Depends(get_db)) -> PublicInterviewOut:
    """Duplicate of the real /public/interview/:token route, still gated by
    the outer api_router's auth dependency because it sits under /api -
    matching the TS quirk of "public" in the path but not actually public."""
    interview, taken = await service.get_by_token(db, token)
    return PublicInterviewOut(**await service.build_public_view(db, interview, taken))


@router.delete("/interviews/{interview_id}", status_code=204, dependencies=[Depends(require_manager)])
async def delete_interview(interview_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_interview(db, interview_id)


@router.post("/interviews/{interview_id}/feedback", response_model=FeedbackOut, status_code=201)
async def add_feedback(
    interview_id: int,
    body: FeedbackIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedbackOut:
    feedback = await service.add_feedback(db, interview_id, content=body.content, rating=body.rating, author_id=user.id)
    return FeedbackOut.model_validate(feedback)


@router.get("/interviews/{interview_id}/feedback", response_model=list[FeedbackOut])
async def list_feedback(interview_id: int, db: AsyncSession = Depends(get_db)) -> list[FeedbackOut]:
    feedback = await service.list_feedback(db, interview_id)
    return [FeedbackOut.model_validate(f) for f in feedback]


@router.delete(
    "/interviews/{interview_id}/feedback/{feedback_id}", status_code=204, dependencies=[Depends(require_manager)]
)
async def delete_feedback(interview_id: int, feedback_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_feedback(db, interview_id, feedback_id)
