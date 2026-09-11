"""Mounted under /api/jobs/{job_id}/pipeline by app/modules/job/router.py,
equivalent to how job.routes.ts mounts pipeline.controller.ts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.pipeline import service
from app.modules.pipeline.schemas import (
    CreatePipelineStageIn,
    PipelineStageOut,
    ReorderStagesIn,
    UpdatePipelineStageIn,
)
from app.shared.auth.deps import require_manager

router = APIRouter()


@router.get("", response_model=list[PipelineStageOut])
async def list_stages(job_id: int, db: AsyncSession = Depends(get_db)) -> list[PipelineStageOut]:
    stages = await service.list_stages(db, job_id)
    return [PipelineStageOut.model_validate(s) for s in stages]


@router.post(
    "", response_model=PipelineStageOut, status_code=201, dependencies=[Depends(require_manager)]
)
async def create_stage(
    job_id: int, body: CreatePipelineStageIn, db: AsyncSession = Depends(get_db)
) -> PipelineStageOut:
    stage = await service.create_stage(
        db, job_id, name=body.name, stage_type=body.stage_type, position=body.position
    )
    return PipelineStageOut.model_validate(stage)


@router.post("/reorder", response_model=list[PipelineStageOut], dependencies=[Depends(require_manager)])
async def reorder_stages(
    job_id: int, body: ReorderStagesIn, db: AsyncSession = Depends(get_db)
) -> list[PipelineStageOut]:
    pairs = [(s.id, s.position) for s in body.stages]
    stages = await service.reorder_stages(db, job_id, pairs)
    return [PipelineStageOut.model_validate(s) for s in stages]


@router.put(
    "/{stage_id}", response_model=PipelineStageOut, dependencies=[Depends(require_manager)]
)
async def update_stage(
    job_id: int, stage_id: int, body: UpdatePipelineStageIn, db: AsyncSession = Depends(get_db)
) -> PipelineStageOut:
    stage = await service.update_stage(
        db, job_id, stage_id, name=body.name, stage_type=body.stage_type
    )
    return PipelineStageOut.model_validate(stage)


@router.delete("/{stage_id}", status_code=204, dependencies=[Depends(require_manager)])
async def delete_stage(job_id: int, stage_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_stage(db, job_id, stage_id)
