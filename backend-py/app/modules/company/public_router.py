"""GET /public/company - equivalent to the company handler in public.routes.ts.

Only exposes name/logo/description - never email/phone/address, which are
internal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.company import service
from app.shared.schema import ApiModel

router = APIRouter()


class PublicCompanyOut(ApiModel):
    name: str
    logo_url: str | None
    description: str | None


@router.get("/company", response_model=PublicCompanyOut | None)
async def get_public_company(db: AsyncSession = Depends(get_db)) -> PublicCompanyOut | None:
    company = await service.get_company(db)
    if company is None:
        return None
    return PublicCompanyOut(name=company.name, logo_url=company.logo_url, description=company.description)
