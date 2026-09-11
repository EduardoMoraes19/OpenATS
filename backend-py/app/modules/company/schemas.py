from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field, HttpUrl

from app.shared.schema import ApiModel, ApiOutModel


class CompanyOut(ApiOutModel):
    id: int
    name: str
    email: str
    website: str | None
    phone: str | None
    address: str | None
    description: str | None
    logo_url: str | None
    created_at: datetime
    updated_at: datetime



class UpsertCompanyIn(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    website: HttpUrl | None = None
    phone: str | None = None
    address: str | None = None
    description: str | None = None
    logo_url: HttpUrl | None = None


class DepartmentOut(ApiOutModel):
    id: int
    company_id: int
    name: str
    created_at: datetime
    updated_at: datetime



class CreateDepartmentIn(ApiModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateDepartmentIn(ApiModel):
    name: str = Field(min_length=1, max_length=255)
