from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.db.models.enums import StageType
from app.shared.schema import ApiModel, ApiOutModel


class PipelineStageOut(ApiOutModel):
    id: int
    job_id: int
    name: str
    position: int
    stage_type: StageType
    source_template_id: int | None
    created_at: datetime
    updated_at: datetime



class CreatePipelineStageIn(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    stage_type: StageType = StageType.screening
    position: int | None = None


class UpdatePipelineStageIn(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    stage_type: StageType | None = None


class StagePositionIn(ApiModel):
    id: int
    position: int


class ReorderStagesIn(ApiModel):
    stages: list[StagePositionIn]
