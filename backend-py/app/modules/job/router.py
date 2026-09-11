"""Equivalent to backend/src/modules/job/job.routes.ts, including mounting
pipeline/hiring-team/custom-question as sub-routes under /jobs, exactly as
the TS router does.
"""

from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.custom_question.router import router as custom_question_router
from app.modules.hiring_team.router import router as hiring_team_router
from app.modules.job import service
from app.modules.job.schemas import (
    CreateJobIn,
    JobAssessmentAttachmentIn,
    JobAssessmentAttachmentOut,
    JobListItemOut,
    JobOut,
    UpdateJobIn,
)
from app.modules.pipeline.router import router as pipeline_router
from app.shared.auth.deps import get_current_user, require_manager
from app.shared.auth.jwt_auth import AuthenticatedUser

router = APIRouter()

router.include_router(pipeline_router, prefix="/{job_id}/pipeline", tags=["pipeline"])
router.include_router(hiring_team_router, prefix="/{job_id}/team", tags=["hiring-team"])
router.include_router(custom_question_router, prefix="/{job_id}/questions", tags=["custom-questions"])


async def _to_list_item(db: AsyncSession, job) -> JobListItemOut:
    skills = await service.get_job_skills(db, job.id)
    return JobListItemOut(**JobOut.model_validate(job).model_dump(), skills=skills)


@router.get("", response_model=None)
async def list_jobs(
    page: int | None = Query(default=None, ge=1),
    limit: int = Query(default=15, ge=1),
    search: str | None = None,
    status: str | None = None,
    department_id: int | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dual-mode like job.controller.ts's `getAllJobs`: no `page` query
    param returns every job as a bare array (auto-wrapped into
    `{"data": [...]}` by the envelope middleware); `page` present (even
    `page=1`) returns `{"data": [...], "pagination": {...}}` with rows
    scoped/filtered/sorted by `getPaginated`."""
    if page is not None:
        jobs, total = await service.list_jobs_paginated(
            db, user=user, page=page, limit=limit, search=search, status=status, department_id=department_id
        )
        items = [await _to_list_item(db, job) for job in jobs]
        return {
            "data": items,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "totalPages": ceil(total / limit) if limit else 0,
            },
        }

    jobs = await service.list_jobs_all(db, user=user)
    return [await _to_list_item(db, job) for job in jobs]


@router.post("", response_model=JobOut, status_code=201, dependencies=[Depends(require_manager)])
async def create_job(
    body: CreateJobIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    data = body.model_dump(exclude={"skills"})
    job = await service.create_job(db, data=data, skills=body.skills, creator_id=user.id)
    return JobOut.model_validate(job)


@router.delete("/bulk", dependencies=[Depends(require_manager)])
async def bulk_delete_jobs(job_ids: list[int], db: AsyncSession = Depends(get_db)) -> dict:
    await service.bulk_delete_jobs(db, job_ids)
    return {"success": True}


@router.get("/slug/{slug}", response_model=JobListItemOut)
async def get_job_by_slug(slug: str, db: AsyncSession = Depends(get_db)) -> JobListItemOut:
    job = await service.get_job_by_slug(db, slug)
    return await _to_list_item(db, job)


@router.get("/{job_id}", response_model=JobListItemOut)
async def get_job(
    job_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobListItemOut:
    job = await service.get_job_by_id(db, job_id)
    if user.role == "interviewer" and not await service.is_user_on_hiring_team(db, job_id, user.id):
        raise HTTPException(status_code=403, detail="You do not have access to this job")
    return await _to_list_item(db, job)


@router.put("/{job_id}", response_model=JobOut, dependencies=[Depends(require_manager)])
async def update_job(job_id: int, body: UpdateJobIn, db: AsyncSession = Depends(get_db)) -> JobOut:
    data = body.model_dump(exclude={"skills"})
    job = await service.update_job(db, job_id, data=data, skills=body.skills)
    return JobOut.model_validate(job)


@router.delete("/{job_id}", status_code=204, dependencies=[Depends(require_manager)])
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_job(db, job_id)


@router.get("/{job_id}/assessments", response_model=list[JobAssessmentAttachmentOut])
async def list_job_assessments(
    job_id: int, db: AsyncSession = Depends(get_db)
) -> list[JobAssessmentAttachmentOut]:
    attachments = await service.list_job_assessment_attachments(db, job_id)
    return [JobAssessmentAttachmentOut.model_validate(a) for a in attachments]


@router.post(
    "/{job_id}/assessments", response_model=JobAssessmentAttachmentOut, status_code=201,
    dependencies=[Depends(require_manager)],
)
async def attach_job_assessment(
    job_id: int, body: JobAssessmentAttachmentIn, db: AsyncSession = Depends(get_db)
) -> JobAssessmentAttachmentOut:
    attachment = await service.attach_job_assessment(
        db, job_id, assessment_id=body.assessment_id, trigger_stage_id=body.trigger_stage_id
    )
    return JobAssessmentAttachmentOut.model_validate(attachment)


@router.delete(
    "/{job_id}/assessments/{attachment_id}", status_code=204, dependencies=[Depends(require_manager)]
)
async def detach_job_assessment(
    job_id: int, attachment_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    await service.detach_job_assessment(db, job_id, attachment_id)
