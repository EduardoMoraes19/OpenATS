"""Asgardeo JWT verification, role mapping, and JIT user provisioning.

Equivalent to backend/src/shared/auth/verify-token.ts. This is the single
source of truth for "who is making this request" - used identically by the
HTTP auth dependency (app/shared/auth/deps.py) and the Socket.IO handshake
(app/sockets/server.py), so the two transports can never drift on who
counts as authenticated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User
from app.settings import settings

AppRole = Literal["super_admin", "hiring_manager", "interviewer"]

_ROLE_PRECEDENCE: list[AppRole] = ["super_admin", "hiring_manager", "interviewer"]
_WSO2_ROLE_CLAIM = "http://wso2.org/claims/role"

_jwks_client = jwt.PyJWKClient(settings.asgardeo_jwks_url)


class AuthError(Exception):
    """Carries an HTTP status alongside the message, mirroring verify-token.ts's AuthError."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    asgardeo_user_id: str
    first_name: str
    last_name: str
    email: str
    avatar_url: str | None
    is_active: bool
    role: AppRole


def _normalize_role_name(value: str) -> str:
    """lowercase, underscores to spaces, collapse whitespace, trim - matches mapToAppRole's normalization."""
    normalized = value.strip().lower().replace("_", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def _collect_roles_from_payload(payload: dict[str, Any]) -> list[str]:
    """Reads `roles` (array or string) AND the WSO2 default role claim (array or
    comma-separated string), concatenated - port of collectRolesFromPayload."""
    roles: list[str] = []

    raw_roles = payload.get("roles")
    if isinstance(raw_roles, list):
        roles.extend(str(item).strip() for item in raw_roles if str(item).strip())
    elif isinstance(raw_roles, str) and raw_roles.strip():
        roles.append(raw_roles.strip())

    wso2_roles = payload.get(_WSO2_ROLE_CLAIM)
    if isinstance(wso2_roles, list):
        roles.extend(str(item).strip() for item in wso2_roles if str(item).strip())
    elif isinstance(wso2_roles, str) and wso2_roles.strip():
        roles.extend(part.strip() for part in wso2_roles.split(",") if part.strip())

    return roles


def _matches_role(normalized_claim: str, role: AppRole) -> bool:
    """Exact match OR suffix match on "/<role>" - never substring, to block things
    like "super_admin_readonly" from granting super_admin."""
    role_name = role.replace("_", " ")
    return normalized_claim == role_name or normalized_claim.endswith(f"/{role_name}")


def map_to_app_role(role_claims: list[str]) -> AppRole | None:
    """Precedence super_admin > hiring_manager > interviewer; first match wins."""
    normalized = [_normalize_role_name(claim) for claim in role_claims]
    for role in _ROLE_PRECEDENCE:
        if any(_matches_role(claim, role) for claim in normalized):
            return role
    return None


async def _find_or_provision_user(
    db: AsyncSession, *, sub: str, email: str, first_name: str, last_name: str
) -> User:
    """JIT provisioning, exact order: by sub, then by email (reconciling a
    changed sub), then insert new. Port of the resolveUser flow."""
    result = await db.execute(select(User).where(User.asgardeo_user_id == sub))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        user.asgardeo_user_id = sub
        await db.flush()
        return user

    try:
        user = User(
            asgardeo_user_id=sub,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )
        db.add(user)
        await db.flush()
        return user
    except Exception as exc:  # noqa: BLE001
        raise AuthError(500, "Failed to provision user") from exc


async def verify_access_token(token: str, db: AsyncSession) -> AuthenticatedUser:
    """Verifies the JWT, maps its role, and resolves/provisions the local user row.

    Raises AuthError for anything the caller should turn into a 4xx response;
    lets jwt.PyJWTError subclasses (bad signature, expired, ...) propagate for
    the caller to turn into a generic "Invalid or expired token" 401.
    """
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=settings.asgardeo_issuer,
        options={"verify_aud": False},
    )

    sub = payload.get("sub")
    if not sub:
        raise AuthError(401, "Invalid token: missing sub claim")

    email = payload.get("email")
    if not email:
        raise AuthError(403, "Token missing required email claim")

    role = map_to_app_role(_collect_roles_from_payload(payload))
    if role is None:
        raise AuthError(403, "No role assigned. Contact your administrator.")

    first_name = payload.get("given_name") or "Unknown"
    last_name = payload.get("family_name") or "User"

    user = await _find_or_provision_user(
        db, sub=sub, email=email, first_name=first_name, last_name=last_name
    )
    await db.commit()

    if not user.is_active:
        raise AuthError(403, "User account is deactivated")

    return AuthenticatedUser(
        id=user.id,
        asgardeo_user_id=user.asgardeo_user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        role=role,
    )
