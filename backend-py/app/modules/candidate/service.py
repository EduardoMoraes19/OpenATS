"""Equivalent to backend/src/modules/candidate/candidate.service.ts (657
lines in the source - the richest module). Resume URLs are intentionally
NEVER signed here: signing happens once, at the response layer in
router.py, via r2_service.sign_url - internal callers of this service need
the raw stored URL, matching the TS "sign at the response, not in the
service" refactor (see recent commits 7bc617e/93e856a).
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assessments import JobAssessmentAttachment
from app.db.models.candidates import (
    Candidate,
    CandidateCustomAnswer,
    CandidateCustomAnswerSelection,
    CandidateStageHistory,
)
from app.db.models.enums import CandidateActivityType, CandidateStatus, OfferStatus, StageType
from app.db.models.jobs import Job
from app.db.models.offers import Offer
from app.db.models.pipeline import JobHiringTeam, JobPipelineStage
from app.logging import get_logger
from app.modules.assessment_execution import service as assessment_execution_service
from app.modules.candidate import activity_service
from app.modules.candidate.schemas import StageAutomationFlags
from app.modules.rejection import service as rejection_service
from app.shared.db_errors import is_unique_violation
from app.shared.services import mail_service, r2_service

logger = get_logger(__name__)


class DuplicateApplicationError(Exception):
    pass


async def apply_for_job(
    db: AsyncSession,
    job_id: int,
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    resume_url: str | None,
    custom_answers: list[dict],
) -> Candidate:
    first_stage_result = await db.execute(
        select(JobPipelineStage)
        .where(JobPipelineStage.job_id == job_id)
        .order_by(JobPipelineStage.position)
        .limit(1)
    )
    first_stage = first_stage_result.scalar_one_or_none()

    candidate = Candidate(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        resume_url=resume_url,
        job_id=job_id,
        current_stage_id=first_stage.id if first_stage else None,
    )
    db.add(candidate)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if is_unique_violation(exc):
            raise DuplicateApplicationError() from exc
        raise

    if first_stage is not None:
        db.add(CandidateStageHistory(candidate_id=candidate.id, stage_id=first_stage.id))

    for answer in custom_answers:
        db.add(
            CandidateCustomAnswer(
                candidate_id=candidate.id,
                question_id=answer["question_id"],
                answer_text=answer.get("answer_text"),
            )
        )
        for option_id in answer.get("option_ids", []):
            db.add(
                CandidateCustomAnswerSelection(
                    candidate_id=candidate.id, question_id=answer["question_id"], option_id=option_id
                )
            )

    await db.commit()
    await db.refresh(candidate)

    try:
        job = await db.get(Job, job_id)
        assert job is not None, "guaranteed by the FK-constrained candidate insert above"
        await mail_service.send_email(
            to=email,
            subject=f"Application received: {job.title}",
            html=f"<p>Hi {first_name},</p><p>We've received your application for {job.title}. "
            f"We'll be in touch soon.</p>",
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to send application confirmation email for candidate=%s", candidate.id)

    return candidate


async def list_candidates(
    db: AsyncSession,
    *,
    job_id: int | None,
    stage_id: int | None,
    search: str | None,
    status: str | None,
    page: int | None,
    limit: int | None,
    team_user_id: int | None,
):
    """Mirrors candidate.service.ts's `getAll` (the sole list query behind
    both `GET /candidates` and `GET /candidates/jobs/:jobId`): unlike the
    job/template/offer list endpoints, this one is never dual-mode - it
    always paginates, defaulting to page=1/limit=25 when the caller (the
    router) didn't already resolve them from query params. Each row is
    joined with its current stage's name and job's title, matching the TS
    service's own select.
    """
    resolved_page = page if page is not None else 1
    resolved_limit = limit if limit is not None else 25
    offset = (resolved_page - 1) * resolved_limit

    query = (
        select(
            Candidate.id,
            Candidate.first_name,
            Candidate.last_name,
            Candidate.email,
            Candidate.phone,
            Candidate.resume_url,
            Candidate.job_id,
            Candidate.current_stage_id,
            Candidate.status,
            Candidate.applied_at,
            Candidate.updated_at,
            JobPipelineStage.name.label("stage_name"),
            Job.title.label("job_title"),
        )
        .select_from(Candidate)
        .outerjoin(JobPipelineStage, Candidate.current_stage_id == JobPipelineStage.id)
        .outerjoin(Job, Candidate.job_id == Job.id)
    )
    count_query = select(func.count()).select_from(Candidate)

    conditions = []
    if job_id is not None:
        conditions.append(Candidate.job_id == job_id)
    if stage_id is not None:
        conditions.append(Candidate.current_stage_id == stage_id)
    if status is not None:
        conditions.append(Candidate.status == status)
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                Candidate.first_name.ilike(pattern),
                Candidate.last_name.ilike(pattern),
                Candidate.email.ilike(pattern),
            )
        )
    if team_user_id is not None:
        team_job_ids = select(JobHiringTeam.job_id).where(JobHiringTeam.user_id == team_user_id)
        conditions.append(Candidate.job_id.in_(team_job_ids))

    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Candidate.applied_at.desc()).offset(offset).limit(resolved_limit)
    rows = (await db.execute(query)).all()
    return rows, total, resolved_page, resolved_limit


async def get_candidate(db: AsyncSession, candidate_id: int) -> Candidate:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


async def update_basic_details(
    db: AsyncSession, candidate_id: int, *, data: dict, new_resume_url: str | None
) -> Candidate:
    candidate = await get_candidate(db, candidate_id)
    old_resume_url = candidate.resume_url

    for key, value in data.items():
        setattr(candidate, key, value)
    if new_resume_url is not None:
        candidate.resume_url = new_resume_url

    await db.commit()
    await db.refresh(candidate)

    # Only delete the old file once the new one is confirmed stored - never
    # delete-before-confirm, matching candidate.controller.ts's ordering.
    if new_resume_url is not None and old_resume_url is not None and old_resume_url != new_resume_url:
        r2_service.delete_by_url(old_resume_url)

    return candidate


async def move_stage(
    db: AsyncSession, candidate_id: int, *, new_stage_id: int, actor_id: int
) -> tuple[Candidate, StageAutomationFlags]:
    """Mirrors candidate.service.ts's moveStage: candidate-not-found and
    invalid-stage errors are both generic (mapped to HTTP 400 by the router's
    caller), never 404 - matching moveCandidateStage's catch-all in the TS
    controller."""
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=400, detail="Candidate not found")

    automation = StageAutomationFlags()

    target_stage = await db.get(JobPipelineStage, new_stage_id)
    if target_stage is None or target_stage.job_id != candidate.job_id:
        raise HTTPException(status_code=400, detail="Invalid stage for this job")

    if candidate.current_stage_id == new_stage_id:
        return candidate, automation

    if candidate.status not in (CandidateStatus.rejected, CandidateStatus.hired):
        next_status = (
            CandidateStatus.offered if target_stage.stage_type == StageType.offer else CandidateStatus.active
        )
        candidate.status = next_status

    candidate.current_stage_id = new_stage_id
    db.add(CandidateStageHistory(candidate_id=candidate_id, stage_id=new_stage_id, moved_by=actor_id))

    if target_stage.stage_type == StageType.offer:
        existing_offer = (
            await db.execute(
                select(Offer).where(Offer.candidate_id == candidate_id, Offer.job_id == candidate.job_id)
            )
        ).scalar_one_or_none()
        if existing_offer is None:
            offer = Offer(
                candidate_id=candidate_id,
                job_id=candidate.job_id,
                status=OfferStatus.draft,
                created_by=actor_id,
            )
            db.add(offer)
            await db.flush()
            await activity_service.create(
                db, candidate_id=candidate_id, job_id=candidate.job_id, offer_id=offer.id,
                stage_id=new_stage_id, actor_id=actor_id, event_type=CandidateActivityType.offer_created,
            )

    attachment_result = await db.execute(
        select(JobAssessmentAttachment).where(
            JobAssessmentAttachment.job_id == candidate.job_id,
            JobAssessmentAttachment.trigger_stage_id == new_stage_id,
        )
    )
    attachment = attachment_result.scalar_one_or_none()
    if attachment is not None:
        _, did_send = await assessment_execution_service.invite_candidate(
            db, candidate_id=candidate_id, assessment_id=attachment.assessment_id
        )
        automation.assessment_invite = "sent" if did_send else "skipped_active_invite"

    await db.commit()
    await db.refresh(candidate)
    return candidate, automation


async def reject_candidate(db: AsyncSession, candidate_id: int, **kwargs):
    """Thin delegation to rejection.service, matching candidate.service.ts's
    rejectCandidate()."""
    return await rejection_service.reject(db, candidate_id, **kwargs)


async def delete_candidate(db: AsyncSession, candidate_id: int) -> None:
    candidate = await get_candidate(db, candidate_id)
    await db.delete(candidate)
    await db.commit()


async def delete_many_by_filters(
    db: AsyncSession, *, job_id: int | None, stage_id: int | None, search: str | None, status: str | None
) -> int:
    query = select(Candidate.id)
    if job_id is not None:
        query = query.where(Candidate.job_id == job_id)
    if stage_id is not None:
        query = query.where(Candidate.current_stage_id == stage_id)
    if status is not None:
        query = query.where(Candidate.status == status)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(Candidate.first_name.ilike(pattern), Candidate.last_name.ilike(pattern), Candidate.email.ilike(pattern))
        )

    ids = list((await db.execute(query)).scalars().all())
    if ids:
        await db.execute(delete(Candidate).where(Candidate.id.in_(ids)))
        await db.commit()
    return len(ids)
