"""Equivalent to backend/src/modules/offer/offer.service.ts (682 lines in
the source - the offer status state machine, idempotent creation, the
send/accept/decline flows, and markAsHired all live here).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.candidates import Candidate, CandidateStageHistory
from app.db.models.enums import CandidateActivityType, CandidateStatus, OfferStatus, StageType
from app.db.models.jobs import Job
from app.db.models.offers import Offer
from app.db.models.pipeline import JobPipelineStage
from app.db.models.templates import Template
from app.logging import get_logger
from app.modules.candidate import activity_service
from app.modules.offer import repository
from app.modules.template.template_engine_service import compile_template
from app.modules.template.variable_service import get_context_for_offer
from app.settings import settings
from app.shared.services import mail_service

logger = get_logger(__name__)

# draft -> {sent, expired}, sent -> {viewed, accepted, declined, expired},
# viewed -> {accepted, declined, expired}; accepted/declined/expired terminal.
_ALLOWED_TRANSITIONS: dict[OfferStatus, set[OfferStatus]] = {
    OfferStatus.draft: {OfferStatus.sent, OfferStatus.expired},
    OfferStatus.sent: {OfferStatus.viewed, OfferStatus.accepted, OfferStatus.declined, OfferStatus.expired},
    OfferStatus.viewed: {OfferStatus.accepted, OfferStatus.declined, OfferStatus.expired},
    OfferStatus.accepted: set(),
    OfferStatus.declined: set(),
    OfferStatus.expired: set(),
}


def _is_transition_allowed(current: OfferStatus, target: OfferStatus) -> bool:
    if current == target:
        return True
    return target in _ALLOWED_TRANSITIONS.get(current, set())


@dataclass
class OfferRelations:
    """The candidate/job/template rows offer.service.ts's Drizzle relational
    queries (`getById`, `getAllDetails`, `getPaginated`) embed alongside the
    offer itself - `Offer` has no SQLAlchemy relationships of its own, so
    these are fetched as a separate batched lookup rather than a join."""

    candidate: Candidate | None
    job: Job | None
    template: Template | None


async def _load_relations(
    db: AsyncSession, offers: list[Offer], *, with_stage_and_department: bool
) -> dict[int, OfferRelations]:
    if not offers:
        return {}

    candidate_ids = {o.candidate_id for o in offers}
    job_ids = {o.job_id for o in offers}
    template_ids = {o.template_id for o in offers if o.template_id is not None}

    candidate_query = select(Candidate).where(Candidate.id.in_(candidate_ids))
    if with_stage_and_department:
        candidate_query = candidate_query.options(selectinload(Candidate.current_stage))
    candidates_by_id = {c.id: c for c in (await db.execute(candidate_query)).scalars().all()}

    job_query = select(Job).where(Job.id.in_(job_ids))
    if with_stage_and_department:
        job_query = job_query.options(selectinload(Job.department))
    jobs_by_id = {j.id: j for j in (await db.execute(job_query)).scalars().all()}

    templates_by_id: dict[int, Template] = {}
    if template_ids:
        templates_result = await db.execute(select(Template).where(Template.id.in_(template_ids)))
        templates_by_id = {t.id: t for t in templates_result.scalars().all()}

    return {
        offer.id: OfferRelations(
            candidate=candidates_by_id.get(offer.candidate_id),
            job=jobs_by_id.get(offer.job_id),
            template=templates_by_id.get(offer.template_id) if offer.template_id is not None else None,
        )
        for offer in offers
    }


async def list_offers_all(db: AsyncSession) -> list[tuple[Offer, OfferRelations]]:
    """Mirrors offer.service.ts's `getAllDetails`: every offer, no
    jobId/status/search filtering, each with its candidate (+ current
    stage), job (+ department), and template."""
    result = await db.execute(select(Offer).order_by(Offer.created_at.desc()))
    offers = list(result.scalars().all())
    relations = await _load_relations(db, offers, with_stage_and_department=True)
    return [(offer, relations[offer.id]) for offer in offers]


async def list_offers_paginated(
    db: AsyncSession, *, page: int, limit: int, search: str | None, status: OfferStatus | None, job_id: int | None
) -> tuple[list[tuple[Offer, OfferRelations]], int]:
    """Mirrors offer.service.ts's `getPaginated`, including its quirk:
    `search` is applied client-side to the already-paginated page of rows
    (matching candidate first+last name), *after* fetching with
    jobId/status alone - it is never part of the `where` used for the
    count or the limit/offset query. So `total`/`totalPages` reflect the
    jobId/status filters only, and the returned row count for a page can
    be smaller than `limit` once `search` is applied.
    """
    conditions = []
    if job_id:
        conditions.append(Offer.job_id == job_id)
    if status:
        conditions.append(Offer.status == status)
    where = and_(*conditions) if conditions else None

    count_query = select(func.count()).select_from(Offer)
    if where is not None:
        count_query = count_query.where(where)
    total = (await db.execute(count_query)).scalar_one()

    query = select(Offer).order_by(Offer.created_at.desc())
    if where is not None:
        query = query.where(where)
    query = query.offset((page - 1) * limit).limit(limit)
    offers = list((await db.execute(query)).scalars().all())

    if search and offers:
        candidate_ids = [o.candidate_id for o in offers]
        candidates_result = await db.execute(select(Candidate).where(Candidate.id.in_(candidate_ids)))
        names_by_id = {
            c.id: f"{c.first_name} {c.last_name}".lower() for c in candidates_result.scalars().all()
        }
        needle = search.lower()
        offers = [o for o in offers if needle in names_by_id.get(o.candidate_id, "")]

    relations = await _load_relations(db, offers, with_stage_and_department=True)
    return [(offer, relations[offer.id]) for offer in offers], total


async def list_offers_for_job(db: AsyncSession, job_id: int) -> list[Offer]:
    result = await db.execute(select(Offer).where(Offer.job_id == job_id).order_by(Offer.created_at.desc()))
    return list(result.scalars().all())


async def get_offer(db: AsyncSession, offer_id: int) -> Offer:
    offer = await repository.find_by_id(db, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    return offer


async def get_offer_with_relations(db: AsyncSession, offer_id: int) -> tuple[Offer, OfferRelations]:
    """Mirrors offer.service.ts's `getById`: candidate/job/template
    embedded, but (unlike the list endpoints) without the candidate's
    current stage or the job's department nested a level further."""
    offer = await get_offer(db, offer_id)
    relations = await _load_relations(db, [offer], with_stage_and_department=False)
    return offer, relations[offer.id]


