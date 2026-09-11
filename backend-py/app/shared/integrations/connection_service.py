"""Per-user meeting-provider connection lifecycle, equivalent to
backend/src/shared/integrations/connection.service.ts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import MeetingProvider
from app.db.models.integrations import IntegrationConnection
from app.shared.integrations import crypto
from app.shared.integrations.registry import get_provider_client

STATE_TTL_SECONDS = 600
REFRESH_BUFFER = timedelta(minutes=5)


@dataclass(frozen=True)
class ConnectionStatus:
    provider: MeetingProvider
    connected: bool
    account_email: str | None


def get_auth_url(user_id: int) -> str:
    state = crypto.sign_state(user_id, STATE_TTL_SECONDS)
    return get_provider_client(MeetingProvider.google_meet).get_auth_url(state)


async def handle_callback(db: AsyncSession, code: str, state: str) -> None:
    payload = crypto.verify_state(state)
    provider = MeetingProvider.google_meet
    result = await get_provider_client(provider).exchange_code(code)

    stmt = (
        pg_insert(IntegrationConnection)
        .values(
            user_id=payload.user_id,
            provider=provider,
            access_token_encrypted=crypto.encrypt(result.access_token),
            refresh_token_encrypted=crypto.encrypt(result.refresh_token),
            expires_at=result.expires_at.replace(tzinfo=None),
            scopes=result.scopes,
            provider_account_email=result.account_email,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "provider"],
            set_={
                "access_token_encrypted": crypto.encrypt(result.access_token),
                "refresh_token_encrypted": crypto.encrypt(result.refresh_token),
                "expires_at": result.expires_at.replace(tzinfo=None),
                "scopes": result.scopes,
                "provider_account_email": result.account_email,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()


async def get_status(db: AsyncSession, user_id: int) -> list[ConnectionStatus]:
    result = await db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == MeetingProvider.google_meet,
        )
    )
    connection = result.scalar_one_or_none()
    return [
        ConnectionStatus(
            provider=MeetingProvider.google_meet,
            connected=connection is not None,
            account_email=connection.provider_account_email if connection else None,
        )
    ]


async def disconnect(db: AsyncSession, user_id: int) -> None:
    result = await db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == MeetingProvider.google_meet,
        )
    )
    connection = result.scalar_one_or_none()
    if connection is not None:
        await db.delete(connection)
        await db.commit()


async def get_valid_access_token(db: AsyncSession, user_id: int) -> str | None:
    """Returns a usable access token, refreshing it first if it expires within
    the 5-minute buffer, persisting any rotated refresh token."""
    result = await db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == MeetingProvider.google_meet,
        )
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        return None

    expires_at = connection.expires_at.replace(tzinfo=UTC)
    if expires_at - datetime.now(UTC) > REFRESH_BUFFER:
        return crypto.decrypt(connection.access_token_encrypted)

    refresh_token = crypto.decrypt(connection.refresh_token_encrypted)
    refreshed = await get_provider_client(MeetingProvider.google_meet).refresh_access_token(
        refresh_token
    )

    connection.access_token_encrypted = crypto.encrypt(refreshed.access_token)
    if refreshed.refresh_token:
        connection.refresh_token_encrypted = crypto.encrypt(refreshed.refresh_token)
    connection.expires_at = refreshed.expires_at.replace(tzinfo=None)
    await db.commit()

    return refreshed.access_token
