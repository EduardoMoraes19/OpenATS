"""arq worker task + WorkerSettings for CV analysis, equivalent to
backend/src/queues/cv-analysis/worker.ts + backend/src/worker.ts.

Retry policy ported from BullMQ's `attempts: 3, backoff: {type:
"exponential", delay: 5000}` (5s, then 10s - BullMQ's formula is
`delay * 2^(attemptsMade-1)`). arq does not auto-retry arbitrary
exceptions, so this is done explicitly: intermediate attempts raise
`Retry(defer=...)` and touch nothing else; only the FINAL exhausted
attempt marks the DB row failed and publishes a "failed" event - mirroring
the TS worker's `exhausted = job.attemptsMade >= maxAttempts` gate, so
in-progress retries leave the row in "pending".
"""

from __future__ import annotations

from arq import Retry
from arq.typing import WorkerSettingsBase
from arq.worker import func as arq_func

from app.db.base import session_scope
from app.logging import get_logger
from app.modules.candidate import cv_analysis_service
from app.queues.cv_analysis.events import publish_cv_analysis_event
from app.queues.cv_analysis.queue import CV_ANALYSIS_QUEUE
from app.queues.cv_analysis.queue import redis_settings as get_redis_settings

logger = get_logger(__name__)

MAX_TRIES = 3
BASE_BACKOFF_SECONDS = 5


async def _analyze_cv(ctx: dict, *, candidate_id: int, job_id: int, resume_url: str) -> None:
    job_try: int = ctx["job_try"]

    try:
        async with session_scope() as db:
            await cv_analysis_service.run_analysis(db, candidate_id, job_id, resume_url)
    except Exception as exc:  # noqa: BLE001
        if job_try < MAX_TRIES:
            delay = BASE_BACKOFF_SECONDS * (2 ** (job_try - 1))
            logger.warning(
                "cv analysis attempt %s/%s failed for candidate=%s, retrying in %ss: %s",
                job_try, MAX_TRIES, candidate_id, delay, exc,
            )
            raise Retry(defer=delay) from exc

        logger.error("cv analysis exhausted retries for candidate=%s: %s", candidate_id, exc)
        async with session_scope() as db:
            await cv_analysis_service.mark_failed(db, candidate_id, str(exc))
        await publish_cv_analysis_event(candidate_id=candidate_id, job_id=job_id, status="failed")
        return

    await publish_cv_analysis_event(candidate_id=candidate_id, job_id=job_id, status="done")


analyze_cv = arq_func(_analyze_cv, name="analyze_cv", max_tries=MAX_TRIES)


class WorkerSettings(WorkerSettingsBase):
    functions = [analyze_cv]
    queue_name = CV_ANALYSIS_QUEUE
    redis_settings = get_redis_settings()
    max_jobs = 3  # concurrency, matching BullMQ's Worker concurrency: 3
