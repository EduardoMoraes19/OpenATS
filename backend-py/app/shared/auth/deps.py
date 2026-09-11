"""FastAPI auth dependencies, equivalent to auth.middleware.ts, role.middleware.ts,
and job-access.middleware.ts.

`get_current_user` is applied once at the `/api` router-group level (see
app/routes/api_router.py), not per-route, mirroring `app.use("/api",
authMiddleware, apiLimiter, router)` - so a new route can't forget it.
"""

from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.logging import get_logger
from app.shared.auth.job_access import can_access_candidate, can_access_job, parse_room_id
from app.shared.auth.jwt_auth import AuthenticatedUser, AuthError, get_user_from_token

logger = get_logger(__name__)


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> AuthenticatedUser:
    header = request.headers.get("authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = header.removeprefix("Bearer ").strip()

    try:
        user = await get_user_from_token(token, db)
    except AuthError as exc:
        logger.warning("auth error: %s", exc.message)
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    except jwt.PyJWTError as exc:
        logger.warning("invalid/expired token: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("authentication failed: %s", exc)
        raise HTTPException(status_code=500, detail="Authentication failed") from exc

    request.state.user = user
    return user


async def require_manager(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if user.role not in ("super_admin", "hiring_manager"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


async def require_admin(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


def require_job_access(param: str = "job_id") -> Callable:
    async def _dependency(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        job_id = parse_room_id(request.path_params.get(param))
        if job_id is None:
            raise HTTPException(status_code=400, detail="Invalid job id")
        if not await can_access_job(db, user, job_id):
            logger.warning("job access denied: user=%s job_id=%s", user.id, job_id)
            raise HTTPException(status_code=403, detail="You do not have access to this resource")
        return user

    return _dependency


def require_candidate_access(param: str = "candidate_id") -> Callable:
    async def _dependency(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        candidate_id = parse_room_id(request.path_params.get(param))
        if candidate_id is None:
            raise HTTPException(status_code=400, detail="Invalid candidate id")
        if not await can_access_candidate(db, user, candidate_id):
            logger.warning(
                "candidate access denied: user=%s candidate_id=%s", user.id, candidate_id
            )
            raise HTTPException(status_code=403, detail="You do not have access to this resource")
        return user

    return _dependency
