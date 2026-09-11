"""Unauthenticated, origin-gated public surface, equivalent to
backend/src/routes/public.routes.ts.

No get_current_user dependency here - these routes use origin gating
(check_origins) and, for candidate-facing flows, their own random-token
auth instead of JWT. Per-route rate limiters are applied where the TS code
applies them, not uniformly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.shared.middleware.allowed_origins import check_origins

public_router = APIRouter(dependencies=[Depends(check_origins)])

from app.modules.assessment_execution.public_router import router as public_assessment_router  # noqa: E402
from app.modules.candidate.public_router import router as public_candidate_router  # noqa: E402
from app.modules.company.public_router import router as public_company_router  # noqa: E402
from app.modules.interview.public_router import router as public_interview_router  # noqa: E402
from app.modules.job.public_router import router as public_job_router  # noqa: E402
from app.modules.offer.public_router import router as public_offer_router  # noqa: E402
from app.modules.upload.public_router import router as public_upload_router  # noqa: E402

public_router.include_router(public_assessment_router)
public_router.include_router(public_candidate_router)
public_router.include_router(public_company_router)
public_router.include_router(public_interview_router)
public_router.include_router(public_job_router)
public_router.include_router(public_offer_router)
public_router.include_router(public_upload_router)

# Remaining module routers are included here as each module is implemented.
