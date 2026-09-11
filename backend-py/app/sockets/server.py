"""python-socketio AsyncServer, equivalent to backend/src/shared/services/socket.service.ts.

Protocol-compatible with the socket.io-client used by frontend/lib/socket.ts,
so the frontend needs zero changes. Authorization for chat writes is a
per-connection "room membership cache", exactly like the TS code: joining
job_<id>/candidate_<id> re-checks the DB once, and every write after that
only checks whether the socket is still in that room - it does not re-query
the DB per message. This is a deliberate behavior to preserve, not a
shortcut to fix.
"""

from __future__ import annotations

import jwt
import socketio
from sqlalchemy import select

from app.db.base import session_scope
from app.db.models.communications import CandidateChatMessage, JobChatMessage
from app.db.models.users import User
from app.logging import get_logger
from app.settings import settings
from app.shared.auth.job_access import can_access_candidate, can_access_job, parse_room_id
from app.shared.auth.jwt_auth import AuthError, get_user_from_token

logger = get_logger(__name__)

STAFF_ROOM = "staff"
SYSTEM_SENDER_ID = 1  # hardcoded system-message sender id, ported literally from socket.service.ts

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[settings.frontend_url],
)


def _job_room(job_id: int) -> str:
    return f"job_{job_id}"


def _candidate_room(candidate_id: int) -> str:
    return f"candidate_{candidate_id}"


async def _socket_in_room(sid: str, room: str) -> bool:
    return room in sio.rooms(sid)


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None) -> None:
    token = (auth or {}).get("token")
    if not token or not isinstance(token, str):
        raise ConnectionRefusedError("unauthorized")

    async with session_scope() as db:
        try:
            user = await get_user_from_token(token, db)
        except (AuthError, jwt.PyJWTError) as exc:
            logger.warning("socket handshake rejected: %s", exc)
            raise ConnectionRefusedError("unauthorized") from exc

    await sio.save_session(sid, {"user": user})
    await sio.enter_room(sid, STAFF_ROOM)


@sio.event
async def disconnect(sid: str) -> None:
    logger.info("socket disconnected: %s", sid)


@sio.event
async def join_job(sid: str, payload: object) -> None:
    session = await sio.get_session(sid)
    user = session["user"]
    job_id = parse_room_id(payload)
    if job_id is None:
        return

    async with session_scope() as db:
        allowed = await can_access_job(db, user, job_id)
    if not allowed:
        await sio.emit("room_denied", {"room": "job", "id": job_id}, to=sid)
        return
    await sio.enter_room(sid, _job_room(job_id))


@sio.event
async def join_candidate(sid: str, payload: object) -> None:
    session = await sio.get_session(sid)
    user = session["user"]
    candidate_id = parse_room_id(payload)
    if candidate_id is None:
        return

    async with session_scope() as db:
        allowed = await can_access_candidate(db, user, candidate_id)
    if not allowed:
        await sio.emit("room_denied", {"room": "candidate", "id": candidate_id}, to=sid)
        return
    await sio.enter_room(sid, _candidate_room(candidate_id))


@sio.event
async def send_job_message(sid: str, payload: dict) -> None:
    session = await sio.get_session(sid)
    user = session["user"]
    job_id = parse_room_id(payload.get("jobId"))
    if job_id is None or not await _socket_in_room(sid, _job_room(job_id)):
        await sio.emit("write_denied", {"event": "send_job_message"}, to=sid)
        return

    async with session_scope() as db:
        message = JobChatMessage(
            job_id=job_id,
            sender_id=user.id,
            message=payload.get("message"),
            reply_to_id=payload.get("replyToId"),
        )
        db.add(message)
        await db.flush()
        sender = await db.get(User, user.id)
        assert sender is not None, "user was just authenticated, so this row must exist"
        await db.commit()

        enriched = {
            "id": message.id,
            "jobId": message.job_id,
            "senderId": message.sender_id,
            "message": message.message,
            "replyToId": message.reply_to_id,
            "sentAt": message.sent_at.isoformat(),
            "isSystemMessage": message.is_system_message,
            "isDeleted": message.is_deleted,
            "senderName": f"{sender.first_name} {sender.last_name}",
            "senderAvatar": sender.avatar_url,
        }

    await sio.emit("new_job_message", enriched, room=_job_room(job_id))


@sio.event
async def edit_job_message(sid: str, payload: dict) -> None:
    session = await sio.get_session(sid)
    user = session["user"]
    job_id = parse_room_id(payload.get("jobId"))
    if job_id is None or not await _socket_in_room(sid, _job_room(job_id)):
        await sio.emit("write_denied", {"event": "edit_job_message"}, to=sid)
        return

    async with session_scope() as db:
        result = await db.execute(
            select(JobChatMessage).where(
                JobChatMessage.id == payload.get("messageId"),
                JobChatMessage.job_id == job_id,
                JobChatMessage.sender_id == user.id,
                JobChatMessage.is_deleted.is_(False),
            )
        )
        message = result.scalar_one_or_none()
        if message is None:
            return  # silent no-op: not found, not the sender, wrong job, or already deleted

        message.message = payload.get("message")
        await db.flush()
        sender = await db.get(User, user.id)
        assert sender is not None, "user was just authenticated, so this row must exist"
        await db.commit()

        enriched = {
            "id": message.id,
            "jobId": message.job_id,
            "senderId": message.sender_id,
            "message": message.message,
            "replyToId": message.reply_to_id,
            "sentAt": message.sent_at.isoformat(),
            "isSystemMessage": message.is_system_message,
            "isDeleted": message.is_deleted,
            "senderName": f"{sender.first_name} {sender.last_name}",
            "senderAvatar": sender.avatar_url,
        }

    await sio.emit("job_message_updated", enriched, room=_job_room(job_id))


