"""Equivalent to backend/src/modules/custom-question/custom-question.service.ts."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.assessments import (
    JobAssessmentAttachment,
    JobCustomQuestion,
    JobCustomQuestionOption,
)
from app.db.models.enums import QuestionType
from app.db.models.pipeline import JobPipelineStage


async def list_questions(db: AsyncSession, job_id: int) -> list[JobCustomQuestion]:
    result = await db.execute(
        select(JobCustomQuestion)
        .options(selectinload(JobCustomQuestion.options))
        .where(JobCustomQuestion.job_id == job_id)
        .order_by(JobCustomQuestion.position)
    )
    return list(result.scalars().unique().all())


async def create_question(
    db: AsyncSession,
    job_id: int,
    *,
    title: str,
    question_type: QuestionType,
    is_required: bool,
    position: int,
    options: list[dict],
) -> JobCustomQuestion:
    question = JobCustomQuestion(
        job_id=job_id, title=title, question_type=question_type, is_required=is_required, position=position
    )
    db.add(question)
    await db.flush()
    for option in options:
        db.add(JobCustomQuestionOption(question_id=question.id, **option))
    await db.commit()
    await db.refresh(question, attribute_names=["options"])
    return question


async def _get_question(db: AsyncSession, job_id: int, question_id: int) -> JobCustomQuestion:
    # populate_existing=True: forces the loader options below to apply even
    # if this question is already in the session's identity map from an
    # earlier query in the same request (see assessment/service.py for the
    # bug this pattern otherwise causes).
    question = await db.get(
        JobCustomQuestion,
        question_id,
        options=[selectinload(JobCustomQuestion.options)],
        populate_existing=True,
    )
    if question is None or question.job_id != job_id:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


async def update_question(
    db: AsyncSession, job_id: int, question_id: int, *, data: dict, options: list[dict] | None
) -> JobCustomQuestion:
    question = await _get_question(db, job_id, question_id)
    for key, value in data.items():
        setattr(question, key, value)

    if options is not None:
        await db.execute(
            delete(JobCustomQuestionOption).where(JobCustomQuestionOption.question_id == question_id)
        )
        for option in options:
            db.add(JobCustomQuestionOption(question_id=question_id, **option))

    await db.commit()
    await db.refresh(question, attribute_names=["options"])
    return question


async def delete_question(db: AsyncSession, job_id: int, question_id: int) -> None:
    question = await _get_question(db, job_id, question_id)
    await db.delete(question)
    await db.commit()


async def get_assessment_attachment(db: AsyncSession, job_id: int) -> JobAssessmentAttachment | None:
    result = await db.execute(
        select(JobAssessmentAttachment).where(JobAssessmentAttachment.job_id == job_id)
    )
    return result.scalar_one_or_none()


async def attach_assessment(
    db: AsyncSession, job_id: int, *, assessment_id: int, trigger_stage_id: int
) -> JobAssessmentAttachment:
    stage = await db.get(JobPipelineStage, trigger_stage_id)
    if stage is None or stage.job_id != job_id:
        raise HTTPException(status_code=400, detail="Stage does not belong to this job")

    stmt = (
        pg_insert(JobAssessmentAttachment)
        .values(job_id=job_id, assessment_id=assessment_id, trigger_stage_id=trigger_stage_id)
        .on_conflict_do_update(
            index_elements=["job_id", "trigger_stage_id"],
            set_={"assessment_id": assessment_id},
        )
        .returning(JobAssessmentAttachment)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


async def detach_assessment(db: AsyncSession, job_id: int, stage_id: int) -> None:
    await db.execute(
        delete(JobAssessmentAttachment).where(
            JobAssessmentAttachment.job_id == job_id,
            JobAssessmentAttachment.trigger_stage_id == stage_id,
        )
    )
    await db.commit()
