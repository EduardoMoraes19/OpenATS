"""Equivalent to backend/src/modules/user/user.service.ts."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User


async def list_active_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.first_name))
    return list(result.scalars().all())


async def get_user(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def create_user(
    db: AsyncSession, *, asgardeo_user_id: str, first_name: str, last_name: str, email: str
) -> User:
    """Reactivates a soft-deleted row matching email OR asgardeo_user_id
    instead of duplicate-inserting - port of user.service.ts's create()."""
    result = await db.execute(
        select(User).where(
            (User.email == email) | (User.asgardeo_user_id == asgardeo_user_id)
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.asgardeo_user_id = asgardeo_user_id
        existing.first_name = first_name
        existing.last_name = last_name
        existing.email = email
        existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        return existing

    user = User(
        asgardeo_user_id=asgardeo_user_id, first_name=first_name, last_name=last_name, email=email
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
    await db.commit()
    await db.refresh(user)
    return user


async def deactivate_user(db: AsyncSession, user_id: int) -> User:
    user = await get_user(db, user_id)
    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user
