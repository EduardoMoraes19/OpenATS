"""GET/POST /public/offers/:token[/accept|/decline] - equivalent to the
offer handlers in public.routes.ts. Token-based, no JWT auth.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.candidates import Candidate
from app.db.models.jobs import Job
from app.modules.offer import service
from app.modules.offer.schemas import PublicOfferOut
from app.shared.rate_limit import public_read_limiter, public_write_limiter
from app.sockets.server import notify_offer_changed

router = APIRouter()


async def _to_public_out(db: AsyncSession, offer) -> PublicOfferOut:
    candidate = await db.get(Candidate, offer.candidate_id)
    job = await db.get(Job, offer.job_id)
    assert candidate is not None and job is not None, "guaranteed by the FKs on offers"
    return PublicOfferOut(
        candidate_name=f"{candidate.first_name} {candidate.last_name}",
        job_title=job.title,
        salary=offer.salary,
        currency=offer.currency,
        employment_type=offer.employment_type,
        start_date=offer.start_date,
        reporting_manager=offer.reporting_manager,
        benefits=offer.benefits,
        offer_letter_html=offer.offer_letter_html,
        status=offer.status,
    )


@router.get("/offers/{token}", response_model=PublicOfferOut, dependencies=[Depends(public_read_limiter)])
async def get_public_offer(token: str, db: AsyncSession = Depends(get_db)) -> PublicOfferOut:
    offer = await service.get_public_by_token(db, token)
    await notify_offer_changed(offer.id, offer.candidate_id, offer.job_id)
    return await _to_public_out(db, offer)


@router.post(
    "/offers/{token}/accept", response_model=PublicOfferOut, dependencies=[Depends(public_write_limiter)]
)
async def accept_public_offer(token: str, db: AsyncSession = Depends(get_db)) -> PublicOfferOut:
    offer = await service.accept_by_token(db, token)
    await notify_offer_changed(offer.id, offer.candidate_id, offer.job_id)
    return await _to_public_out(db, offer)


@router.post(
    "/offers/{token}/decline", response_model=PublicOfferOut, dependencies=[Depends(public_write_limiter)]
)
async def decline_public_offer(token: str, db: AsyncSession = Depends(get_db)) -> PublicOfferOut:
    offer = await service.decline_by_token(db, token)
    await notify_offer_changed(offer.id, offer.candidate_id, offer.job_id)
    return await _to_public_out(db, offer)
