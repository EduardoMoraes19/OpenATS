"""State machine + orchestration for candidate CV analysis, equivalent to
backend/src/modules/candidate/cv-analysis.service.ts (minus the Gemini
calls themselves, which live in app/queues/cv_analysis/gemini_client.py,
and the scoring algorithm, in app/queues/cv_analysis/scoring.py).

Called by the arq task (app/queues/cv_analysis/tasks.py), not directly by
HTTP routes.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidates import CandidateCvAnalysis
from app.db.models.enums import CvAnalysisStatus
from app.db.models.jobs import Job, JobSkill
from app.logging import get_logger
from app.queues.cv_analysis.gemini_client import (
    generate_ai_summary,
    parse_cv_with_gemini,
    parse_jd_with_gemini,
)
from app.queues.cv_analysis.scoring import JobRequirements, score_cv
from app.shared.services import r2_service

logger = get_logger(__name__)


class CvNotAResumeError(Exception):
    pass


async def mark_pending(db: AsyncSession, candidate_id: int, job_id: int) -> None:
    stmt = (
        pg_insert(CandidateCvAnalysis)
        .values(candidate_id=candidate_id, job_id=job_id, status=CvAnalysisStatus.pending)
        .on_conflict_do_update(
            index_elements=["candidate_id"],
            set_={
                "job_id": job_id,
                "status": CvAnalysisStatus.pending,
                "match_score": None,
                "matched_skills": None,
                "missing_skills": None,
                "score_breakdown": None,
                "ai_summary": None,
                "extracted_text": None,
                "error_message": None,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()


async def mark_failed(db: AsyncSession, candidate_id: int, error_message: str) -> None:
    result = await db.execute(
        select(CandidateCvAnalysis).where(CandidateCvAnalysis.candidate_id == candidate_id)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        return
    analysis.status = CvAnalysisStatus.failed
    analysis.error_message = error_message
    await db.commit()


async def _job_requirements(db: AsyncSession, job_id: int) -> tuple[str | None, JobRequirements]:
    job = await db.get(Job, job_id)
    description = job.description if job else None

    skills_result = await db.execute(select(JobSkill.skill).where(JobSkill.job_id == job_id))
    skills = list(skills_result.scalars().all())

    if description:
        jd = await parse_jd_with_gemini(description)
        requirements = JobRequirements(
            skills=skills,
            min_experience_years=jd["minExperienceYears"],
            job_level=jd["jobLevel"],
            required_certifications=jd["requiredCertifications"],
        )
    else:
        requirements = JobRequirements(skills=skills)

    return description, requirements


async def run_analysis(db: AsyncSession, candidate_id: int, job_id: int, resume_url: str) -> None:
    key = r2_service.extract_key_from_url(resume_url)
    if key is None:
        raise ValueError(f"resume_url is not a valid R2 url: {resume_url}")
    pdf_bytes = await asyncio.to_thread(r2_service.download_file, key)

    parsed_cv, (description, job_requirements) = await asyncio.gather(
        parse_cv_with_gemini(pdf_bytes), _job_requirements(db, job_id)
    )

    if not parsed_cv.is_cv_or_resume or parsed_cv.confidence < 0.6:
        raise CvNotAResumeError(
            f"Uploaded document doesn't look like a CV/resume "
            f"(type: {parsed_cv.document_type}, confidence: {parsed_cv.confidence}). "
            f"Please upload a resume/CV PDF."
        )

    score_result = score_cv(parsed_cv, job_requirements)
    ai_summary = await generate_ai_summary(parsed_cv, job_requirements, score_result)

    result = await db.execute(
        select(CandidateCvAnalysis).where(CandidateCvAnalysis.candidate_id == candidate_id)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        analysis = CandidateCvAnalysis(candidate_id=candidate_id, job_id=job_id)
        db.add(analysis)

    analysis.status = CvAnalysisStatus.done
    analysis.match_score = Decimal(score_result.match_score)
    analysis.matched_skills = score_result.matched_skills
    analysis.missing_skills = score_result.missing_skills
    analysis.score_breakdown = {
        "skills": score_result.breakdown.skills,
        "experience": score_result.breakdown.experience,
        "level": score_result.breakdown.level,
        "certs": score_result.breakdown.certs,
    }
    analysis.ai_summary = ai_summary
    analysis.error_message = None
    await db.commit()
