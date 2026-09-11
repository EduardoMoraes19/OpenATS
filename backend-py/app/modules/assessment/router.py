"""Equivalent to backend/src/modules/assessment/assessment.routes.ts."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.assessment import service
from app.modules.assessment.schemas import (
    AssessmentOut,
    AssessmentQuestionOut,
    CreateAssessmentIn,
    CreateAssessmentQuestionIn,
    UpdateAssessmentIn,
    UpdateAssessmentQuestionIn,
)
from app.shared.auth.deps import get_current_user, require_manager
from app.shared.auth.verify_token import AuthenticatedUser

router = APIRouter()


@router.get("", response_model=list[AssessmentOut])
async def list_assessments(db: AsyncSession = Depends(get_db)) -> list[AssessmentOut]:
    assessments = await service.list_assessments(db)
    return [AssessmentOut.model_validate(a) for a in assessments]


@router.post("", response_model=AssessmentOut, status_code=201, dependencies=[Depends(require_manager)])
async def create_assessment(
    body: CreateAssessmentIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentOut:
    assessment = await service.create_assessment(
        db,
        title=body.title,
        description=body.description,
        time_limit=body.time_limit,
        questions=[q.model_dump() for q in body.questions],
        created_by=user.id,
    )
    return AssessmentOut.model_validate(assessment)


@router.get("/{assessment_id}", response_model=AssessmentOut)
async def get_assessment(assessment_id: int, db: AsyncSession = Depends(get_db)) -> AssessmentOut:
    assessment = await service.get_assessment(db, assessment_id)
    return AssessmentOut.model_validate(assessment)


@router.put("/{assessment_id}", response_model=AssessmentOut, dependencies=[Depends(require_manager)])
async def update_assessment(
    assessment_id: int, body: UpdateAssessmentIn, db: AsyncSession = Depends(get_db)
) -> AssessmentOut:
    assessment = await service.update_assessment(db, assessment_id, data=body.model_dump(exclude_none=True))
    return AssessmentOut.model_validate(assessment)


@router.delete("/{assessment_id}", status_code=204, dependencies=[Depends(require_manager)])
async def delete_assessment(assessment_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_assessment(db, assessment_id)


@router.post(
    "/{assessment_id}/questions", response_model=AssessmentQuestionOut, status_code=201,
    dependencies=[Depends(require_manager)],
)
async def add_question(
    assessment_id: int, body: CreateAssessmentQuestionIn, db: AsyncSession = Depends(get_db)
) -> AssessmentQuestionOut:
    question = await service.add_question(db, assessment_id, data=body.model_dump())
    return AssessmentQuestionOut.model_validate(question)


@router.put(
    "/{assessment_id}/questions/{question_id}", response_model=AssessmentQuestionOut,
    dependencies=[Depends(require_manager)],
)
async def update_question(
    assessment_id: int, question_id: int, body: UpdateAssessmentQuestionIn, db: AsyncSession = Depends(get_db)
) -> AssessmentQuestionOut:
    data = body.model_dump(exclude={"options"}, exclude_none=True)
    options = [o.model_dump() for o in body.options] if body.options is not None else None
    question = await service.update_question(db, assessment_id, question_id, data=data, options=options)
    return AssessmentQuestionOut.model_validate(question)


@router.delete(
    "/{assessment_id}/questions/{question_id}", status_code=204, dependencies=[Depends(require_manager)]
)
async def delete_question(assessment_id: int, question_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_question(db, assessment_id, question_id)