async def _render_offer_letter(db: AsyncSession, candidate: Candidate, offer: Offer) -> str | None:
    if offer.template_id is None:
        return offer.offer_letter_html
    template = await db.get(Template, offer.template_id)
    if template is None:
        return offer.offer_letter_html
    context = await get_context_for_offer(db, candidate, offer)
    compiled = compile_template(subject=template.subject, body_json=template.body_json, context=context)
    return compiled["html"]


async def create_offer(db: AsyncSession, *, data: dict, created_by: int) -> Offer:
    """Idempotent by (candidate_id, job_id) - returns the existing offer
    rather than duplicating."""
    existing = await repository.find_by_candidate_and_job(db, data["candidate_id"], data["job_id"])
    if existing is not None:
        return existing

    offer = await repository.create(db, created_by=created_by, **data)

    candidate = await db.get(Candidate, offer.candidate_id)
    assert candidate is not None, "guaranteed by the candidates.id FK on offers"
    if offer.offer_letter_html is None and offer.template_id is not None:
        offer.offer_letter_html = await _render_offer_letter(db, candidate, offer)

    await activity_service.create(
        db,
        candidate_id=offer.candidate_id,
        job_id=offer.job_id,
        offer_id=offer.id,
        actor_id=created_by,
        event_type=CandidateActivityType.offer_created,
    )
    await db.commit()
    await db.refresh(offer)
    return offer


async def update_offer(db: AsyncSession, offer_id: int, *, data: dict) -> Offer:
    offer = await get_offer(db, offer_id)
    target_status = data.get("status")
    if target_status is not None and not _is_transition_allowed(offer.status, target_status):
        raise HTTPException(
            status_code=400, detail=f"Cannot transition offer from {offer.status.value} to {target_status.value}"
        )

    for key, value in data.items():
        setattr(offer, key, value)
    await db.commit()
    await db.refresh(offer)
    return offer


async def delete_offer(db: AsyncSession, offer_id: int) -> None:
    offer = await get_offer(db, offer_id)
    await db.delete(offer)
    await db.commit()


async def bulk_delete_offers(db: AsyncSession, offer_ids: list[int]) -> None:
    await db.execute(delete(Offer).where(Offer.id.in_(offer_ids)))
    await db.commit()


_REQUIRED_SEND_FIELDS = (
    "salary", "currency", "employment_type", "start_date",
    "reporting_manager", "benefits", "offer_letter_html",
)


def _validate_send_requirements(offer: Offer) -> None:
    missing = [field for field in _REQUIRED_SEND_FIELDS if getattr(offer, field) is None]
    if missing:
        raise HTTPException(status_code=400, detail=f"Offer is missing required fields: {', '.join(missing)}")


