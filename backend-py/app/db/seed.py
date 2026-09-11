"""Seeds pipeline_stage_templates - equivalent to backend/src/db/seed.ts.

Required on first setup for the app to function. Seeds only this one table
(7 rows, not 5 - see the row list below); company/users/departments are
created through the normal app flow, not by this script.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete

from app.db.base import session_scope
from app.db.models.enums import StageType
from app.db.models.pipeline import PipelineStageTemplate
from app.logging import get_logger

logger = get_logger(__name__)

_STAGE_TEMPLATES = [
    {"name": "Screening", "position": 1, "stage_type": StageType.screening, "is_deletable": False},
    {
        "name": "Screening Qualified",
        "position": 2,
        "stage_type": StageType.screening,
        "is_deletable": False,
    },
    {
        "name": "Screening Disqualified",
        "position": 3,
        "stage_type": StageType.screening,
        "is_deletable": False,
    },
    {"name": "Interviews", "position": 4, "stage_type": StageType.interview, "is_deletable": False},
    {
        "name": "Shortlisted",
        "position": 5,
        "stage_type": StageType.interview,
        "is_deletable": False,
    },
    {"name": "Offer", "position": 6, "stage_type": StageType.offer, "is_deletable": False},
    {"name": "Hired", "position": 7, "stage_type": StageType.offer, "is_deletable": False},
]


async def seed_pipeline_stage_templates() -> None:
    async with session_scope() as session:
        await session.execute(delete(PipelineStageTemplate))
        session.add_all(PipelineStageTemplate(**row) for row in _STAGE_TEMPLATES)
        await session.commit()
    logger.info("Seeded %d pipeline stage templates", len(_STAGE_TEMPLATES))


if __name__ == "__main__":
    asyncio.run(seed_pipeline_stage_templates())
