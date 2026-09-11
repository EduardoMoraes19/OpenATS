"""Thin data-access layer, equivalent to backend/src/modules/offer/offer.repository.ts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.offers import Offer


async def find_by_id(db: AsyncSession, offer_id: int) -> Offer | None:
    return await db.get(Offer, offer_id)


async def find_by_candidate_and_job(db: AsyncSession, candidate_id: int, job_id: int) -> Offer | None:
    result = await db.execute(
        select(Offer).where(Offer.candidate_id == candidate_id, Offer.job_id == job_id)
    )
    return result.scalar_one_or_none()


async def find_by_review_token(db: AsyncSession, token: str) -> Offer | None:
    result = await db.execute(select(Offer).where(Offer.review_token == token))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, **fields) -> Offer:
    offer = Offer(**fields)
    db.add(offer)
    await db.flush()
    return offer
