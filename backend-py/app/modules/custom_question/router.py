"""Mounted under /api/jobs/{job_id}/questions by app/modules/job/router.py
with mergeParams-equivalent path param propagation (job_id comes from the
parent router's path prefix)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.custom_question import service
from app.modules.custom_question.schemas import (
    AssessmentAttachmentIn,
    AssessmentAttachmentOut,
    CreateCustomQuestionIn,
    CustomQuestionOut,
    UpdateCustomQuestionIn,
)
from app.shared.auth.deps import require_manager

router = APIRouter()


@router.get("", response_model=list[CustomQuestionOut])
async def list_questions(job_id: int, db: AsyncSession = Depends(get_db)) -> list[CustomQuestionOut]:
    questions = await service.list_questions(db, job_id)
    return [CustomQuestionOut.model_validate(q) for q in questions]


@router.post(
    "", response_model=CustomQuestionOut, status_code=201, dependencies=[Depends(require_manager)]
)
async def create_question(
    job_id: int, body: CreateCustomQuestionIn, db: AsyncSession = Depends(get_db)
) -> CustomQuestionOut:
    question = await service.create_question(
        db,
        job_id,
        title=body.title,
        question_type=body.question_type,
        is_required=body.is_required,
        position=body.position,
        options=[o.model_dump() for o in body.options],
    )
    return CustomQuestionOut.model_validate(question)


@router.put(
    "/{question_id}", response_model=CustomQuestionOut, dependencies=[Depends(require_manager)]
)
async def update_question(
    job_id: int, question_id: int, body: UpdateCustomQuestionIn, db: AsyncSession = Depends(get_db)
) -> CustomQuestionOut:
    data = body.model_dump(exclude={"options"}, exclude_none=True)
    options = [o.model_dump() for o in body.options] if body.options is not None else None
    question = await service.update_question(db, job_id, question_id, data=data, options=options)
    return CustomQuestionOut.model_validate(question)


@router.delete("/{question_id}", status_code=204, dependencies=[Depends(require_manager)])
async def delete_question(job_id: int, question_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_question(db, job_id, question_id)


@router.get("/assessment-attachment", response_model=AssessmentAttachmentOut | None)
async def get_assessment_attachment(
    job_id: int, db: AsyncSession = Depends(get_db)
) -> AssessmentAttachmentOut | None:
    attachment = await service.get_assessment_attachment(db, job_id)
    return AssessmentAttachmentOut.model_validate(attachment) if attachment else None


@router.post(
    "/assessment-attachment", response_model=AssessmentAttachmentOut,
    dependencies=[Depends(require_manager)],
)
async def attach_assessment(
    job_id: int, body: AssessmentAttachmentIn, db: AsyncSession = Depends(get_db)
) -> AssessmentAttachmentOut:
    attachment = await service.attach_assessment(
        db, job_id, assessment_id=body.assessment_id, trigger_stage_id=body.trigger_stage_id
    )
    return AssessmentAttachmentOut.model_validate(attachment)


@router.delete(
    "/assessment-attachment/{stage_id}", status_code=204, dependencies=[Depends(require_manager)]
)
async def detach_assessment(job_id: int, stage_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.detach_assessment(db, job_id, stage_id)
