"""Per-user OAuth2 Google Meet provider, equivalent to
backend/src/shared/integrations/google-meet.provider.ts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.settings import settings
from app.shared.integrations.types import (
    CreateMeetingInput,
    CreateMeetingResult,
    ExchangeCodeResult,
    RefreshTokenResult,
)

_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _require_oauth_config() -> tuple[str, str, str]:
    client_id = settings.google_oauth_client_id
    client_secret = settings.google_oauth_client_secret
    redirect_uri = settings.google_oauth_redirect_uri
    if not client_id or not client_secret or not redirect_uri:
        raise RuntimeError(
            "GOOGLE_OAUTH_CLIENT_ID/GOOGLE_OAUTH_CLIENT_SECRET/GOOGLE_OAUTH_REDIRECT_URI are required"
        )
    return client_id, client_secret, redirect_uri


def _build_flow() -> Flow:
    client_id, client_secret, redirect_uri = _require_oauth_config()
    return Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=_SCOPES,
        redirect_uri=redirect_uri,
    )


class GoogleMeetProvider:
    def get_auth_url(self, state: str) -> str:
        flow = _build_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline", prompt="consent", state=state
        )
        return auth_url

    async def exchange_code(self, code: str) -> ExchangeCodeResult:
        flow = _build_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        if not credentials.token or not credentials.refresh_token:
            raise RuntimeError(
                "Google did not return a refresh token - ensure access_type=offline "
                "and prompt=consent are used"
            )

        account_email = None
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                params={"access_token": credentials.token},
            )
            if response.status_code == 200:
                account_email = response.json().get("email")

        expires_at = credentials.expiry or (datetime.now(UTC) + timedelta(seconds=3600))

        return ExchangeCodeResult(
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expires_at=expires_at,
            account_email=account_email,
            scopes=list(credentials.scopes or _SCOPES),
        )

    async def refresh_access_token(self, refresh_token: str) -> RefreshTokenResult:
        client_id, client_secret, _ = _require_oauth_config()
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        import google.auth.transport.requests

        credentials.refresh(google.auth.transport.requests.Request())
        assert credentials.token is not None, "google-auth guarantees a token after a successful refresh"

        return RefreshTokenResult(
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expires_at=credentials.expiry or (datetime.now(UTC) + timedelta(seconds=3600)),
        )

    async def create_meeting(
        self, access_token: str, meeting_input: CreateMeetingInput
    ) -> CreateMeetingResult:
        credentials = Credentials(token=access_token)
        service = build("calendar", "v3", credentials=credentials)

        end_time = meeting_input.scheduled_at + timedelta(minutes=meeting_input.duration_minutes)
        event_body: dict[str, Any] = {
            "summary": meeting_input.event_name,
            "start": {"dateTime": meeting_input.scheduled_at.isoformat()},
            "end": {"dateTime": end_time.isoformat()},
            "conferenceData": {
                "createRequest": {
                    "requestId": f"openats-{meeting_input.scheduled_at.timestamp()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        if meeting_input.attendee_emails:
            event_body["attendees"] = [{"email": e} for e in meeting_input.attendee_emails]

        created = (
            service.events()
            .insert(
                calendarId="primary",
                body=event_body,
                conferenceDataVersion=1,
                sendUpdates="all",
            )
            .execute()
        )

        hangout_link = created.get("hangoutLink")
        if not hangout_link:
            raise RuntimeError("Google did not return a Meet link")

        return CreateMeetingResult(meeting_url=hangout_link, provider_meeting_id=created.get("id"))

    async def delete_meeting(self, access_token: str, provider_meeting_id: str) -> None:
        credentials = Credentials(token=access_token)
        service = build("calendar", "v3", credentials=credentials)
        service.events().delete(
            calendarId="primary", eventId=provider_meeting_id, sendUpdates="all"
        ).execute()


google_meet_provider = GoogleMeetProvider()
