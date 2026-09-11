"""Equivalent to backend/src/modules/assessment/assessment.service.ts."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.assessments import Assessment, AssessmentQuestion, AssessmentQuestionOption


async def list_assessments(db: AsyncSession) -> list[Assessment]:
    result = await db.execute(select(Assessment).order_by(Assessment.created_at.desc()))
    return list(result.scalars().all())


async def get_assessment(db: AsyncSession, assessment_id: int) -> Assessment:
    # populate_existing=True: without it, db.get() returns the Python object
    # already in the session's identity map as-is (e.g. right after an
    # insert earlier in the same session) without applying these loader
    # options, leaving `questions`/`options` unloaded.
    assessment = await db.get(
        Assessment,
        assessment_id,
        options=[selectinload(Assessment.questions).selectinload(AssessmentQuestion.options)],
        populate_existing=True,
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


async def create_assessment(
    db: AsyncSession, *, title: str, description: str | None, time_limit: int, questions: list[dict], created_by: int
) -> Assessment:
    assessment = Assessment(title=title, description=description, time_limit=time_limit, created_by=created_by)
    db.add(assessment)
    await db.flush()

    for question_data in questions:
        options = question_data.pop("options", [])
        question = AssessmentQuestion(assessment_id=assessment.id, **question_data)
        db.add(question)
        await db.flush()
        for option in options:
            db.add(AssessmentQuestionOption(question_id=question.id, **option))

    await db.commit()
    return await get_assessment(db, assessment.id)


async def update_assessment(db: AsyncSession, assessment_id: int, *, data: dict) -> Assessment:
    assessment = await get_assessment(db, assessment_id)
    for key, value in data.items():
        setattr(assessment, key, value)
    await db.commit()
    return await get_assessment(db, assessment_id)


async def delete_assessment(db: AsyncSession, assessment_id: int) -> None:
    assessment = await get_assessment(db, assessment_id)
    await db.delete(assessment)
    await db.commit()


async def add_question(db: AsyncSession, assessment_id: int, *, data: dict) -> AssessmentQuestion:
    await get_assessment(db, assessment_id)
    options = data.pop("options", [])
    question = AssessmentQuestion(assessment_id=assessment_id, **data)
    db.add(question)
    await db.flush()
    for option in options:
        db.add(AssessmentQuestionOption(question_id=question.id, **option))
    await db.commit()
    await db.refresh(question, attribute_names=["options"])
    return question


async def _get_question(db: AsyncSession, assessment_id: int, question_id: int) -> AssessmentQuestion:
    question = await db.get(
        AssessmentQuestion, question_id, options=[selectinload(AssessmentQuestion.options)]
    )
    if question is None or question.assessment_id != assessment_id:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


async def update_question(
    db: AsyncSession, assessment_id: int, question_id: int, *, data: dict, options: list[dict] | None
) -> AssessmentQuestion:
    question = await _get_question(db, assessment_id, question_id)
    for key, value in data.items():
        setattr(question, key, value)

    if options is not None:
        await db.execute(
            delete(AssessmentQuestionOption).where(AssessmentQuestionOption.question_id == question_id)
        )
        for option in options:
            db.add(AssessmentQuestionOption(question_id=question_id, **option))

    await db.commit()
    await db.refresh(question, attribute_names=["options"])
    return question


async def delete_question(db: AsyncSession, assessment_id: int, question_id: int) -> None:
    question = await _get_question(db, assessment_id, question_id)
    await db.delete(question)
    await db.commit()
