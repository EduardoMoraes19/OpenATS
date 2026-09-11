"""Equivalent to backend/src/modules/chat/chat.routes.ts.

Read-only: all writes (send/edit/delete) happen over Socket.IO
(app/sockets/server.py), not REST - this is the one module where the
source TS code uses requireJobAccess/requireCandidateAccess as route
middleware, which is mirrored exactly here via router-level dependencies.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.communications import CandidateChatMessage, JobChatMessage
from app.db.models.users import User
from app.modules.chat.schemas import ChatMessageOut
from app.shared.auth.deps import require_candidate_access, require_job_access

router = APIRouter()


def _to_out(m: JobChatMessage | CandidateChatMessage, u: User | None) -> ChatMessageOut:
    """A left-joined `u` is None when the sender's user row is gone - the
    message still shows, just without sender details, matching the TS
    controller's LEFT JOIN + `senderName: m.senderName ? ... : null`."""
    return ChatMessageOut(
        id=m.id, sender_id=m.sender_id,
        message=m.message, reply_to_id=m.reply_to_id, sent_at=m.sent_at,
        is_system_message=m.is_system_message, is_deleted=m.is_deleted,
        sender_name=f"{u.first_name} {u.last_name}".strip() if u else None,
        sender_last_name=u.last_name if u else None,
        sender_avatar=u.avatar_url if u else None,
    )


@router.get(
    "/job/{job_id}", response_model=list[ChatMessageOut], dependencies=[Depends(require_job_access("job_id"))]
)
async def get_job_chat_history(job_id: int, db: AsyncSession = Depends(get_db)) -> list[ChatMessageOut]:
    result = await db.execute(
        select(JobChatMessage, User)
        .outerjoin(User, User.id == JobChatMessage.sender_id)
        .where(JobChatMessage.job_id == job_id, JobChatMessage.is_deleted.is_(False))
        .order_by(JobChatMessage.sent_at.desc())
    )
    return [_to_out(m, u) for m, u in result.all()]


@router.get(
    "/candidate/{candidate_id}", response_model=list[ChatMessageOut],
    dependencies=[Depends(require_candidate_access("candidate_id"))],
)
async def get_candidate_chat_history(candidate_id: int, db: AsyncSession = Depends(get_db)) -> list[ChatMessageOut]:
    result = await db.execute(
        select(CandidateChatMessage, User)
        .outerjoin(User, User.id == CandidateChatMessage.sender_id)
        .where(CandidateChatMessage.candidate_id == candidate_id, CandidateChatMessage.is_deleted.is_(False))
        .order_by(CandidateChatMessage.sent_at.desc())
    )
    return [_to_out(m, u) for m, u in result.all()]
