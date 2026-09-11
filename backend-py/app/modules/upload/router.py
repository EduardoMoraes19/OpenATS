"""Equivalent to backend/src/modules/upload/upload.routes.ts."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.company import Company
from app.shared.rate_limit import expensive_limiter
from app.shared.schema import ApiModel
from app.shared.services import r2_service

router = APIRouter(dependencies=[Depends(expensive_limiter)])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}


class UploadOut(ApiModel):
    url: str
    filename: str
    mimetype: str
    size: int


async def _read_and_validate(file: UploadFile, *, allowed_types: set[str]) -> tuple[bytes, str]:
    content_type = file.content_type
    if content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File must be 10MB or smaller")
    return content, content_type


@router.post("/resume", response_model=UploadOut)
async def upload_resume(file: UploadFile) -> UploadOut:
    content, content_type = await _read_and_validate(file, allowed_types={"application/pdf"})
    url = await asyncio.to_thread(r2_service.upload_file, content=content, content_type=content_type, folder="resumes")
    return UploadOut(url=url, filename=file.filename or "", mimetype=content_type, size=len(content))


@router.post("/logo", response_model=UploadOut)
async def upload_logo(
    file: UploadFile, company_id: int | None = Query(default=None), db: AsyncSession = Depends(get_db)
) -> UploadOut:
    content, content_type = await _read_and_validate(file, allowed_types=_ALLOWED_LOGO_TYPES)
    url = await asyncio.to_thread(r2_service.upload_file, content=content, content_type=content_type, folder="logos")

    if company_id is not None:
        company = await db.get(Company, company_id)
    else:
        company = (await db.execute(select(Company).limit(1))).scalar_one_or_none()

    if company is not None:
        company.logo_url = url
        await db.commit()

    return UploadOut(url=url, filename=file.filename or "", mimetype=content_type, size=len(content))
