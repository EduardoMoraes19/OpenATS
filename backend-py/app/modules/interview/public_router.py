"""GET /public/interview/:token, PATCH /public/interview/:token/select -
equivalent to the interview handlers in public.routes.ts. Token-based, no
JWT auth.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.modules.interview import service
from app.modules.interview.schemas import PublicInterviewOut, SelectSlotIn
from app.shared.rate_limit import public_read_limiter, public_write_limiter
from app.sockets.server import notify_interview_changed

router = APIRouter()


@router.get(
    "/interview/{token}", response_model=PublicInterviewOut, dependencies=[Depends(public_read_limiter)]
)
async def get_interview(token: str, db: AsyncSession = Depends(get_db)) -> PublicInterviewOut:
    interview, taken = await service.get_by_token(db, token)
    return PublicInterviewOut(**await service.build_public_view(db, interview, taken))


@router.patch(
    "/interview/{token}/select",
    response_model=None,
    dependencies=[Depends(public_write_limiter)],
)
async def select_slot(token: str, body: SelectSlotIn, db: AsyncSession = Depends(get_db)):
    """`{"slotIndex": n}` -> `{"data": {"confirmed": true, "slot": {...}}}`.

    See interview/service.py::select_slot for the full TS-matching business
    logic (token expiry, past-slot rejection, cross-interview collision
    check). SlotTakenError is translated here, not in service.py, because
    it needs a response shape (`{"error", "code"}`) the generic HTTPException
    handler can't produce - a plain string `detail`.
    """
    try:
        interview, selected_slot = await service.select_slot(db, token, slot_index=body.slot_index)
    except service.SlotTakenError:
        return JSONResponse(
            status_code=409,
            content={
                "error": "This time slot is no longer available. Please pick a different time.",
                "code": "SLOT_TAKEN",
            },
        )
    await notify_interview_changed(interview.id, interview.candidate_id)
    return {"confirmed": True, "slot": selected_slot}
