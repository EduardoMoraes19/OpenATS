"""Redis pub/sub publisher for CV-analysis completion events, equivalent to
backend/src/queues/cv-analysis/events.ts's `publishCvAnalysisEvent`.

The subscriber side (bridging into a Socket.IO broadcast) lives in
app/sockets/events.py, in the API process - this module is used by the arq
worker process, which has no Socket.IO server of its own.
"""

from __future__ import annotations

import json

from redis.asyncio import Redis

from app.settings import settings

CV_ANALYSIS_CHANNEL = "cv-analysis:events"

_publisher = Redis.from_url(settings.redis_url, decode_responses=True)


async def publish_cv_analysis_event(*, candidate_id: int, job_id: int, status: str) -> None:
    payload = {"candidateId": candidate_id, "jobId": job_id, "status": status}
    await _publisher.publish(CV_ANALYSIS_CHANNEL, json.dumps(payload))
