"""Local (self-hosted) auth contracts: login/logout/change-password. New
module - replaces the Asgardeo delegation this project used to rely on, so
these shapes have no direct TS equivalent to mirror; password complexity
mirrors labs-contaja's admin_auth.py `validate_password_strength`
(apps/backend/src/infrastructure/api/routes/admin_auth.py), translated to
English to match this codebase's English-only error message convention.
"""

from __future__ import annotations

import re

from pydantic import EmailStr, Field, field_validator

from app.shared.schema import ApiModel


def validate_password_strength(password: str) -> str:
    """Minimum 12 characters, at least one uppercase letter, one lowercase
    letter, one digit, and one special character. Shared by ChangePasswordIn
    below and the create_admin bootstrap script so the rule lives in one
    place."""
    errors: list[str] = []
    if len(password) < 12:
        errors.append("at least 12 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("at least 1 uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("at least 1 lowercase letter")
    if not re.search(r"\d", password):
        errors.append("at least 1 digit")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+\[\]\\;'/`~]", password):
        errors.append("at least 1 special character")
    if errors:
        raise ValueError("Weak password: requires " + ", ".join(errors))
    return password


class LoginIn(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1)


class AuthUserOut(ApiModel):
    """Mirrors app/modules/user/schemas.py's MeOut - the user shape returned
    alongside the access token on login."""

    id: int
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None
    role: str


class LoginOut(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserOut


class ChangePasswordIn(ApiModel):
    current_password: str = Field(min_length=1)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _check_strength(cls, value: str) -> str:
        return validate_password_strength(value)


class MessageOut(ApiModel):
    message: str
