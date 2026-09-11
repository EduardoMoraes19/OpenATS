"""MeetingProviderClient protocol, equivalent to backend/src/shared/integrations/types.ts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ExchangeCodeResult:
    access_token: str
    refresh_token: str
    expires_at: datetime
    account_email: str | None
    scopes: list[str]


@dataclass(frozen=True)
class RefreshTokenResult:
    access_token: str
    refresh_token: str | None
    expires_at: datetime


@dataclass(frozen=True)
class CreateMeetingInput:
    event_name: str
    scheduled_at: datetime
    duration_minutes: int
    attendee_emails: list[str] | None = None


@dataclass(frozen=True)
class CreateMeetingResult:
    meeting_url: str
    provider_meeting_id: str | None = None


class MeetingProviderClient(Protocol):
    def get_auth_url(self, state: str) -> str: ...

    async def exchange_code(self, code: str) -> ExchangeCodeResult: ...

    async def refresh_access_token(self, refresh_token: str) -> RefreshTokenResult: ...

    async def create_meeting(
        self, access_token: str, meeting_input: CreateMeetingInput
    ) -> CreateMeetingResult: ...

    async def delete_meeting(self, access_token: str, provider_meeting_id: str) -> None: ...
