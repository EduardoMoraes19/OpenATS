"""Equivalent to backend/src/modules/hiring-team/hiring-team.service.ts."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.jobs import Job
from app.db.models.pipeline import JobHiringTeam
from app.db.models.users import User


async def list_members(db: AsyncSession, job_id: int) -> list[dict]:
    result = await db.execute(
        select(JobHiringTeam, User)
        .join(User, User.id == JobHiringTeam.user_id)
        .where(JobHiringTeam.job_id == job_id)
        .order_by(JobHiringTeam.added_at)
    )
    return [
        {
            "id": membership.id,
            "job_id": membership.job_id,
            "user_id": membership.user_id,
            "added_at": membership.added_at,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "avatar_url": user.avatar_url,
        }
        for membership, user in result.all()
    ]


async def is_member(db: AsyncSession, job_id: int, user_id: int) -> bool:
    result = await db.execute(
        select(JobHiringTeam.id).where(
            JobHiringTeam.job_id == job_id, JobHiringTeam.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None


async def add_member(db: AsyncSession, job_id: int, user_id: int) -> None:
    if await is_member(db, job_id, user_id):
        raise HTTPException(status_code=409, detail="User is already on the hiring team")
    db.add(JobHiringTeam(job_id=job_id, user_id=user_id))
    await db.commit()


async def remove_member(db: AsyncSession, job_id: int, user_id: int) -> None:
    job = await db.get(Job, job_id)
    if job is not None and job.created_by == user_id:
        raise HTTPException(status_code=403, detail="Cannot remove the job creator from the hiring team")

    result = await db.execute(
        select(JobHiringTeam).where(
            JobHiringTeam.job_id == job_id, JobHiringTeam.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="User is not on the hiring team")

    await db.delete(membership)
    await db.commit()
