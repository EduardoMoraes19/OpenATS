"""arq job producer for CV analysis, equivalent to
backend/src/queues/cv-analysis/queue.ts.

`request_cv_analysis` marks the analysis pending in the DB *before*
enqueuing, exactly matching requestCvAnalysis()'s ordering in the TS code.
"""

from __future__ import annotations

from urllib.parse import urlparse

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.candidate import cv_analysis_service
from app.settings import settings

CV_ANALYSIS_QUEUE = "cv-analysis"

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    parsed = urlparse(settings.redis_url)
    return RedisSettings(host=parsed.hostname or "localhost", port=parsed.port or 6379)


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def request_cv_analysis(db: AsyncSession, *, candidate_id: int, job_id: int, resume_url: str) -> None:
    await cv_analysis_service.mark_pending(db, candidate_id, job_id)
    pool = await get_pool()
    await pool.enqueue_job(
        "analyze_cv",
        candidate_id=candidate_id,
        job_id=job_id,
        resume_url=resume_url,
        _queue_name=CV_ANALYSIS_QUEUE,
    )
