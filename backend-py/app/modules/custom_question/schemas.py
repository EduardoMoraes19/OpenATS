from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.db.models.enums import QuestionType
from app.shared.schema import ApiModel, ApiOutModel

_OPTION_BASED_TYPES = {QuestionType.checkbox, QuestionType.radio}


class QuestionOptionIn(ApiModel):
    label: str = Field(min_length=1, max_length=500)
    is_correct: bool = False
    position: int


class QuestionOptionOut(ApiOutModel):
    id: int
    label: str
    is_correct: bool
    position: int



class CreateCustomQuestionIn(ApiModel):
    title: str = Field(min_length=1, max_length=500)
    question_type: QuestionType
    is_required: bool = False
    position: int
    options: list[QuestionOptionIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_options(self) -> CreateCustomQuestionIn:
        if self.question_type in _OPTION_BASED_TYPES and len(self.options) < 2:
            raise ValueError("checkbox/radio questions need at least 2 options")
        return self


class UpdateCustomQuestionIn(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    question_type: QuestionType | None = None
    is_required: bool | None = None
    position: int | None = None
    options: list[QuestionOptionIn] | None = None


class CustomQuestionOut(ApiOutModel):
    id: int
    job_id: int
    title: str
    question_type: QuestionType
    is_required: bool
    position: int
    created_at: datetime
    updated_at: datetime
    options: list[QuestionOptionOut] = Field(default_factory=list)



class AssessmentAttachmentIn(ApiModel):
    assessment_id: int
    trigger_stage_id: int


class AssessmentAttachmentOut(ApiOutModel):
    id: int
    job_id: int
    assessment_id: int
    trigger_stage_id: int
    created_at: datetime

