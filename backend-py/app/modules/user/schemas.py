from __future__ import annotations

from pydantic import EmailStr, Field, field_validator

from app.db.models.enums import AppRole
from app.modules.auth.schemas import validate_password_strength
from app.shared.schema import ApiModel, ApiOutModel, UtcDatetime


class UserOut(ApiOutModel):
    id: int
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None
    role: AppRole
    is_active: bool
    created_at: UtcDatetime
    updated_at: UtcDatetime



class MeOut(ApiModel):
    id: int
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None
    role: AppRole


class CreateUserIn(ApiModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str
    role: AppRole

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class UpdateUserIn(ApiModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = None
    is_active: bool | None = None
    role: AppRole | None = None
