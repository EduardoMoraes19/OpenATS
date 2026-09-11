from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from app.shared.schema import ApiModel, ApiOutModel


class UserOut(ApiOutModel):
    id: int
    asgardeo_user_id: str
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime



class MeOut(ApiModel):
    id: int
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None
    role: str


class CreateUserIn(ApiModel):
    asgardeo_user_id: str = Field(min_length=1)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr


class UpdateUserIn(ApiModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = None
    is_active: bool | None = None
