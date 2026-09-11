"""Equivalent to backend/src/modules/company/company.service.ts."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.company import Company, Department
from app.shared.cache import TtlCache
from app.shared.db_errors import is_foreign_key_violation, is_unique_violation

_departments_cache = TtlCache(ttl_seconds=300)


async def get_company(db: AsyncSession) -> Company | None:
    result = await db.execute(select(Company).limit(1))
    return result.scalar_one_or_none()


async def upsert_company(db: AsyncSession, data: dict) -> Company:
    company = await get_company(db)
    if company is None:
        company = Company(**data)
        db.add(company)
    else:
        for key, value in data.items():
            setattr(company, key, value)
    await db.commit()
    await db.refresh(company)
    return company


async def list_departments(db: AsyncSession) -> list[Department]:
    cached = _departments_cache.get("all")
    if cached is not None:
        return cached
    result = await db.execute(select(Department).order_by(Department.name))
    departments = list(result.scalars().all())
    _departments_cache.set("all", departments)
    return departments


async def create_department(db: AsyncSession, name: str) -> Department:
    company = await get_company(db)
    if company is None:
        raise HTTPException(status_code=400, detail="Set up your company profile first")

    department = Department(company_id=company.id, name=name)
    db.add(department)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_unique_violation(exc):
            raise HTTPException(status_code=409, detail="A department with this name already exists") from exc
        raise
    await db.refresh(department)
    _departments_cache.clear()
    return department


async def update_department(db: AsyncSession, department_id: int, name: str) -> Department:
    department = await db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")

    department.name = name
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_unique_violation(exc):
            raise HTTPException(status_code=409, detail="A department with this name already exists") from exc
        raise
    await db.refresh(department)
    _departments_cache.clear()
    return department


async def delete_department(db: AsyncSession, department_id: int) -> None:
    department = await db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")

    await db.delete(department)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if is_foreign_key_violation(exc):
            raise HTTPException(
                status_code=409, detail="Cannot delete a department that has jobs"
            ) from exc
        raise
    _departments_cache.clear()
