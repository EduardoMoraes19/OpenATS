"""Equivalent to backend/src/modules/user/user.routes.ts.

PUT /:id has authorization logic beyond a static role gate: a user may
always edit themselves, but only a super_admin may change `is_active` or
`role` - ported into the handler rather than a route dependency, matching
the TS controller.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.enums import AppRole
from app.modules.user import service
from app.modules.user.schemas import CreateUserIn, MeOut, UpdateUserIn, UserOut
from app.shared.auth.deps import get_current_user, require_admin, require_manager
from app.shared.auth.jwt_auth import AuthenticatedUser

router = APIRouter()


@router.get("", response_model=list[UserOut], dependencies=[Depends(require_manager)])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[UserOut]:
    users = await service.list_active_users(db)
    return [UserOut.model_validate(u) for u in users]


@router.get("/me", response_model=MeOut)
async def get_me(user: AuthenticatedUser = Depends(get_current_user)) -> MeOut:
    return MeOut(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        avatar_url=user.avatar_url,
        # `AuthenticatedUser.role` (app/shared/auth/jwt_auth.py) is typed as a
        # plain Literal - not the db-backed `AppRole` enum - since it's read off
        # the JWT claim, not the ORM row. Same values, different type; coerce
        # explicitly so this satisfies MeOut.role: AppRole under mypy.
        role=AppRole(user.role),
    )


@router.get("/{user_id}", response_model=UserOut, dependencies=[Depends(require_manager)])
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)) -> UserOut:
    user = await service.get_user(db, user_id)
    return UserOut.model_validate(user)


@router.post("", response_model=UserOut, status_code=201, dependencies=[Depends(require_admin)])
async def create_user(body: CreateUserIn, db: AsyncSession = Depends(get_db)) -> UserOut:
    user = await service.create_user(
        db,
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        password=body.password,
        role=body.role,
    )
    return UserOut.model_validate(user)


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UpdateUserIn,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    is_self = current_user.id == user_id
    is_admin = current_user.role == "super_admin"
    if not is_self and not is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    if body.is_active is not None and not is_admin:
        raise HTTPException(status_code=403, detail="Only an admin can change account status")
    if body.role is not None and not is_admin:
        raise HTTPException(status_code=403, detail="Only an admin can change account role")

    user = await service.update_user(
        db,
        user_id,
        first_name=body.first_name,
        last_name=body.last_name,
        avatar_url=body.avatar_url,
        is_active=body.is_active,
        role=body.role,
    )
    return UserOut.model_validate(user)


@router.delete("/{user_id}", response_model=UserOut)
async def deactivate_user(
    user_id: int,
    current_user: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    if current_user.id == user_id:
        raise HTTPException(status_code=403, detail="You cannot deactivate your own account")
    user = await service.deactivate_user(db, user_id)
    return UserOut.model_validate(user)
