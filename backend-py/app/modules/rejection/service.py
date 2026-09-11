"""Equivalent to backend/src/modules/rejection/rejection.service.ts."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidates import Candidate, CandidateStageHistory
from app.db.models.enums import CandidateStatus, RejectionEmailStatus
from app.db.models.jobs import Job
from app.db.models.pipeline import JobPipelineStage
from app.db.models.rejections import CandidateRejection
from app.db.models.templates import Template
from app.logging import get_logger
from app.modules.template.template_engine_service import compile_template
from app.modules.template.variable_service import get_context_for_candidate
from app.shared.services import mail_service

logger = get_logger(__name__)


async def list_rejections(db: AsyncSession, candidate_id: int) -> list[CandidateRejection]:
    result = await db.execute(
        select(CandidateRejection)
        .where(CandidateRejection.candidate_id == candidate_id)
        .order_by(CandidateRejection.rejected_at.desc())
    )
    return list(result.scalars().all())


async def reject(
    db: AsyncSession,
    candidate_id: int,
    *,
    reason: str,
    internal_note: str | None,
    template_id: int | None,
    email_status: RejectionEmailStatus,
    rejected_by: int,
) -> CandidateRejection:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status == CandidateStatus.rejected:
        raise HTTPException(status_code=400, detail="Candidate is already rejected")

    rejection = CandidateRejection(
        candidate_id=candidate_id,
        job_id=candidate.job_id,
        from_stage_id=candidate.current_stage_id,
        rejected_by=rejected_by,
        reason=reason,
        internal_note=internal_note,
        template_id=template_id,
        email_status=email_status,
        sent_at=datetime.now(UTC).replace(tzinfo=None) if email_status == RejectionEmailStatus.sent else None,
    )
    db.add(rejection)

    candidate.status = CandidateStatus.rejected
    candidate.current_stage_id = None

    await db.commit()
    await db.refresh(rejection)

    if email_status == RejectionEmailStatus.sent and template_id is not None:
        template = await db.get(Template, template_id)
        if template is None:
            raise HTTPException(status_code=400, detail="Template not found")
        job = await db.get(Job, rejection.job_id)
        assert job is not None, "guaranteed by the jobs.id FK on candidates"
        context = await get_context_for_candidate(db, candidate)
        compiled = compile_template(subject=template.subject, body_json=template.body_json, context=context)
        try:
            mail_service.send_rejection_email(
                to=candidate.email,
                candidate_name=f"{candidate.first_name} {candidate.last_name}",
                job_title=job.title,
                body_html=compiled["html"],
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to send rejection email for candidate=%s", candidate_id)

    return rejection


async def unreject(db: AsyncSession, candidate_id: int, *, actor_id: int) -> Candidate:
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status != CandidateStatus.rejected:
        raise HTTPException(status_code=400, detail="Candidate is not rejected")

    result = await db.execute(
        select(CandidateRejection)
        .where(CandidateRejection.candidate_id == candidate_id)
        .order_by(CandidateRejection.rejected_at.desc())
        .limit(1)
    )
    latest_rejection = result.scalar_one_or_none()

    target_stage_id = latest_rejection.from_stage_id if latest_rejection else None
    if target_stage_id is not None:
        stage = await db.get(JobPipelineStage, target_stage_id)
        if stage is None or stage.job_id != candidate.job_id:
            target_stage_id = None

    if target_stage_id is None:
        first_stage_result = await db.execute(
            select(JobPipelineStage)
            .where(JobPipelineStage.job_id == candidate.job_id)
            .order_by(JobPipelineStage.position)
            .limit(1)
        )
        first_stage = first_stage_result.scalar_one_or_none()
        target_stage_id = first_stage.id if first_stage else None

    candidate.status = CandidateStatus.active
    candidate.current_stage_id = target_stage_id
    if target_stage_id is not None:
        db.add(CandidateStageHistory(candidate_id=candidate_id, stage_id=target_stage_id, moved_by=actor_id))

    await db.commit()
    await db.refresh(candidate)
    return candidate
