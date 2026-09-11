"""Equivalent to backend/src/modules/rejection/rejections.routes.ts, mounted
at the API root (not under its own prefix) since its routes hang off
/candidates/:id/... and /templates/:id/preview - matching how the TS router
is mounted at app root "/" rather than under a feature prefix.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.candidates import Candidate
from app.db.models.enums import RejectionEmailStatus
from app.db.models.templates import Template
from app.modules.rejection import service
from app.modules.rejection.schemas import RejectCandidateIn, RejectionOut
from app.modules.template.template_engine_service import compile_template
from app.modules.template.variable_service import get_context_for_candidate
from app.shared.auth.deps import get_current_user, require_manager
from app.shared.auth.verify_token import AuthenticatedUser

router = APIRouter()


@router.post("/candidates/{candidate_id}/reject", status_code=201, dependencies=[Depends(require_manager)])
async def reject_candidate(
    candidate_id: int,
    body: RejectCandidateIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mirrors rejections.routes.ts's POST /candidates/:id/reject: the route
    renders the template once (for the response preview) independently of
    rejection.service.ts's own internal render-and-send - a template that
    exists but fails to render doesn't block the rejection, and a missing
    template just leaves the rendered fields null."""
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    rendered_subject: str | None = None
    rendered_html: str | None = None
    if body.template_id and body.email_status == RejectionEmailStatus.sent:
        template = await db.get(Template, body.template_id)
        if template is not None:
            context = await get_context_for_candidate(db, candidate)
            compiled = compile_template(subject=template.subject, body_json=template.body_json, context=context)
            rendered_subject = compiled["subject"]
            rendered_html = compiled["html"]

    rejection = await service.reject(
        db,
        candidate_id,
        reason=body.reason,
        internal_note=body.internal_note,
        template_id=body.template_id,
        email_status=body.email_status,
        rejected_by=user.id,
    )
    return {
        "data": {
            **RejectionOut.model_validate(rejection).model_dump(by_alias=True),
            "renderedSubject": rendered_subject,
            "renderedHtml": rendered_html,
        }
    }


@router.post("/candidates/{candidate_id}/unreject", dependencies=[Depends(require_manager)])
async def unreject_candidate(
    candidate_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await service.unreject(db, candidate_id, actor_id=user.id)
    return {"success": True}


@router.get("/candidates/{candidate_id}/rejections", response_model=list[RejectionOut])
async def list_rejections(candidate_id: int, db: AsyncSession = Depends(get_db)) -> list[RejectionOut]:
    rejections = await service.list_rejections(db, candidate_id)
    return [RejectionOut.model_validate(r) for r in rejections]


# Note: the source TS codebase also defines POST /templates/:id/preview in
# rejections.routes.ts (a candidate-bound variant of template.routes.ts's own
# preview endpoint at the identical path) - only one is ever reachable there
# since Express resolves to whichever router mounted first. That behavior is
# consolidated into the single handler in app/modules/template/router.py
# instead of reproducing an ambiguous duplicate route here.
