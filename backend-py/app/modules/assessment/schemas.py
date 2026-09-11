from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.db.models.enums import QuestionType
from app.shared.schema import ApiModel, ApiOutModel

_ASSESSMENT_QUESTION_TYPES = {QuestionType.short_answer, QuestionType.multiple_choice}


class QuestionOptionIn(ApiModel):
    label: str = Field(min_length=1, max_length=500)
    is_correct: bool = False
    position: int


class QuestionOptionOut(ApiOutModel):
    id: int
    label: str
    is_correct: bool
    position: int



class CreateAssessmentQuestionIn(ApiModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    question_type: QuestionType
    points: Decimal = Decimal("1")
    position: int
    options: list[QuestionOptionIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_options(self) -> CreateAssessmentQuestionIn:
        if self.question_type == QuestionType.multiple_choice and len(self.options) < 2:
            raise ValueError("multiple_choice questions need at least 2 options")
        return self


class UpdateAssessmentQuestionIn(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    question_type: QuestionType | None = None
    points: Decimal | None = None
    position: int | None = None
    options: list[QuestionOptionIn] | None = None


class AssessmentQuestionOut(ApiOutModel):
    id: int
    assessment_id: int
    title: str
    description: str | None
    question_type: QuestionType
    points: Decimal
    position: int
    created_at: datetime
    updated_at: datetime
    options: list[QuestionOptionOut] = Field(default_factory=list)



class CreateAssessmentIn(ApiModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    time_limit: int = Field(gt=0)
    questions: list[CreateAssessmentQuestionIn] = Field(default_factory=list)


class UpdateAssessmentIn(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    time_limit: int | None = Field(default=None, gt=0)


class AssessmentOut(ApiOutModel):
    id: int
    title: str
    description: str | None
    time_limit: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    questions: list[AssessmentQuestionOut] = Field(default_factory=list)

