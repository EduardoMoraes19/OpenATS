"""Equivalent to backend/src/modules/user/user.service.ts.

Users are only ever created explicitly by an admin via `POST /api/users`
now - there is no external IdP triggering "first login" JIT provisioning,
so (unlike the original TS/Asgardeo version) `create_user` is a plain
insert, not a reconcile-by-email-or-external-id upsert.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import AppRole
from app.db.models.users import User
from app.shared.auth.jwt_auth import hash_password


async def list_active_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.first_name))
    return list(result.scalars().all())


async def get_user(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def create_user(
    db: AsyncSession,
    *,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    role: AppRole,
) -> User:
    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        token_version=0,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(
    db: AsyncSession,
    user_id: int,
    *,
    first_name: str | None,
    last_name: str | None,
    avatar_url: str | None,
    is_active: bool | None,
    role: AppRole | None,
) -> User:
    user = await get_user(db, user_id)
    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    if avatar_url is not None:
        user.avatar_url = avatar_url
    if is_active is not None:
        user.is_active = is_active
    if role is not None and role != user.role:
        # The JWT carries the role as a claim (see jwt_auth.create_access_token),
        # so an outstanding token for this user still asserts the OLD role.
        # Bumping token_version invalidates it immediately (get_user_from_token
        # rejects any token whose `tv` claim doesn't match), instead of letting
        # a demoted user keep acting under their previous role until it expires.
        user.role = role
        user.token_version += 1
    await db.commit()
    await db.refresh(user)
    return user


async def deactivate_user(db: AsyncSession, user_id: int) -> User:
    user = await get_user(db, user_id)
    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user
