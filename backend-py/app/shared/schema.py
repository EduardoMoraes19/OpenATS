"""Shared Pydantic base for API schemas.

The frontend (frontend/) is a TypeScript codebase and every field name it
expects - and the TS backend actually sent - is camelCase (Drizzle maps
snake_case DB columns to camelCase TS properties on the way out, e.g.
`firstName: varchar("first_name")`). FastAPI defaults
`response_model_by_alias=True`, so giving every schema a camelCase alias
generator here is enough to make every response camelCase automatically,
with zero per-route changes. `populate_by_name=True` keeps snake_case
constructible too, which is convenient for internal Python code and tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiOutModel(ApiModel):
    """For response schemas built from ORM objects via `.model_validate(obj)`."""

    model_config = ConfigDict(from_attributes=True)


def _to_utc_iso_z(value: datetime) -> str:
    """Every `timestamp` column in this schema is WITHOUT TIME ZONE (see
    app/db/models/mixins.py) and always holds a UTC instant in practice, but
    Pydantic's default serializer emits a naive datetime with no offset at
    all (`"2026-12-01T15:00:00"`). The TS backend's `Date.toISOString()`
    always emits a `Z`-suffixed UTC string (`"2026-12-01T15:00:00.000Z"`),
    which the frontend's date parsing depends on - a bare, offset-less
    string is ambiguous and some JS `Date` parsers treat it as local time
    instead of UTC, shifting displayed times by the viewer's UTC offset.
    """
    if value.tzinfo is None:
        return value.isoformat(timespec="milliseconds") + "Z"
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_to_utc_iso_z, return_type=str, when_used="json")]
