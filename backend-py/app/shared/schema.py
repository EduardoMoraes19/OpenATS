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

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiOutModel(ApiModel):
    """For response schemas built from ORM objects via `.model_validate(obj)`."""

    model_config = ConfigDict(from_attributes=True)