async def send_offer(db: AsyncSession, offer_id: int, *, actor_id: int) -> Offer:
    offer = await get_offer(db, offer_id)
    if offer.status in (OfferStatus.accepted, OfferStatus.declined, OfferStatus.expired):
        raise HTTPException(status_code=400, detail="Cannot send a terminal offer")

    candidate = await db.get(Candidate, offer.candidate_id)
    job = await db.get(Job, offer.job_id)
    assert candidate is not None and job is not None, "guaranteed by the FKs on offers"

    if offer.template_id is not None:
        offer.offer_letter_html = await _render_offer_letter(db, candidate, offer)

    _validate_send_requirements(offer)

    if not offer.review_token:
        offer.review_token = secrets.token_hex(32)
    offer.status = OfferStatus.sent
    offer.sent_at = datetime.now(UTC).replace(tzinfo=None)

    review_url = f"{settings.frontend_url}/offers/{offer.review_token}"

    await activity_service.create(
        db,
        candidate_id=offer.candidate_id,
        job_id=offer.job_id,
        offer_id=offer.id,
        actor_id=actor_id,
        event_type=CandidateActivityType.offer_sent,
        metadata={"reviewUrl": review_url},
    )
    await db.commit()
    await db.refresh(offer)

    try:
        mail_service.send_offer_email(
            to=candidate.email,
            candidate_name=f"{candidate.first_name} {candidate.last_name}",
            job_title=job.title,
            review_url=review_url,
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to send offer email for offer=%s", offer_id)

    return offer


async def accept_offer(db: AsyncSession, offer_id: int, *, actor_id: int | None) -> Offer:
    offer = await get_offer(db, offer_id)
    if offer.status not in (OfferStatus.sent, OfferStatus.viewed):
        raise HTTPException(status_code=400, detail="Offer cannot be accepted from its current status")
    offer.status = OfferStatus.accepted
    offer.accepted_at = datetime.now(UTC).replace(tzinfo=None)
    await activity_service.create(
        db, candidate_id=offer.candidate_id, job_id=offer.job_id, offer_id=offer.id,
        actor_id=actor_id, event_type=CandidateActivityType.offer_accepted,
    )
    await db.commit()
    await db.refresh(offer)
    return offer


async def decline_offer(db: AsyncSession, offer_id: int, *, actor_id: int | None) -> Offer:
    offer = await get_offer(db, offer_id)
    if offer.status not in (OfferStatus.sent, OfferStatus.viewed):
        raise HTTPException(status_code=400, detail="Offer cannot be declined from its current status")
    offer.status = OfferStatus.declined
    offer.declined_at = datetime.now(UTC).replace(tzinfo=None)
    await activity_service.create(
        db, candidate_id=offer.candidate_id, job_id=offer.job_id, offer_id=offer.id,
        actor_id=actor_id, event_type=CandidateActivityType.offer_declined,
    )
    await db.commit()
    await db.refresh(offer)
    return offer


async def get_public_by_token(db: AsyncSession, token: str) -> Offer:
    offer = await repository.find_by_review_token(db, token)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")

    if offer.status == OfferStatus.sent:
        offer.status = OfferStatus.viewed
        offer.viewed_at = datetime.now(UTC).replace(tzinfo=None)
        await activity_service.create(
            db, candidate_id=offer.candidate_id, job_id=offer.job_id, offer_id=offer.id,
            actor_id=None, event_type=CandidateActivityType.offer_viewed,
        )
        await db.commit()
        await db.refresh(offer)

    return offer


async def accept_by_token(db: AsyncSession, token: str) -> Offer:
    offer = await repository.find_by_review_token(db, token)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    return await accept_offer(db, offer.id, actor_id=None)


async def decline_by_token(db: AsyncSession, token: str) -> Offer:
    offer = await repository.find_by_review_token(db, token)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    return await decline_offer(db, offer.id, actor_id=None)


async def mark_as_hired(db: AsyncSession, offer_id: int, *, actor_id: int) -> tuple[Candidate, JobPipelineStage]:
    """Port of offer.service.ts's markAsHired: prefers a stage literally
    named "Hired" (case-insensitive) among this job's offer-type stages,
    falling back to the last offer-type stage by position."""
    offer = await get_offer(db, offer_id)
    if offer.status != OfferStatus.accepted:
        raise HTTPException(status_code=400, detail="Only accepted offers can be marked as hired")

    stages_result = await db.execute(
        select(JobPipelineStage)
        .where(JobPipelineStage.job_id == offer.job_id, JobPipelineStage.stage_type == StageType.offer)
        .order_by(JobPipelineStage.position)
    )
    offer_stages = list(stages_result.scalars().all())
    if not offer_stages:
        raise HTTPException(status_code=400, detail="No Offer-type stage found for this job")

    target_stage = next(
        (s for s in offer_stages if s.name.strip().lower() == "hired"), offer_stages[-1]
    )

    candidate = await db.get(Candidate, offer.candidate_id)
    assert candidate is not None, "guaranteed by the candidates.id FK on offers"
    candidate.status = CandidateStatus.hired
    candidate.current_stage_id = target_stage.id
    db.add(CandidateStageHistory(candidate_id=candidate.id, stage_id=target_stage.id, moved_by=actor_id))

    await activity_service.create(
        db, candidate_id=offer.candidate_id, job_id=offer.job_id, offer_id=offer.id,
        stage_id=target_stage.id, actor_id=actor_id, event_type=CandidateActivityType.candidate_hired,
    )
    await db.commit()
    await db.refresh(candidate)
    await db.refresh(target_stage)
    return candidate, target_stage
