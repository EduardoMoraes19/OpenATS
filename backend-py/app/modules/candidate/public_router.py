"""POST /public/jobs/:jobId/apply - equivalent to the apply handler in
public.routes.ts. Rate-limited to 5/15min, origin-gated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.candidate import service
from app.modules.candidate.router import signed_candidate_out
from app.modules.candidate.schemas import CandidateApplyIn, CandidateOut
from app.queues.cv_analysis.queue import request_cv_analysis
from app.shared.rate_limit import apply_limiter
from app.sockets.server import notify_candidate_applied

router = APIRouter()


@router.post(
    "/jobs/{job_id}/apply", response_model=CandidateOut, status_code=201,
    dependencies=[Depends(apply_limiter)],
)
async def apply_for_job(job_id: int, body: CandidateApplyIn, db: AsyncSession = Depends(get_db)) -> CandidateOut:
    try:
        candidate = await service.apply_for_job(
            db,
            job_id,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            phone=body.phone,
            resume_url=body.resume_url,
            custom_answers=[a.model_dump() for a in body.custom_answers],
        )
    except service.DuplicateApplicationError as exc:
        raise HTTPException(status_code=409, detail={"code": "DUPLICATE_APPLICATION"}) from exc

    await notify_candidate_applied(job_id)
    if candidate.resume_url:
        await request_cv_analysis(db, candidate_id=candidate.id, job_id=job_id, resume_url=candidate.resume_url)

    return signed_candidate_out(candidate)
