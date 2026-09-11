"""Equivalent to the zod schemas in backend/src/modules/template/template.routes.ts.

`body_json` is a union: a raw HTML string for email templates, or a list of
typed ContentBlock dicts for event templates - the frontend's email-builder
component depends on this exact discriminated-union shape, so it is kept
as `Any` here (validated loosely) rather than over-constrained, matching
how loosely the TS `bodyJson: ContentBlock[] | string` type is enforced at
the API boundary (zod validates structurally, not by strict discriminant).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.db.models.enums import TemplateType
from app.shared.schema import ApiModel, ApiOutModel


class CreateTemplateIn(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    type: TemplateType
    subject: str = Field(min_length=1, max_length=500)
    body_json: Any = Field(default_factory=list)


class UpdateTemplateIn(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: TemplateType | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=500)
    body_json: Any = None


class TemplateOut(ApiOutModel):
    id: int
    name: str
    type: TemplateType
    subject: str
    body_json: Any
    created_by: int
    created_at: datetime
    updated_at: datetime
