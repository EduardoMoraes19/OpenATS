"""GET /public/jobs, /public/jobs/:id, /public/jobs/:jobId/questions -
equivalent to the job handlers in public.routes.ts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.enums import JobStatus
from app.db.models.jobs import Job
from app.modules.custom_question import service as custom_question_service
from app.modules.custom_question.schemas import CustomQuestionOut
from app.modules.job import service as job_service
from app.modules.job.schemas import PublicJobOut

router = APIRouter()


@router.get("/jobs", response_model=list[PublicJobOut])
async def list_published_jobs(db: AsyncSession = Depends(get_db)) -> list[PublicJobOut]:
    result = await db.execute(
        select(Job).where(Job.status == JobStatus.published).order_by(Job.created_at.desc())
    )
    jobs = list(result.scalars().all())
    out = []
    for job in jobs:
        skills = await job_service.get_job_skills(db, job.id)
        out.append(PublicJobOut(**{**_job_dict(job), "skills": skills}))
    return out


def _job_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "slug": job.slug,
        "title": job.title,
        "department_id": job.department_id,
        "employment_type": job.employment_type,
        "location": job.location,
        "description": job.description,
        "salary_type": job.salary_type,
        "currency": job.currency,
        "pay_frequency": job.pay_frequency,
        "salary_fixed": job.salary_fixed,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
    }


@router.get("/jobs/{job_id}", response_model=PublicJobOut)
async def get_published_job(job_id: int, db: AsyncSession = Depends(get_db)) -> PublicJobOut:
    job = await job_service.get_job_by_id(db, job_id)
    if job.status != JobStatus.published:
        raise HTTPException(status_code=404, detail="Job not found")
    skills = await job_service.get_job_skills(db, job.id)
    return PublicJobOut(**{**_job_dict(job), "skills": skills})


@router.get("/jobs/{job_id}/questions", response_model=list[CustomQuestionOut])
async def get_public_job_questions(
    job_id: int, db: AsyncSession = Depends(get_db)
) -> list[CustomQuestionOut]:
    questions = await custom_question_service.list_questions(db, job_id)
    return [CustomQuestionOut.model_validate(q) for q in questions]
