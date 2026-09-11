"""POST /public/upload/resume - equivalent to the resume upload handler in
public.routes.ts. PDF-only, 10MB cap, origin-gated, rate-limited.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.modules.upload.router import MAX_UPLOAD_BYTES, UploadOut
from app.shared.rate_limit import public_write_limiter
from app.shared.services import r2_service

router = APIRouter()


@router.post("/upload/resume", response_model=UploadOut, dependencies=[Depends(public_write_limiter)])
async def upload_resume(file: UploadFile) -> UploadOut:
    content_type = file.content_type
    if content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Resume must be a PDF file")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Resume must be 10MB or smaller")
    url = await asyncio.to_thread(r2_service.upload_file, content=content, content_type=content_type, folder="resumes")
    return UploadOut(url=url, filename=file.filename or "", mimetype=content_type, size=len(content))
