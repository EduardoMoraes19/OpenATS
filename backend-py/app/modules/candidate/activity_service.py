"""Append-only candidate activity log, equivalent to
backend/src/modules/candidate/candidate-activity.service.ts.

`create()` takes the caller's own AsyncSession so it composes inside
whatever transaction the caller (offer.service, candidate.service, ...) is
already running, matching the TS version's optional-transaction-handle
parameter.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidate_activities import CandidateActivity
from app.db.models.enums import CandidateActivityType


async def create(
    db: AsyncSession,
    *,
    candidate_id: int,
    job_id: int,
    event_type: CandidateActivityType,
    offer_id: int | None = None,
    stage_id: int | None = None,
    actor_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> CandidateActivity:
    activity = CandidateActivity(
        candidate_id=candidate_id,
        job_id=job_id,
        offer_id=offer_id,
        stage_id=stage_id,
        actor_id=actor_id,
        event_type=event_type,
        metadata_=metadata,
    )
    db.add(activity)
    await db.flush()
    return activity
