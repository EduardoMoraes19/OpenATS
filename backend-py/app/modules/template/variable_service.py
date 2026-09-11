"""Builds the template substitution context, equivalent to
backend/src/modules/template/variable.service.ts.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidates import Candidate
from app.db.models.company import Company, Department
from app.db.models.jobs import Job
from app.db.models.offers import Offer


async def get_context_for_candidate(db: AsyncSession, candidate: Candidate) -> dict[str, str]:
    job = await db.get(Job, candidate.job_id)
    department = await db.get(Department, job.department_id) if job else None
    company_result = await db.get(Company, department.company_id) if department else None

    return {
        "candidate_name": f"{candidate.first_name} {candidate.last_name}",
        "job_title": job.title if job else "",
        "company_name": company_result.name if company_result else "",
        "start_date": "TBD",
        "salary": "TBD",
        "currency": "",
        "employment_type": job.employment_type.value if job else "",
        "reporting_manager": "TBD",
        "benefits": "TBD",
    }


async def get_context_for_offer(
    db: AsyncSession, candidate: Candidate, offer: Offer, *, review_url: str | None = None
) -> dict[str, str]:
    base = await get_context_for_candidate(db, candidate)
    base.update(
        {
            "start_date": offer.start_date.isoformat() if offer.start_date else "TBD",
            "salary": str(offer.salary) if offer.salary is not None else "TBD",
            "currency": offer.currency or "",
            "employment_type": offer.employment_type.value if offer.employment_type else base["employment_type"],
            "reporting_manager": offer.reporting_manager or "TBD",
            "benefits": offer.benefits or "TBD",
        }
    )
    if review_url:
        base["offer_review_url"] = review_url
    return base
