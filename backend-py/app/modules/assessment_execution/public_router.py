"""GET/POST /public/assessment/:token[...] - the real unauthenticated
candidate-facing flow, equivalent to the assessment handlers in
public.routes.ts. Hits the same service functions as router.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.assessment_execution import service
from app.modules.assessment_execution.router import questions_out
from app.modules.assessment_execution.schemas import (
    AnswerIn,
    AttemptDetailOut,
    AttemptOut,
    CompleteAssessmentIn,
)
from app.shared.rate_limit import public_read_limiter, public_write_limiter
from app.sockets.server import notify_assessment_progress

router = APIRouter()


@router.get(
    "/assessment/{token}", response_model=AttemptDetailOut, dependencies=[Depends(public_read_limiter)]
)
async def get_attempt(token: str, db: AsyncSession = Depends(get_db)) -> AttemptDetailOut:
    attempt = await service.get_by_token(db, token)
    questions = await service.get_questions_for_candidate(db, attempt.assessment_id)
    return AttemptDetailOut(attempt=AttemptOut.model_validate(attempt), questions=questions_out(questions))


@router.post(
    "/assessment/{token}/start", response_model=AttemptOut, dependencies=[Depends(public_write_limiter)]
)
async def start_attempt(token: str, db: AsyncSession = Depends(get_db)) -> AttemptOut:
    attempt = await service.start_attempt(db, token)
    return AttemptOut.model_validate(attempt)


@router.post("/assessment/{token}/answer", dependencies=[Depends(public_write_limiter)])
async def submit_answer(token: str, body: AnswerIn, db: AsyncSession = Depends(get_db)) -> dict:
    attempt = await service.get_by_token(db, token)
    await service.submit_answer(
        db, token, question_id=body.question_id, answer_text=body.answer_text, option_ids=body.option_ids
    )
    await notify_assessment_progress(attempt.candidate_id, attempt.id)
    return {"success": True}


@router.post("/assessment/{token}/complete", dependencies=[Depends(public_write_limiter)])
async def complete_attempt(
    token: str, body: CompleteAssessmentIn = CompleteAssessmentIn(), db: AsyncSession = Depends(get_db)
) -> dict:
    attempt = await service.complete_attempt(db, token, auto_submit_reason=body.auto_submit_reason)
    await notify_assessment_progress(attempt.candidate_id, attempt.id)
    return {
        "message": "Assessment completed successfully",
        "data": {"passed": attempt.passed, "scorePercentage": attempt.score_percentage},
    }
