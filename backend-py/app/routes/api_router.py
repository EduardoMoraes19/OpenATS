"""Mounts every authenticated module router under /api, equivalent to
backend/src/routes/index.ts.

`get_current_user` and `api_limiter` are applied once here (not per route),
mirroring `app.use("/api", authMiddleware, apiLimiter, router)` so a new
route can't forget authentication or rate limiting.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.shared.auth.deps import get_current_user
from app.shared.rate_limit import api_limiter

api_router = APIRouter(dependencies=[Depends(get_current_user), Depends(api_limiter)])

# job.routes.ts also mounts pipeline/hiring-team/custom-question as sub-routes
# under /jobs - replicate that by including those routers on the job router
# itself (app/modules/job/router.py), not here.

from app.modules.assessment.router import router as assessment_router  # noqa: E402
from app.modules.assessment_execution.router import router as assessment_execution_router  # noqa: E402
from app.modules.candidate.router import router as candidate_router  # noqa: E402
from app.modules.chat.router import router as chat_router  # noqa: E402
from app.modules.company.router import router as company_router  # noqa: E402
from app.modules.integrations.router import router as integrations_router  # noqa: E402
from app.modules.interview.router import router as interview_router  # noqa: E402
from app.modules.job.router import router as job_router  # noqa: E402
from app.modules.offer.router import router as offer_router  # noqa: E402
from app.modules.rejection.router import router as rejection_router  # noqa: E402
from app.modules.report.router import router as report_router  # noqa: E402
from app.modules.settings.router import router as settings_router  # noqa: E402
from app.modules.template.router import router as template_router  # noqa: E402
from app.modules.upload.router import router as upload_router  # noqa: E402
from app.modules.user.router import router as user_router  # noqa: E402

api_router.include_router(assessment_router, prefix="/assessments", tags=["assessments"])
api_router.include_router(
    assessment_execution_router, prefix="/assessment-execution", tags=["assessment-execution"]
)
api_router.include_router(candidate_router, prefix="/candidates", tags=["candidates"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_router.include_router(company_router, prefix="/company", tags=["company"])
api_router.include_router(integrations_router, prefix="/integrations", tags=["integrations"])
api_router.include_router(interview_router, tags=["interviews"])
api_router.include_router(job_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(offer_router, prefix="/offers", tags=["offers"])
api_router.include_router(rejection_router, tags=["rejection"])
api_router.include_router(report_router, prefix="/reports", tags=["reports"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(template_router, prefix="/templates", tags=["templates"])
api_router.include_router(upload_router, prefix="/upload", tags=["upload"])
api_router.include_router(user_router, prefix="/users", tags=["users"])
