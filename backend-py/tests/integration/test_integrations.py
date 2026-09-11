"""Real end-to-end tests of the integrations module - connection status,
the authorize-url handoff, disconnect, and the public OAuth callback
(equivalent to integrations.routes.ts + oauth.routes.ts).

The actual Google token exchange is a real network call, so it's
monkeypatched at the provider-registry boundary (the same "swap the external
client" pattern used for R2 in test_upload.py) - everything else (state
signing/verification, the DB upsert, the redirect shape) runs for real.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models.enums import MeetingProvider
from app.shared.integrations import crypto, registry
from app.shared.integrations.types import ExchangeCodeResult
from tests.conftest import make_bearer_token
from tests.integration.helpers import manager_headers

pytestmark = pytest.mark.asyncio


class _FakeGoogleMeetClient:
    def get_auth_url(self, state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/auth?state={state}"

    async def exchange_code(self, code: str) -> ExchangeCodeResult:
        if code == "bad-code":
            raise RuntimeError("Google rejected the code")
        return ExchangeCodeResult(
            access_token="fake-access-token",
            refresh_token="fake-refresh-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            account_email="connected@example.com",
            scopes=["https://www.googleapis.com/auth/calendar.events"],
        )

    async def refresh_access_token(self, refresh_token: str):
        raise NotImplementedError("not exercised by these tests")

    async def create_meeting(self, access_token: str, meeting_input):
        raise NotImplementedError("not exercised by these tests")

    async def delete_meeting(self, access_token: str, provider_meeting_id: str) -> None:
        raise NotImplementedError("not exercised by these tests")


@pytest.fixture(autouse=True)
def _stub_google_meet_provider(monkeypatch):
    monkeypatch.setitem(registry._REGISTRY, MeetingProvider.google_meet, _FakeGoogleMeetClient())


async def test_status_with_no_connection_reports_not_connected(client):
    headers = await manager_headers()
    response = await client.get("/api/integrations/status", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"] == [
        {"provider": "google_meet", "connected": False, "accountEmail": None}
    ]


async def test_authorize_url_embeds_a_verifiable_signed_state(client):
    headers = await manager_headers()
    response = await client.get("/api/integrations/google/authorize-url", headers=headers)
    assert response.status_code == 200, response.text
    url = response.json()["data"]["url"]
    assert url.startswith("https://accounts.google.com/o/oauth2/auth?state=")

    state = url.split("state=", 1)[1]
    payload = crypto.verify_state(state)
    # The signed state carries the requesting user's id, not anything client-supplied.
    assert isinstance(payload.user_id, int)


async def test_authorize_url_requires_authentication(client):
    response = await client.get("/api/integrations/google/authorize-url")
    assert response.status_code == 401


async def test_callback_without_code_or_state_redirects_with_error(client):
    response = await client.get("/oauth/google/callback", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].endswith("/settings/integrations?error=google_meet")


async def test_callback_with_invalid_state_redirects_with_error(client):
    response = await client.get(
        "/oauth/google/callback",
        params={"code": "some-code", "state": "garbage-not-a-real-state"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert response.headers["location"].endswith("/settings/integrations?error=google_meet")


async def test_callback_when_the_provider_rejects_the_code_redirects_with_error(client):
    state = crypto.sign_state(1, ttl_seconds=600)
    response = await client.get(
        "/oauth/google/callback", params={"code": "bad-code", "state": state}, follow_redirects=False
    )
    assert response.status_code in (302, 307)
    assert response.headers["location"].endswith("/settings/integrations?error=google_meet")


async def test_callback_success_connects_then_status_and_disconnect_reflect_it(client):
    headers = await manager_headers()
    me_response = await client.get("/api/users/me", headers=headers)
    user_id = me_response.json()["data"]["id"]

    state = crypto.sign_state(user_id, ttl_seconds=600)
    callback_response = await client.get(
        "/oauth/google/callback", params={"code": "good-code", "state": state}, follow_redirects=False
    )
    assert callback_response.status_code in (302, 307)
    assert callback_response.headers["location"].endswith(
        "/settings/integrations?connected=google_meet"
    )

    status_response = await client.get("/api/integrations/status", headers=headers)
    assert status_response.json()["data"] == [
        {"provider": "google_meet", "connected": True, "accountEmail": "connected@example.com"}
    ]

    disconnect_response = await client.delete("/api/integrations/google", headers=headers)
    assert disconnect_response.status_code == 200
    assert disconnect_response.json()["data"] == {"disconnected": True}

    status_after = await client.get("/api/integrations/status", headers=headers)
    assert status_after.json()["data"] == [
        {"provider": "google_meet", "connected": False, "accountEmail": None}
    ]


async def test_disconnect_with_nothing_connected_is_a_safe_no_op(client):
    headers = await manager_headers()
    response = await client.delete("/api/integrations/google", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == {"disconnected": True}


async def test_status_for_another_user_requires_manager_role(client):
    interviewer_token = await make_bearer_token(email="interviewer@example.com", role="interviewer")
    interviewer_headers = {"Authorization": f"Bearer {interviewer_token}"}

    response = await client.get("/api/integrations/status/1", headers=interviewer_headers)
    assert response.status_code == 403
