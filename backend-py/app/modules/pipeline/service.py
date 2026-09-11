"""Equivalent to backend/src/modules/pipeline/pipeline.service.ts."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidates import CandidateStageHistory
from app.db.models.enums import StageType
from app.db.models.pipeline import JobPipelineStage
from app.shared.db_errors import is_unique_violation


async def list_stages(db: AsyncSession, job_id: int) -> list[JobPipelineStage]:
    result = await db.execute(
        select(JobPipelineStage)
        .where(JobPipelineStage.job_id == job_id)
        .order_by(JobPipelineStage.position)
    )
    return list(result.scalars().all())


async def create_stage(
    db: AsyncSession, job_id: int, *, name: str, stage_type: StageType, position: int | None
) -> JobPipelineStage:
    if position is None:
        max_position = (
            await db.execute(
                select(func.max(JobPipelineStage.position)).where(
                    JobPipelineStage.job_id == job_id
                )
            )
        ).scalar_one()
        position = (max_position or 0) + 1

    stage = JobPipelineStage(job_id=job_id, name=name, stage_type=stage_type, position=position)
    db.add(stage)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_unique_violation(exc):
            # Position conflict - fall back to append-at-end.
            max_position = (
                await db.execute(
                    select(func.max(JobPipelineStage.position)).where(
                        JobPipelineStage.job_id == job_id
                    )
                )
            ).scalar_one()
            stage = JobPipelineStage(
                job_id=job_id, name=name, stage_type=stage_type, position=(max_position or 0) + 1
            )
            db.add(stage)
            await db.commit()
        else:
            raise
    await db.refresh(stage)
    return stage


async def update_stage(
    db: AsyncSession, job_id: int, stage_id: int, *, name: str | None, stage_type: StageType | None
) -> JobPipelineStage:
    stage = await db.get(JobPipelineStage, stage_id)
    if stage is None or stage.job_id != job_id:
        raise HTTPException(status_code=404, detail="Pipeline stage not found")
    if name is not None:
        stage.name = name
    if stage_type is not None:
        stage.stage_type = stage_type
    await db.commit()
    await db.refresh(stage)
    return stage


async def reorder_stages(
    db: AsyncSession, job_id: int, stages: list[tuple[int, int]]
) -> list[JobPipelineStage]:
    """Two-phase update: first push all positions negative (by -id) to dodge
    the (job_id, position) unique constraint, then apply the real target
    positions - port of pipeline.service.ts's reorder(). `stages` is a list
    of (id, position) pairs, applied in the given order; the returned list
    mirrors only those stages, in that same order - not the full pipeline."""
    for stage_id, _position in stages:
        await db.execute(
            update(JobPipelineStage)
            .where(JobPipelineStage.id == stage_id, JobPipelineStage.job_id == job_id)
            .values(position=-stage_id)
        )

    results: list[JobPipelineStage] = []
    for stage_id, position in stages:
        stmt = (
            update(JobPipelineStage)
            .where(JobPipelineStage.id == stage_id, JobPipelineStage.job_id == job_id)
            .values(position=position)
            .returning(JobPipelineStage)
        )
        updated = (await db.execute(stmt)).scalar_one_or_none()
        if updated is not None:
            results.append(updated)

    await db.commit()
    for stage in results:
        await db.refresh(stage)
    return results


async def delete_stage(db: AsyncSession, job_id: int, stage_id: int) -> None:
    stage = await db.get(JobPipelineStage, stage_id)
    if stage is None or stage.job_id != job_id:
        raise HTTPException(status_code=404, detail="Pipeline stage not found")

    in_use = (
        await db.execute(
            select(CandidateStageHistory.id).where(CandidateStageHistory.stage_id == stage_id).limit(1)
        )
    ).scalar_one_or_none()
    if in_use is not None:
        raise HTTPException(
            status_code=409, detail="Cannot delete a stage that candidates have passed through"
        )

    await db.delete(stage)
    await db.commit()
