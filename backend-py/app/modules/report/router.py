"""Equivalent to backend/src/modules/report/report.routes.ts +
report.controller.ts.

`GET /analytics` carries no extra role gate beyond the router-group-level
auth (matches `router.get("/analytics", getReportsAnalytics)` in the TS
source - no `requireManager`). `GET /analytics/export` requires manager,
matching `router.get("/analytics/export", requireManager,
exportReportsAnalytics)`.

Unlike a typical export endpoint, this does not stream a file: the TS
controller returns the export content as a plain JSON body
(`res.json({data: result})`), so this router does too - the envelope
middleware wraps the returned dict in `{"data": ...}` automatically.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.report import service
from app.shared.auth.deps import require_manager

router = APIRouter()


@router.get("/analytics")
async def get_reports_analytics(
    period: str = Query(default="7d", pattern="^(7d|30d|90d)$"),
    department_id: int | None = Query(default=None, gt=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.get_analytics(db, period=period, department_id=department_id)


@router.get("/analytics/export", dependencies=[Depends(require_manager)])
async def export_reports_analytics(
    period: str = Query(default="7d", pattern="^(7d|30d|90d)$"),
    department_id: int | None = Query(default=None, gt=0),
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.export_analytics(db, period=period, department_id=department_id, format_=format)
