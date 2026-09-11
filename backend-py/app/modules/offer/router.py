"""Equivalent to backend/src/modules/offer/offer.routes.ts."""

from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.enums import OfferStatus
from app.db.models.offers import Offer
from app.modules.candidate.schemas import CandidateOut
from app.modules.company.schemas import DepartmentOut
from app.modules.job.schemas import JobOut
from app.modules.offer import service
from app.modules.offer.schemas import (
    OfferCandidateOut,
    OfferDetailOut,
    OfferInputIn,
    OfferJobOut,
    OfferListItemOut,
    OfferOut,
    OfferUpdateIn,
)
from app.modules.offer.service import OfferRelations
from app.modules.pipeline.schemas import PipelineStageOut
from app.modules.template.schemas import TemplateOut
from app.shared.auth.deps import get_current_user, require_manager
from app.shared.auth.verify_token import AuthenticatedUser
from app.sockets.server import notify_offer_changed, notify_stage_changed

router = APIRouter()


def _to_detail_out(offer: Offer, relations: OfferRelations) -> OfferDetailOut:
    base = OfferOut.model_validate(offer).model_dump()
    return OfferDetailOut(
        **base,
        candidate=CandidateOut.model_validate(relations.candidate) if relations.candidate else None,
        job=JobOut.model_validate(relations.job) if relations.job else None,
        template=TemplateOut.model_validate(relations.template) if relations.template else None,
    )


def _to_list_item_out(offer: Offer, relations: OfferRelations) -> OfferListItemOut:
    candidate_out = None
    if relations.candidate is not None:
        candidate_out = OfferCandidateOut(
            **CandidateOut.model_validate(relations.candidate).model_dump(),
            current_stage=PipelineStageOut.model_validate(relations.candidate.current_stage)
            if relations.candidate.current_stage
            else None,
        )
    job_out = None
    if relations.job is not None:
        job_out = OfferJobOut(
            **JobOut.model_validate(relations.job).model_dump(),
            department=DepartmentOut.model_validate(relations.job.department) if relations.job.department else None,
        )
    base = OfferOut.model_validate(offer).model_dump()
    return OfferListItemOut(
        **base,
        candidate=candidate_out,
        job=job_out,
        template=TemplateOut.model_validate(relations.template) if relations.template else None,
    )


@router.get("", response_model=None)
async def list_offers(
    page: int | None = Query(default=None, ge=1),
    limit: int = Query(default=15, ge=1),
    search: str | None = None,
    status: OfferStatus | None = None,
    job_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Dual-mode like offer.controller.ts's `getAllOffers`: no `page` query
    param returns every offer as a bare array (`getAllDetails`, auto-wrapped
    into `{"data": [...]}` by the envelope middleware, and ignoring
    search/status/jobId - the TS non-paginated branch takes no filters
    either). `page` present returns
    `{"data": [...], "pagination": {...}}` via `getPaginated`."""
    if page is not None:
        rows, total = await service.list_offers_paginated(
            db, page=page, limit=limit, search=search, status=status, job_id=job_id
        )
        return {
            "data": [_to_list_item_out(offer, relations) for offer, relations in rows],
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "totalPages": ceil(total / limit) if limit else 0,
            },
        }

    rows = await service.list_offers_all(db)
    return [_to_list_item_out(offer, relations) for offer, relations in rows]


@router.delete("/bulk", dependencies=[Depends(require_manager)])
async def bulk_delete_offers(offer_ids: list[int], db: AsyncSession = Depends(get_db)) -> dict:
    await service.bulk_delete_offers(db, offer_ids)
    return {"success": True}


@router.get("/job/{job_id}", response_model=list[OfferOut])
async def list_offers_for_job(job_id: int, db: AsyncSession = Depends(get_db)) -> list[OfferOut]:
    offers = await service.list_offers_for_job(db, job_id)
    return [OfferOut.model_validate(o) for o in offers]


@router.get("/{offer_id}", response_model=OfferDetailOut)
async def get_offer(offer_id: int, db: AsyncSession = Depends(get_db)) -> OfferDetailOut:
    offer, relations = await service.get_offer_with_relations(db, offer_id)
    return _to_detail_out(offer, relations)


@router.post("", response_model=OfferOut, status_code=201, dependencies=[Depends(require_manager)])
async def create_offer(
    body: OfferInputIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OfferOut:
    offer = await service.create_offer(db, data=body.model_dump(), created_by=user.id)
    await notify_offer_changed(offer.id, offer.candidate_id, offer.job_id)
    return OfferOut.model_validate(offer)


@router.patch("/{offer_id}", response_model=OfferOut, dependencies=[Depends(require_manager)])
async def update_offer(offer_id: int, body: OfferUpdateIn, db: AsyncSession = Depends(get_db)) -> OfferOut:
    offer = await service.update_offer(db, offer_id, data=body.model_dump(exclude_none=True))
    await notify_offer_changed(offer.id, offer.candidate_id, offer.job_id)
    return OfferOut.model_validate(offer)


@router.delete("/{offer_id}", status_code=204, dependencies=[Depends(require_manager)])
async def delete_offer(offer_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_offer(db, offer_id)


@router.post("/{offer_id}/send", response_model=OfferOut, dependencies=[Depends(require_manager)])
async def send_offer(
    offer_id: int, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> OfferOut:
    offer = await service.send_offer(db, offer_id, actor_id=user.id)
    await notify_offer_changed(offer.id, offer.candidate_id, offer.job_id)
    return OfferOut.model_validate(offer)


@router.post("/{offer_id}/accept", response_model=OfferOut)
async def accept_offer(
    offer_id: int, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> OfferOut:
    offer = await service.accept_offer(db, offer_id, actor_id=user.id)
    await notify_offer_changed(offer.id, offer.candidate_id, offer.job_id)
    return OfferOut.model_validate(offer)


@router.post("/{offer_id}/decline", response_model=OfferOut)
async def decline_offer(
    offer_id: int, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> OfferOut:
    offer = await service.decline_offer(db, offer_id, actor_id=user.id)
    await notify_offer_changed(offer.id, offer.candidate_id, offer.job_id)
    return OfferOut.model_validate(offer)


@router.post("/{offer_id}/mark-hired", dependencies=[Depends(require_manager)])
async def mark_offer_hired(
    offer_id: int, user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    candidate, target_stage = await service.mark_as_hired(db, offer_id, actor_id=user.id)
    await notify_offer_changed(offer_id, candidate.id, candidate.job_id)
    await notify_stage_changed(candidate.id, candidate.job_id, target_stage.id)
    return {
        "candidate": CandidateOut.model_validate(candidate).model_dump(by_alias=True),
        "hiredStage": PipelineStageOut.model_validate(target_stage).model_dump(by_alias=True),
    }
