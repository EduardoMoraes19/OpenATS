"""templates - equivalent to backend/src/db/schema/templates.ts.

body_json holds either a raw HTML string (email templates) or a list of
ContentBlock dicts (event templates) - see app/modules/template/schemas.py
for the discriminated-union Pydantic shape the frontend's email builder
depends on. The DB column itself is untyped JSONB, matching the TS source.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import TemplateType, pg_enum
from app.db.models.mixins import TimestampsMixin


class Template(Base, TimestampsMixin):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[TemplateType] = mapped_column(
        pg_enum(TemplateType, "template_type"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_json: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
