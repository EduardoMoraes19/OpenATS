"""Equivalent to backend/src/modules/assessment-execution/assessment-execution.service.ts.

`invite_candidate` reuses an active attempt (started, or pending and not
expired) instead of creating a duplicate. `complete_attempt` grades
option-based questions by exact-set comparison of selected vs correct
option ids; short_answer/long_answer always score 0 (no auto-grading is
implemented - matching the current, admittedly incomplete, TS behavior,
not something to "fix" here). `passed` is always left null - no pass/fail
threshold logic is wired in the source either.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.assessments import Assessment, AssessmentQuestion
from app.db.models.candidates import (
    Candidate,
    CandidateAssessmentAnswer,
    CandidateAssessmentAnswerSelection,
    CandidateAssessmentAttempt,
)
from app.db.models.enums import AssessmentStatus, QuestionType
from app.logging import get_logger
from app.settings import settings
from app.shared.services import mail_service

logger = get_logger(__name__)

_OPTION_BASED_TYPES = {QuestionType.checkbox, QuestionType.radio, QuestionType.multiple_choice}


async def invite_candidate(
    db: AsyncSession, *, candidate_id: int, assessment_id: int, expiry_days: int = 7
) -> tuple[CandidateAssessmentAttempt, bool]:
    now = datetime.now(UTC).replace(tzinfo=None)
    result = await db.execute(
        select(CandidateAssessmentAttempt).where(
            CandidateAssessmentAttempt.candidate_id == candidate_id,
            CandidateAssessmentAttempt.assessment_id == assessment_id,
            (CandidateAssessmentAttempt.status == AssessmentStatus.started)
            | (
                (CandidateAssessmentAttempt.status == AssessmentStatus.pending)
                & (CandidateAssessmentAttempt.expires_at > now)
            ),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    token = secrets.token_hex(32)
    attempt = CandidateAssessmentAttempt(
        candidate_id=candidate_id,
        assessment_id=assessment_id,
        token=token,
        status=AssessmentStatus.pending,
        expires_at=now + timedelta(days=expiry_days),
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    candidate = await db.get(Candidate, candidate_id)
    assessment = await db.get(Assessment, assessment_id)
    assert candidate is not None and assessment is not None, (
        "guaranteed by the FK-constrained insert above"
    )
    invite_url = f"{settings.frontend_url}/assessment/{token}"
    try:
        await mail_service.send_assessment_invite_email(
            to=candidate.email,
            subject=f"Assessment invite: {assessment.title}",
            body_html=f'<p>Hi {candidate.first_name},</p><p>Please complete your assessment: '
            f'<a href="{invite_url}">{invite_url}</a></p>',
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to send assessment invite email for candidate=%s", candidate_id)

    return attempt, True


async def get_by_token(db: AsyncSession, token: str) -> CandidateAssessmentAttempt:
    """Port of getAttemptByTokenOrFail, shared by every public token-based
    handler: 404 for an unknown token, 410 once expiresAt has passed."""
    result = await db.execute(
        select(CandidateAssessmentAttempt).where(CandidateAssessmentAttempt.token == token)
    )
    attempt = result.scalar_one_or_none()
    if attempt is None:
        raise HTTPException(status_code=404, detail="Assessment attempt not found or invalid token")

    now = datetime.now(UTC).replace(tzinfo=None)
    if attempt.expires_at < now:
        raise HTTPException(status_code=410, detail="Assessment link has expired")

    return attempt


async def get_questions_for_candidate(db: AsyncSession, assessment_id: int) -> list[AssessmentQuestion]:
    """No `isCorrect` is leaked to the candidate-facing payload - filter it
    out at the router/schema layer, not here."""
    result = await db.execute(
        select(AssessmentQuestion)
        .options(selectinload(AssessmentQuestion.options))
        .where(AssessmentQuestion.assessment_id == assessment_id)
        .order_by(AssessmentQuestion.position)
    )
    return list(result.scalars().unique().all())


async def list_attempts_for_candidate(db: AsyncSession, candidate_id: int) -> list[CandidateAssessmentAttempt]:
    result = await db.execute(
        select(CandidateAssessmentAttempt)
        .where(CandidateAssessmentAttempt.candidate_id == candidate_id)
        .order_by(CandidateAssessmentAttempt.created_at.desc())
    )
    return list(result.scalars().all())


async def start_attempt(db: AsyncSession, token: str) -> CandidateAssessmentAttempt:
    attempt = await get_by_token(db, token)
    if attempt.status != AssessmentStatus.pending:
        raise HTTPException(status_code=400, detail="Assessment attempt is not pending")
    attempt.status = AssessmentStatus.started
    attempt.started_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def submit_answer(
    db: AsyncSession, token: str, *, question_id: int, answer_text: str | None, option_ids: list[int]
) -> None:
    attempt = await get_by_token(db, token)
    if attempt.status != AssessmentStatus.started:
        raise HTTPException(status_code=400, detail="Assessment attempt is not in progress")

    result = await db.execute(
        select(CandidateAssessmentAnswer).where(
            CandidateAssessmentAnswer.attempt_id == attempt.id,
            CandidateAssessmentAnswer.question_id == question_id,
        )
    )
    answer = result.scalar_one_or_none()
    if answer is None:
        answer = CandidateAssessmentAnswer(attempt_id=attempt.id, question_id=question_id)
        db.add(answer)
        await db.flush()
    else:
        await db.execute(
            delete(CandidateAssessmentAnswerSelection).where(
                CandidateAssessmentAnswerSelection.answer_id == answer.id
            )
        )

    answer.answer_text = answer_text
    for option_id in option_ids:
        db.add(CandidateAssessmentAnswerSelection(answer_id=answer.id, option_id=option_id))

    await db.commit()


async def complete_attempt(
    db: AsyncSession, token: str, *, auto_submit_reason: str | None = None
) -> CandidateAssessmentAttempt:
    attempt = await get_by_token(db, token)
    if attempt.status != AssessmentStatus.started:
        raise HTTPException(status_code=400, detail="Only started assessments can be completed")

    questions = await get_questions_for_candidate(db, attempt.assessment_id)
    answers_result = await db.execute(
        select(CandidateAssessmentAnswer)
        .options(selectinload(CandidateAssessmentAnswer.selections))
        .where(CandidateAssessmentAnswer.attempt_id == attempt.id)
    )
    answers_by_question = {a.question_id: a for a in answers_result.scalars().unique().all()}

    total_points = Decimal("0")
    raw_points = Decimal("0")

    for question in questions:
        total_points += question.points
        answer = answers_by_question.get(question.id)
        if answer is None:
            continue

        if question.question_type in _OPTION_BASED_TYPES:
            selected_ids = {s.option_id for s in answer.selections}
            correct_ids = {o.id for o in question.options if o.is_correct}
            points_earned = question.points if selected_ids == correct_ids else Decimal("0")
        else:
            points_earned = Decimal("0")  # short_answer/long_answer: no auto-grading

        answer.points_earned = points_earned
        raw_points += points_earned

    attempt.status = AssessmentStatus.completed
    attempt.completed_at = datetime.now(UTC).replace(tzinfo=None)
    attempt.score_raw = raw_points
    attempt.score_total = total_points
    attempt.score_percentage = (raw_points / total_points * 100) if total_points > 0 else Decimal("0")
    attempt.passed = None  # no threshold logic implemented - preserved as-is

    await db.commit()
    await db.refresh(attempt)

    candidate = await db.get(Candidate, attempt.candidate_id)
    assert candidate is not None, "guaranteed by the candidates.id FK on candidate_assessment_attempts"
    try:
        await mail_service.send_assessment_completion_email(
            to=candidate.email,
            candidate_name=f"{candidate.first_name} {candidate.last_name}",
            auto_submit_reason=auto_submit_reason,
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to send assessment completion email for attempt=%s", attempt.id)

    return attempt


async def get_results(db: AsyncSession, attempt_id: int) -> tuple[CandidateAssessmentAttempt, list[dict]]:
    attempt = await db.get(CandidateAssessmentAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")

    questions = await get_questions_for_candidate(db, attempt.assessment_id)
    answers_result = await db.execute(
        select(CandidateAssessmentAnswer)
        .options(selectinload(CandidateAssessmentAnswer.selections))
        .where(CandidateAssessmentAnswer.attempt_id == attempt_id)
    )
    answers_by_question = {a.question_id: a for a in answers_result.scalars().unique().all()}

    graded = []
    for question in questions:
        answer = answers_by_question.get(question.id)
        graded.append(
            {
                "question_id": question.id,
                "answer_text": answer.answer_text if answer else None,
                "selected_option_ids": [s.option_id for s in answer.selections] if answer else [],
                "correct_option_ids": [o.id for o in question.options if o.is_correct],
                "points_earned": answer.points_earned if answer else None,
                "points_possible": question.points,
            }
        )
    return attempt, graded
