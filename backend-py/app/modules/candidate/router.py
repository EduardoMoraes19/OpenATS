"""Equivalent to backend/src/modules/candidate/candidate.routes.ts.

Resume URLs are signed here, at the response boundary, via
r2_service.sign_url - never inside the service layer.
"""

from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.logging import get_logger
from app.modules.candidate import service
from app.modules.candidate.schemas import (
    BulkDeleteCandidatesIn,
    CandidateApplyIn,
    CandidateListItemOut,
    CandidateOut,
    MoveStageIn,
)
from app.queues.cv_analysis.queue import request_cv_analysis
from app.shared.auth.deps import get_current_user, require_manager
from app.shared.auth.job_access import can_access_candidate
from app.shared.auth.verify_token import AuthenticatedUser
from app.shared.services import r2_service
from app.sockets.server import notify_candidate_applied, notify_stage_changed

logger = get_logger(__name__)

router = APIRouter()

_MAX_RESUME_BYTES = 10 * 1024 * 1024


def signed_candidate_out(candidate: object) -> CandidateOut:
    out = CandidateOut.model_validate(candidate)
    out.resume_url = r2_service.sign_url(out.resume_url)
    return out


def signed_candidate_list_item(row: object) -> CandidateListItemOut:
    out = CandidateListItemOut.model_validate(row)
    out.resume_url = r2_service.sign_url(out.resume_url)
    return out


_ALLOWED_CANDIDATE_STATUSES = {"active", "rejected", "offered", "hired", "withdrawn"}


async def _list_candidates(
    db: AsyncSession,
    *,
    user: AuthenticatedUser,
    job_id: int | None,
    stage_id: int | None,
    search: str | None,
    status: str | None,
    page: int | None,
    limit: int | None,
) -> dict:
    """Shared by `GET /candidates` and `GET /candidates/jobs/:jobId`, both of
    which candidate.controller.ts routes through the same `getCandidates`
    handler. Unlike job/template/offer, this endpoint is never dual-mode -
    it always returns `{"data": [...], "pagination": {...}}`."""
    if status is not None and status not in _ALLOWED_CANDIDATE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid candidate status")

    normalized_page = max(1, page) if page is not None else None
    normalized_limit = min(200, max(1, limit)) if limit is not None else None
    team_user_id = user.id if user.role == "interviewer" else None

    rows, total, resolved_page, resolved_limit = await service.list_candidates(
        db,
        job_id=job_id,
        stage_id=stage_id,
        search=search,
        status=status,
        page=normalized_page,
        limit=normalized_limit,
        team_user_id=team_user_id,
    )
    return {
        "data": [signed_candidate_list_item(row) for row in rows],
        "pagination": {
            "total": total,
            "page": resolved_page,
            "limit": resolved_limit,
            "totalPages": ceil(total / resolved_limit) if resolved_limit else 0,
        },
    }


@router.post("/jobs/{job_id}/apply", response_model=CandidateOut, status_code=201)
async def apply_for_job(job_id: int, body: CandidateApplyIn, db: AsyncSession = Depends(get_db)) -> CandidateOut:
    try:
        candidate = await service.apply_for_job(
            db,
            job_id,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            phone=body.phone,
            resume_url=body.resume_url,
            custom_answers=[a.model_dump() for a in body.custom_answers],
        )
    except service.DuplicateApplicationError as exc:
        raise HTTPException(status_code=409, detail={"code": "DUPLICATE_APPLICATION"}) from exc

    await notify_candidate_applied(job_id)
    if candidate.resume_url:
        await request_cv_analysis(db, candidate_id=candidate.id, job_id=job_id, resume_url=candidate.resume_url)

    return signed_candidate_out(candidate)


@router.get("", response_model=None)
async def list_candidates(
    page: int | None = None,
    limit: int | None = None,
    stage_id: int | None = None,
    search: str | None = None,
    status: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _list_candidates(
        db, user=user, job_id=None, stage_id=stage_id, search=search, status=status, page=page, limit=limit
    )


@router.get("/jobs/{job_id}", response_model=None)
async def list_candidates_for_job(
    job_id: int,
    page: int | None = None,
    limit: int | None = None,
    stage_id: int | None = None,
    search: str | None = None,
    status: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _list_candidates(
        db, user=user, job_id=job_id, stage_id=stage_id, search=search, status=status, page=page, limit=limit
    )


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(
    candidate_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CandidateOut:
    if user.role == "interviewer" and not await can_access_candidate(db, user, candidate_id):
        raise HTTPException(status_code=403, detail="You do not have access to this resource")

    candidate = await service.get_candidate(db, candidate_id)
    return signed_candidate_out(candidate)


@router.patch("/{candidate_id}", response_model=CandidateOut, dependencies=[Depends(require_manager)])
async def update_candidate(
    candidate_id: int,
    first_name: str | None = Form(default=None),
    last_name: str | None = Form(default=None),
    email: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    resume: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
) -> CandidateOut:
    data = {
        k: v for k, v in {
            "first_name": first_name, "last_name": last_name, "email": email, "phone": phone
        }.items() if v is not None
    }

    new_resume_url = None
    if resume is not None:
        if resume.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Resume must be a PDF file")
        content = await resume.read()
        if len(content) > _MAX_RESUME_BYTES:
            raise HTTPException(status_code=400, detail="Resume must be 10MB or smaller")
        new_resume_url = r2_service.upload_file(content=content, content_type=resume.content_type, folder="resumes")

    candidate = await service.update_basic_details(db, candidate_id, data=data, new_resume_url=new_resume_url)

    if new_resume_url is not None:
        await request_cv_analysis(db, candidate_id=candidate.id, job_id=candidate.job_id, resume_url=new_resume_url)

    return signed_candidate_out(candidate)


@router.put("/{candidate_id}/stage", dependencies=[Depends(require_manager)])
async def move_stage(
    candidate_id: int,
    body: MoveStageIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    candidate, automation = await service.move_stage(
        db, candidate_id, new_stage_id=body.new_stage_id, actor_id=user.id
    )
    await notify_stage_changed(candidate_id, candidate.job_id, body.new_stage_id)
    return {
        "data": signed_candidate_out(candidate).model_dump(by_alias=True),
        "stageAutomation": automation.model_dump(by_alias=True, exclude_none=True),
    }


@router.delete("/bulk", dependencies=[Depends(require_manager)])
async def bulk_delete_candidates(body: BulkDeleteCandidatesIn, db: AsyncSession = Depends(get_db)) -> dict:
    count = await service.delete_many_by_filters(
        db, job_id=body.job_id, stage_id=body.stage_id, search=body.search, status=body.status
    )
    return {"success": True, "deleted": count}


@router.delete("/{candidate_id}", status_code=204, dependencies=[Depends(require_manager)])
async def delete_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_candidate(db, candidate_id)
