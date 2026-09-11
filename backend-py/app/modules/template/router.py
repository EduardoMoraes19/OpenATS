"""Equivalent to backend/src/modules/template/template.routes.ts."""

from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.enums import TemplateType
from app.modules.template import service
from app.modules.template.schemas import CreateTemplateIn, TemplateOut, UpdateTemplateIn
from app.modules.template.template_engine_service import compile_template
from app.shared.auth.deps import get_current_user, require_manager
from app.shared.auth.verify_token import AuthenticatedUser

router = APIRouter()


@router.get("", response_model=None)
async def list_templates(
    type: TemplateType | None = None,
    page: int | None = Query(default=None, ge=1),
    limit: int = Query(default=15, ge=1),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Dual-mode like template.controller.ts's `getAllTemplates`: no `page`
    query param returns a bare array (`getByType(type)` when `type` is
    given, else `getAll()`), auto-wrapped into `{"data": [...]}` by the
    envelope middleware. `page` present returns
    `{"data": [...], "pagination": {...}}` via `getPaginated`, which is the
    only branch that honors `search`."""
    if page is not None:
        templates, total = await service.list_templates_paginated(
            db, type_=type, page=page, limit=limit, search=search
        )
        return {
            "data": [TemplateOut.model_validate(t) for t in templates],
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "totalPages": ceil(total / limit) if limit else 0,
            },
        }

    if type is not None:
        templates = await service.list_templates_by_type(db, type_=type)
    else:
        templates = await service.list_templates_all(db)
    return [TemplateOut.model_validate(t) for t in templates]


@router.post("", response_model=TemplateOut, status_code=201, dependencies=[Depends(require_manager)])
async def create_template(
    body: CreateTemplateIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    template = await service.create_template(db, data=body.model_dump(), created_by=user.id)
    return TemplateOut.model_validate(template)


@router.delete("/bulk", dependencies=[Depends(require_manager)])
async def bulk_delete_templates(template_ids: list[int], db: AsyncSession = Depends(get_db)) -> dict:
    await service.bulk_delete_templates(db, template_ids)
    return {"success": True}


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)) -> TemplateOut:
    template = await service.get_template(db, template_id)
    return TemplateOut.model_validate(template)


@router.put("/{template_id}", response_model=TemplateOut, dependencies=[Depends(require_manager)])
async def update_template(
    template_id: int, body: UpdateTemplateIn, db: AsyncSession = Depends(get_db)
) -> TemplateOut:
    template = await service.update_template(
        db, template_id, data=body.model_dump(exclude_none=True)
    )
    return TemplateOut.model_validate(template)


@router.delete("/{template_id}", status_code=204, dependencies=[Depends(require_manager)])
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await service.delete_template(db, template_id)


@router.post("/{template_id}/preview", response_model=None)
async def preview_template(
    template_id: int, context: dict = Body(default_factory=dict), db: AsyncSession = Depends(get_db)
) -> dict:
    """The source TS codebase defines POST /templates/:id/preview in two
    different routers: template.routes.ts's own (mounted at "/templates",
    registered first) and a candidate-bound variant inside
    rejections.routes.ts (mounted at "/", registered later). Express
    matches route registration order, so template.controller.ts's
    previewTemplate always wins and the rejection variant is dead code -
    this is a direct port of the WINNING handler only: no candidate-context
    enrichment, no generic-context fallback, the raw request body is used
    as the template context verbatim, and the full compileTemplate() result
    (subject, bodyJson, html) is returned, not just subject/html."""
    template = await service.get_template(db, template_id)
    return compile_template(subject=template.subject, body_json=template.body_json, context=context)
