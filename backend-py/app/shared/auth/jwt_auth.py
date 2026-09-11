"""Self-hosted JWT authentication: issuance, verification, and password
hashing. Modeled on labs-contaja's admin-auth pattern (apps/backend/src/
infrastructure/api/deps.py) rather than the original app's Asgardeo/WSO2
delegation - this project stores and checks passwords itself now.

This is the single source of truth for "who is making this request" - used
identically by the HTTP auth dependency (app/shared/auth/deps.py) and the
Socket.IO handshake (app/sockets/server.py), so the two transports can
never drift on who counts as authenticated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User
from app.settings import settings

AppRole = Literal["super_admin", "hiring_manager", "interviewer"]


class AuthError(Exception):
    """Carries an HTTP status alongside the message."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None
    is_active: bool
    role: AppRole


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(*, user_id: int, role: str, token_version: int) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "role": role, "tv": token_version, "exp": expires_at}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError subclasses (bad signature, expired, ...) for
    the caller to turn into a 401 - not caught here, matching deps.py's
    existing error-mapping shape."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


async def get_user_from_token(token: str, db: AsyncSession) -> AuthenticatedUser:
    """Decodes the JWT, loads the user it names, and checks it hasn't been
    invalidated (deactivated, or superseded by a logout/password change that
    bumped `token_version` since this token was issued)."""
    payload = decode_token(token)

    sub = payload.get("sub")
    if not sub:
        raise AuthError(401, "Invalid token: missing sub claim")

    try:
        user_id = int(sub)
    except ValueError as exc:
        raise AuthError(401, "Invalid token: malformed sub claim") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthError(401, "User not found")

    if not user.is_active:
        raise AuthError(403, "User account is deactivated")

    token_version = payload.get("tv", 0)
    if token_version != user.token_version:
        raise AuthError(401, "Session expired. Please log in again.")

    role = payload.get("role")
    if role not in ("super_admin", "hiring_manager", "interviewer"):
        raise AuthError(403, "No role assigned. Contact your administrator.")

    return AuthenticatedUser(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        role=role,
    )
