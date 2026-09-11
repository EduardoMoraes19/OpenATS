"""Equivalent to backend/src/modules/assessment-execution/assessment-execution.routes.ts.

Mounted at /api/assessment-execution (authenticated, since it sits under
the api_router's global get_current_user dependency) - note its own
/public/:token/... sub-paths here are STILL authenticated for that reason;
the real candidate-facing unauthenticated flow lives in public_router.py,
hitting the same service functions, matching the TS quirk exactly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.assessment_execution import service
from app.modules.assessment_execution.schemas import (
    AnswerIn,
    AttemptDetailOut,
    AttemptOut,
    AttemptResultsOut,
    CompleteAssessmentIn,
    GradedAnswerOut,
    InviteCandidateIn,
    InviteCandidateOut,
    QuestionForCandidateOut,
)
from app.sockets.server import notify_assessment_progress

router = APIRouter()


def questions_out(questions) -> list[QuestionForCandidateOut]:
    return [
        QuestionForCandidateOut(
            id=q.id, title=q.title, description=q.description, question_type=q.question_type.value,
            points=q.points, position=q.position,
            options=[{"id": o.id, "label": o.label, "position": o.position} for o in q.options],
        )
        for q in questions
    ]


@router.post("/invite", response_model=InviteCandidateOut, status_code=201)
async def invite_candidate(body: InviteCandidateIn, db: AsyncSession = Depends(get_db)) -> InviteCandidateOut:
    attempt, did_send = await service.invite_candidate(
        db, candidate_id=body.candidate_id, assessment_id=body.assessment_id, expiry_days=body.expiry_days
    )
    return InviteCandidateOut(attempt_id=attempt.id, token=attempt.token, did_send_invite=did_send)


@router.get("/candidate/{candidate_id}", response_model=list[AttemptOut])
async def list_attempts(candidate_id: int, db: AsyncSession = Depends(get_db)) -> list[AttemptOut]:
    attempts = await service.list_attempts_for_candidate(db, candidate_id)
    return [AttemptOut.model_validate(a) for a in attempts]


@router.get("/attempts/{attempt_id}/results", response_model=AttemptResultsOut)
async def get_results(attempt_id: int, db: AsyncSession = Depends(get_db)) -> AttemptResultsOut:
    attempt, graded = await service.get_results(db, attempt_id)
    return AttemptResultsOut(
        attempt=AttemptOut.model_validate(attempt), answers=[GradedAnswerOut(**g) for g in graded]
    )


@router.get("/public/{token}", response_model=AttemptDetailOut)
async def get_attempt_by_token(token: str, db: AsyncSession = Depends(get_db)) -> AttemptDetailOut:
    attempt = await service.get_by_token(db, token)
    questions = await service.get_questions_for_candidate(db, attempt.assessment_id)
    return AttemptDetailOut(attempt=AttemptOut.model_validate(attempt), questions=questions_out(questions))


@router.post("/public/{token}/start", response_model=AttemptOut)
async def start_attempt(token: str, db: AsyncSession = Depends(get_db)) -> AttemptOut:
    attempt = await service.start_attempt(db, token)
    return AttemptOut.model_validate(attempt)


@router.post("/public/{token}/answer")
async def submit_answer(token: str, body: AnswerIn, db: AsyncSession = Depends(get_db)) -> dict:
    attempt = await service.get_by_token(db, token)
    await service.submit_answer(
        db, token, question_id=body.question_id, answer_text=body.answer_text, option_ids=body.option_ids
    )
    await notify_assessment_progress(attempt.candidate_id, attempt.id)
    return {"success": True}


@router.post("/public/{token}/complete")
async def complete_attempt(
    token: str, body: CompleteAssessmentIn = CompleteAssessmentIn(), db: AsyncSession = Depends(get_db)
) -> dict:
    attempt = await service.complete_attempt(db, token, auto_submit_reason=body.auto_submit_reason)
    await notify_assessment_progress(attempt.candidate_id, attempt.id)
    return {
        "message": "Assessment completed successfully",
        "data": {"passed": attempt.passed, "scorePercentage": attempt.score_percentage},
    }
