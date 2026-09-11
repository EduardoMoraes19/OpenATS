from __future__ import annotations

from pydantic import Field

from app.shared.schema import ApiModel


class AllowedOriginsOut(ApiModel):
    # Wire field is "origins" (no underscore, so the alias generator is a
    # no-op) - page-settings.controller.ts returns {"data": {"origins": [...]}},
    # not "allowedOrigins".
    origins: list[str]


class AllowedOriginsIn(ApiModel):
    origins: list[str] = Field(max_length=50)
