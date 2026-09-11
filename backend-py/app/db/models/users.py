"""users - originally equivalent to backend/src/db/schema/users.ts, now
extended for local (self-hosted) authentication instead of Asgardeo.

`password_hash` and `token_version` back the JWT login/logout flow in
app/shared/auth/jwt_auth.py (bcrypt hash; token_version increments on
logout/password-change to invalidate all outstanding tokens for the user,
since a JWT is otherwise stateless). `role` was previously never persisted
(derived from the Asgardeo JWT on every request) - with no external IdP
there's nowhere else for it to live.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import AppRole, pg_enum
from app.db.models.mixins import TimestampsMixin


class User(Base, TimestampsMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AppRole] = mapped_column(pg_enum(AppRole, "app_role"), nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
