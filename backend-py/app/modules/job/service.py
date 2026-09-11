"""Equivalent to backend/src/modules/job/job.service.ts."""

from __future__ import annotations

import re
import time

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assessments import JobAssessmentAttachment
from app.db.models.candidates import Candidate
from app.db.models.jobs import Job, JobSkill
from app.db.models.offers import Offer
from app.db.models.pipeline import JobHiringTeam, JobPipelineStage, PipelineStageTemplate
from app.shared.auth.jwt_auth import AuthenticatedUser
from app.shared.db_errors import is_unique_violation


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{slug}-{int(time.time() * 1000)}"


async def list_jobs_all(db: AsyncSession, *, user: AuthenticatedUser) -> list[Job]:
    """Mirrors job.service.ts's `getAll`: only the interviewer's hiring-team
    scoping applies here - search/status/departmentId are not accepted by
    the TS non-paginated branch, so they are not accepted here either."""
    query = select(Job).order_by(Job.created_at.desc())

    if user.role == "interviewer":
        team_job_ids = select(JobHiringTeam.job_id).where(JobHiringTeam.user_id == user.id)
        query = query.where(Job.id.in_(team_job_ids))

    result = await db.execute(query)
    return list(result.scalars().all())


async def list_jobs_paginated(
    db: AsyncSession,
    *,
    user: AuthenticatedUser,
    page: int,
    limit: int,
    search: str | None,
    status: str | None,
    department_id: int | None,
) -> tuple[list[Job], int]:
    """Mirrors job.service.ts's `getPaginated`: search only matches the
    title (not location)."""
    query = select(Job)
    count_query = select(func.count()).select_from(Job)

    if user.role == "interviewer":
        team_job_ids = select(JobHiringTeam.job_id).where(JobHiringTeam.user_id == user.id)
        query = query.where(Job.id.in_(team_job_ids))
        count_query = count_query.where(Job.id.in_(team_job_ids))

    if search:
        pattern = f"%{search}%"
        query = query.where(Job.title.ilike(pattern))
        count_query = count_query.where(Job.title.ilike(pattern))

    if status:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)

    if department_id:
        query = query.where(Job.department_id == department_id)
        count_query = count_query.where(Job.department_id == department_id)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Job.created_at.desc()).offset((page - 1) * limit).limit(limit)
    jobs = list((await db.execute(query)).scalars().all())
    return jobs, total


async def get_job_skills(db: AsyncSession, job_id: int) -> list[str]:
    result = await db.execute(select(JobSkill.skill).where(JobSkill.job_id == job_id))
    return list(result.scalars().all())


async def create_job(db: AsyncSession, *, data: dict, skills: list[str], creator_id: int) -> Job:
    job = Job(slug=_slugify(data["title"]), created_by=creator_id, **data)
    db.add(job)
    await db.flush()

    for skill in skills:
        db.add(JobSkill(job_id=job.id, skill=skill))

    templates_result = await db.execute(
        select(PipelineStageTemplate).order_by(PipelineStageTemplate.position)
    )
    for template in templates_result.scalars().all():
        db.add(
            JobPipelineStage(
                job_id=job.id,
                name=template.name,
                position=template.position,
                stage_type=template.stage_type,
                source_template_id=template.id,
            )
        )

    db.add(JobHiringTeam(job_id=job.id, user_id=creator_id))

    await db.commit()
    await db.refresh(job)
    return job


async def get_job_by_id(db: AsyncSession, job_id: int) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def get_job_by_slug(db: AsyncSession, slug: str) -> Job:
    result = await db.execute(select(Job).where(Job.slug == slug))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def is_user_on_hiring_team(db: AsyncSession, job_id: int, user_id: int) -> bool:
    result = await db.execute(
        select(JobHiringTeam.id).where(
            JobHiringTeam.job_id == job_id, JobHiringTeam.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None


async def update_job(db: AsyncSession, job_id: int, *, data: dict, skills: list[str] | None) -> Job:
    job = await get_job_by_id(db, job_id)
    for key, value in data.items():
        setattr(job, key, value)

    if skills is not None:
        await db.execute(delete(JobSkill).where(JobSkill.job_id == job_id))
        for skill in skills:
            db.add(JobSkill(job_id=job_id, skill=skill))

    await db.commit()
    await db.refresh(job)
    return job


async def _delete_jobs_cascade(db: AsyncSession, job_ids: list[int]) -> None:
    await db.execute(delete(Offer).where(Offer.job_id.in_(job_ids)))
    await db.execute(delete(Candidate).where(Candidate.job_id.in_(job_ids)))
    await db.execute(delete(Job).where(Job.id.in_(job_ids)))
    await db.commit()


async def delete_job(db: AsyncSession, job_id: int) -> None:
    await get_job_by_id(db, job_id)
    await _delete_jobs_cascade(db, [job_id])


async def bulk_delete_jobs(db: AsyncSession, job_ids: list[int]) -> None:
    await _delete_jobs_cascade(db, job_ids)


async def list_job_assessment_attachments(db: AsyncSession, job_id: int) -> list[JobAssessmentAttachment]:
    result = await db.execute(
        select(JobAssessmentAttachment).where(JobAssessmentAttachment.job_id == job_id)
    )
    return list(result.scalars().all())


async def attach_job_assessment(
    db: AsyncSession, job_id: int, *, assessment_id: int, trigger_stage_id: int
) -> JobAssessmentAttachment:
    attachment = JobAssessmentAttachment(
        job_id=job_id, assessment_id=assessment_id, trigger_stage_id=trigger_stage_id
    )
    db.add(attachment)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_unique_violation(exc):
            raise HTTPException(
                status_code=409, detail="An assessment is already attached to this stage"
            ) from exc
        raise
    await db.refresh(attachment)
    return attachment


async def detach_job_assessment(db: AsyncSession, job_id: int, attachment_id: int) -> None:
    attachment = await db.get(JobAssessmentAttachment, attachment_id)
    if attachment is None or attachment.job_id != job_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await db.delete(attachment)
    await db.commit()
