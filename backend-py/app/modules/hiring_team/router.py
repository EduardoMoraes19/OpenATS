"""Mounted under /api/jobs/{job_id}/team by app/modules/job/router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.hiring_team import service
from app.modules.hiring_team.schemas import AddHiringTeamMemberIn, HiringTeamMemberOut
from app.shared.auth.deps import require_manager

router = APIRouter()


@router.get("", response_model=list[HiringTeamMemberOut])
async def list_members(job_id: int, db: AsyncSession = Depends(get_db)) -> list[HiringTeamMemberOut]:
    members = await service.list_members(db, job_id)
    return [HiringTeamMemberOut(**m) for m in members]


@router.post("", status_code=201, dependencies=[Depends(require_manager)])
async def add_member(
    job_id: int, body: AddHiringTeamMemberIn, db: AsyncSession = Depends(get_db)
) -> dict:
    await service.add_member(db, job_id, body.user_id)
    return {"success": True}


@router.delete("/{user_id}", status_code=204, dependencies=[Depends(require_manager)])
async def remove_member(job_id: int, user_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.remove_member(db, job_id, user_id)
