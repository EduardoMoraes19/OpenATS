"""Local (self-hosted) auth endpoints - login/logout/change-password.
New module, replacing the Asgardeo OIDC delegation this project used to
rely on. Modeled on labs-contaja's admin auth routes
(apps/backend/src/infrastructure/api/routes/admin_auth.py).

POST /login is intentionally NOT gated by get_current_user: it is mounted
directly on the ASGI app in app/main.py (`fastapi_app.include_router(...,
prefix="/api/auth")`), as a SIBLING of `api_router` rather than included
inside it, because `api_router` applies `get_current_user` to every route
in its group (see app/routes/api_router.py) - nesting this router there
would make /login require a valid token to reach /login, a lockout bug.
/logout and /change-password still require an authenticated caller, but
that is declared per-route below via `Depends(get_current_user)`, not
inherited from a router-group dependency.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.users import User
from app.logging import get_logger
from app.modules.auth.schemas import AuthUserOut, ChangePasswordIn, LoginIn, LoginOut, MessageOut
from app.settings import settings
from app.shared.auth.deps import get_current_user
from app.shared.auth.jwt_auth import (
    AuthenticatedUser,
    create_access_token,
    hash_password,
    verify_password,
)
from app.shared.rate_limit import auth_change_password_limiter, auth_login_limiter

logger = get_logger(__name__)

router = APIRouter()


@router.post("/login", response_model=LoginOut, dependencies=[Depends(auth_login_limiter)])
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)) -> LoginOut:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash) or not user.is_active:
        # Generic message on purpose - never reveal whether the email
        # exists, to avoid user enumeration (matches labs-contaja's
        # admin_login non-specific error).
        logger.warning("login failed for email=%s", body.email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(
        user_id=user.id, role=user.role.value, token_version=user.token_version
    )

    return LoginOut(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user=AuthUserOut(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            avatar_url=user.avatar_url,
            role=user.role.value,
        ),
    )


@router.post("/logout", response_model=MessageOut)
async def logout(
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MessageOut:
    """Bumps token_version, invalidating every outstanding JWT for this
    user - including the one used to call this endpoint and any other
    active session - not just clearing client-side state."""
    db_user = await db.get(User, user.id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    db_user.token_version += 1
    await db.commit()

    return MessageOut(message="Logged out successfully")


@router.post(
    "/change-password",
    response_model=MessageOut,
    # get_current_user must be listed here, before the rate limiter: FastAPI
    # resolves decorator-level `dependencies=[]` before the endpoint's own
    # parameter dependencies, so without this the limiter would run first,
    # find `request.state.user` unset, and key by IP instead of user id
    # (verified empirically - decorator-level deps run strictly before
    # parameter-level ones). The `user: ... = Depends(get_current_user)`
    # parameter below is a second reference to the same callable; FastAPI
    # caches it per-request, so it only actually executes once.
    dependencies=[Depends(get_current_user), Depends(auth_change_password_limiter)],
)
async def change_password(
    body: ChangePasswordIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    db_user = await db.get(User, user.id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(body.current_password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    db_user.password_hash = hash_password(body.new_password)
    db_user.token_version += 1
    await db.commit()

    return MessageOut(message="Password changed successfully. Please log in again.")
