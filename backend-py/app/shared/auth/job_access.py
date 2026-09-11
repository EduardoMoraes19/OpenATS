"""Hiring-team based authorization, equivalent to backend/src/shared/auth/job-access.ts.

Shared verbatim by the HTTP dependencies (deps.py) and the Socket.IO
handlers (app/sockets/server.py) - the "single source of truth" the TS
comment documents.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidates import Candidate
from app.db.models.pipeline import JobHiringTeam
from app.shared.auth.verify_token import AuthenticatedUser


def parse_room_id(value: object) -> int | None:
    """Coerces a string/number to a positive integer id; anything else is None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


async def can_access_job(db: AsyncSession, user: AuthenticatedUser, job_id: int) -> bool:
    """super_admin always passes (admins manage hiring teams, so requiring
    membership would lock them out); everyone else must be on job_hiring_team."""
    if user.role == "super_admin":
        return True
    result = await db.execute(
        select(JobHiringTeam.id).where(
            JobHiringTeam.job_id == job_id, JobHiringTeam.user_id == user.id
        )
    )
    return result.scalar_one_or_none() is not None


async def can_access_candidate(db: AsyncSession, user: AuthenticatedUser, candidate_id: int) -> bool:
    """A candidate's access follows its job - super_admin short-circuits first."""
    if user.role == "super_admin":
        return True
    result = await db.execute(select(Candidate.job_id).where(Candidate.id == candidate_id))
    job_id = result.scalar_one_or_none()
    if job_id is None:
        return False
    return await can_access_job(db, user, job_id)
