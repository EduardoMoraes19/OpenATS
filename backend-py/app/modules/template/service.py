"""Equivalent to backend/src/modules/template/template.service.ts."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import TemplateType
from app.db.models.templates import Template


async def list_templates_all(db: AsyncSession) -> list[Template]:
    """Mirrors template.service.ts's `getAll`: every template, ordered
    ascending by createdAt (oldest first - unlike the paginated/getByType
    branches, which don't share this ordering)."""
    result = await db.execute(select(Template).order_by(Template.created_at.asc()))
    return list(result.scalars().all())


async def list_templates_by_type(db: AsyncSession, *, type_: TemplateType) -> list[Template]:
    """Mirrors template.service.ts's `getByType`: filtered, no explicit
    ordering."""
    result = await db.execute(select(Template).where(Template.type == type_))
    return list(result.scalars().all())


async def list_templates_paginated(
    db: AsyncSession, *, type_: TemplateType | None, page: int, limit: int, search: str | None
) -> tuple[list[Template], int]:
    """Mirrors template.service.ts's `getPaginated`."""
    query = select(Template)
    count_query = select(func.count()).select_from(Template)

    if search:
        pattern = f"%{search}%"
        query = query.where(Template.name.ilike(pattern))
        count_query = count_query.where(Template.name.ilike(pattern))

    if type_ is not None:
        query = query.where(Template.type == type_)
        count_query = count_query.where(Template.type == type_)

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Template.created_at.desc()).offset((page - 1) * limit).limit(limit)
    templates = list((await db.execute(query)).scalars().all())
    return templates, total


async def get_template(db: AsyncSession, template_id: int) -> Template:
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


async def create_template(db: AsyncSession, *, data: dict, created_by: int) -> Template:
    template = Template(created_by=created_by, **data)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def update_template(db: AsyncSession, template_id: int, *, data: dict) -> Template:
    template = await get_template(db, template_id)
    for key, value in data.items():
        setattr(template, key, value)
    await db.commit()
    await db.refresh(template)
    return template


async def delete_template(db: AsyncSession, template_id: int) -> None:
    template = await get_template(db, template_id)
    await db.delete(template)
    await db.commit()


async def bulk_delete_templates(db: AsyncSession, template_ids: list[int]) -> None:
    await db.execute(delete(Template).where(Template.id.in_(template_ids)))
    await db.commit()
