"""Equivalent to backend/src/modules/company/company.routes.ts."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.company import service
from app.modules.company.schemas import (
    CompanyOut,
    CreateDepartmentIn,
    DepartmentOut,
    UpdateDepartmentIn,
    UpsertCompanyIn,
)
from app.shared.auth.deps import require_admin, require_manager

router = APIRouter()


@router.get("", response_model=CompanyOut | None)
async def get_company(db: AsyncSession = Depends(get_db)) -> CompanyOut | None:
    company = await service.get_company(db)
    return CompanyOut.model_validate(company) if company else None


@router.put("", response_model=CompanyOut, dependencies=[Depends(require_admin)])
async def upsert_company(body: UpsertCompanyIn, db: AsyncSession = Depends(get_db)) -> CompanyOut:
    data = body.model_dump(mode="json", exclude_none=True)
    company = await service.upsert_company(db, data)
    return CompanyOut.model_validate(company)


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(db: AsyncSession = Depends(get_db)) -> list[DepartmentOut]:
    departments = await service.list_departments(db)
    return [DepartmentOut.model_validate(d) for d in departments]


@router.post(
    "/departments", response_model=DepartmentOut, status_code=201,
    dependencies=[Depends(require_manager)],
)
async def create_department(
    body: CreateDepartmentIn, db: AsyncSession = Depends(get_db)
) -> DepartmentOut:
    department = await service.create_department(db, body.name)
    return DepartmentOut.model_validate(department)


@router.put(
    "/departments/{department_id}", response_model=DepartmentOut,
    dependencies=[Depends(require_manager)],
)
async def update_department(
    department_id: int, body: UpdateDepartmentIn, db: AsyncSession = Depends(get_db)
) -> DepartmentOut:
    department = await service.update_department(db, department_id, body.name)
    return DepartmentOut.model_validate(department)


@router.delete(
    "/departments/{department_id}", status_code=204, dependencies=[Depends(require_manager)]
)
async def delete_department(department_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_department(db, department_id)
