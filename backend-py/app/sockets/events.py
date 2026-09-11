"""Redis pub/sub bridge from the arq worker process into Socket.IO broadcasts,
equivalent to server.ts's `subscribeToCvAnalysisEvents(event =>
socketService.emitCvAnalysisUpdate(event))` call at boot.

The channel name and JSON payload shape are identical to what
app/queues/cv_analysis/tasks.py publishes, so this is a drop-in replacement
for the old server.ts <-> worker.ts Redis bridge.
"""

from __future__ import annotations

import asyncio
import json

from redis.asyncio import Redis

from app.logging import get_logger
from app.queues.cv_analysis.events import CV_ANALYSIS_CHANNEL
from app.settings import settings
from app.sockets.server import emit_cv_analysis_update

logger = get_logger(__name__)

_subscriber_task: asyncio.Task | None = None


async def _listen() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(CV_ANALYSIS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                event = json.loads(message["data"])
                await emit_cv_analysis_update(
                    candidate_id=event["candidateId"],
                    job_id=event["jobId"],
                    status=event["status"],
                )
            except Exception:  # noqa: BLE001
                logger.exception("failed to process cv-analysis event: %s", message)
    finally:
        await pubsub.unsubscribe(CV_ANALYSIS_CHANNEL)
        await redis.aclose()


async def start_cv_analysis_bridge() -> None:
    global _subscriber_task
    _subscriber_task = asyncio.create_task(_listen())
    logger.info("cv-analysis event bridge started")


async def stop_cv_analysis_bridge() -> None:
    if _subscriber_task is not None:
        _subscriber_task.cancel()