@sio.event
async def delete_job_message(sid: str, payload: dict) -> None:
    session = await sio.get_session(sid)
    user = session["user"]
    job_id = parse_room_id(payload.get("jobId"))
    if job_id is None or not await _socket_in_room(sid, _job_room(job_id)):
        await sio.emit("write_denied", {"event": "delete_job_message"}, to=sid)
        return

    async with session_scope() as db:
        result = await db.execute(
            select(JobChatMessage).where(
                JobChatMessage.id == payload.get("messageId"),
                JobChatMessage.job_id == job_id,
                JobChatMessage.sender_id == user.id,
                JobChatMessage.is_deleted.is_(False),
            )
        )
        message = result.scalar_one_or_none()
        if message is None:
            return
        message.is_deleted = True
        message_id = message.id
        await db.commit()

    await sio.emit("job_message_deleted", {"id": message_id}, room=_job_room(job_id))


@sio.event
async def send_candidate_message(sid: str, payload: dict) -> None:
    session = await sio.get_session(sid)
    user = session["user"]
    candidate_id = parse_room_id(payload.get("candidateId"))
    if candidate_id is None or not await _socket_in_room(sid, _candidate_room(candidate_id)):
        await sio.emit("write_denied", {"event": "send_candidate_message"}, to=sid)
        return

    async with session_scope() as db:
        message = CandidateChatMessage(
            candidate_id=candidate_id,
            sender_id=user.id,
            message=payload.get("message"),
            reply_to_id=payload.get("replyToId"),
        )
        db.add(message)
        await db.flush()
        row = {
            "id": message.id,
            "candidateId": message.candidate_id,
            "senderId": message.sender_id,
            "message": message.message,
            "replyToId": message.reply_to_id,
            "sentAt": message.sent_at.isoformat(),
            "isSystemMessage": message.is_system_message,
            "isDeleted": message.is_deleted,
        }
        await db.commit()

    # No sender-name enrichment here - matches the TS asymmetry vs job messages.
    await sio.emit("new_candidate_message", row, room=_candidate_room(candidate_id))


async def send_system_message_to_job(job_id: int, message: str) -> None:
    async with session_scope() as db:
        row = JobChatMessage(
            job_id=job_id,
            sender_id=SYSTEM_SENDER_ID,
            message=message,
            is_system_message=True,
        )
        db.add(row)
        await db.flush()
        enriched = {
            "id": row.id,
            "jobId": row.job_id,
            "senderId": row.sender_id,
            "message": row.message,
            "replyToId": row.reply_to_id,
            "sentAt": row.sent_at.isoformat(),
            "isSystemMessage": row.is_system_message,
            "isDeleted": row.is_deleted,
        }
        await db.commit()
    await sio.emit("new_job_message", enriched, room=_job_room(job_id))


# --- Server -> client domain-event broadcasts, all to STAFF_ROOM. ---------


async def notify_candidate_applied(job_id: int) -> None:
    await sio.emit("candidate_applied", {"jobId": job_id}, room=STAFF_ROOM)


async def notify_stage_changed(candidate_id: int, job_id: int, stage_id: int) -> None:
    await sio.emit(
        "candidate_stage_changed",
        {"candidateId": candidate_id, "jobId": job_id, "stageId": stage_id},
        room=STAFF_ROOM,
    )


async def notify_offer_changed(offer_id: int, candidate_id: int, job_id: int) -> None:
    await sio.emit(
        "offer_changed",
        {"offerId": offer_id, "candidateId": candidate_id, "jobId": job_id},
        room=STAFF_ROOM,
    )


async def notify_interview_changed(interview_id: int, candidate_id: int) -> None:
    await sio.emit(
        "interview_changed",
        {"interviewId": interview_id, "candidateId": candidate_id},
        room=STAFF_ROOM,
    )


async def notify_assessment_progress(candidate_id: int, attempt_id: int) -> None:
    await sio.emit(
        "assessment_progress_updated",
        {"candidateId": candidate_id, "attemptId": attempt_id},
        room=STAFF_ROOM,
    )


async def emit_cv_analysis_update(candidate_id: int, job_id: int, status: str) -> None:
    await sio.emit(
        "cv_analysis_updated",
        {"candidateId": candidate_id, "jobId": job_id, "status": status},
        room=STAFF_ROOM,
    )
