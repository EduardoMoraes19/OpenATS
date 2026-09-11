"""Real end-to-end tests of the self-hosted auth module (app/modules/auth):
login, logout, and change-password against the actual JWT/bcrypt/
token_version machinery in app/shared/auth/jwt_auth.py, not mocked.

/api/auth/* is envelope-wrapped like the rest of /api/* on success
(EnvelopeMiddleware), but error responses go through
register_error_handlers's `{"error": message}` shape instead of FastAPI's
default `{"detail": ...}` - see app/shared/middleware/error_handlers.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models.users import User
from tests.conftest import make_bearer_token

pytestmark = pytest.mark.asyncio

_PASSWORD = "CorrectHorse123!"


async def _deactivate(email: str) -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.is_active = False
        await session.commit()


async def test_login_succeeds_and_the_returned_token_authenticates(client):
    await make_bearer_token(email="login@example.com", role="super_admin", password=_PASSWORD)

    response = await client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": _PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["tokenType"] == "bearer"
    assert body["user"]["email"] == "login@example.com"
    assert body["user"]["role"] == "super_admin"

    me_response = await client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {body['accessToken']}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["data"]["email"] == "login@example.com"


async def test_login_with_wrong_password_is_rejected_with_a_generic_message(client):
    await make_bearer_token(email="wrongpass@example.com", password=_PASSWORD)

    response = await client.post(
        "/api/auth/login",
        json={"email": "wrongpass@example.com", "password": "NotTheRightOne123!"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "Invalid email or password"

    # An email that doesn't exist at all gets the exact same message and
    # status - no signal that would let a caller enumerate valid accounts.
    unknown_response = await client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "WhateverItIs123!"}
    )
    assert unknown_response.status_code == 401
    assert unknown_response.json()["error"] == "Invalid email or password"


async def test_login_for_a_deactivated_user_is_rejected(client):
    await make_bearer_token(email="deactivated@example.com", password=_PASSWORD)
    await _deactivate("deactivated@example.com")

    response = await client.post(
        "/api/auth/login", json={"email": "deactivated@example.com", "password": _PASSWORD}
    )
    assert response.status_code == 401


async def test_logout_invalidates_the_token(client):
    await make_bearer_token(email="logout@example.com", password=_PASSWORD)
    login_response = await client.post(
        "/api/auth/login", json={"email": "logout@example.com", "password": _PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login_response.json()['data']['accessToken']}"}

    logout_response = await client.post("/api/auth/logout", headers=headers)
    assert logout_response.status_code == 200, logout_response.text

    # Same token, same session - token_version has moved on, so it's dead.
    stale_request = await client.get("/api/users/me", headers=headers)
    assert stale_request.status_code == 401


async def test_change_password_with_wrong_current_password_is_rejected(client):
    await make_bearer_token(email="changepw-wrong@example.com", password=_PASSWORD)
    login_response = await client.post(
        "/api/auth/login", json={"email": "changepw-wrong@example.com", "password": _PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login_response.json()['data']['accessToken']}"}

    response = await client.post(
        "/api/auth/change-password",
        json={"currentPassword": "TotallyWrongPassword123!", "newPassword": "BrandNewPass123!"},
        headers=headers,
    )
    assert response.status_code == 401


async def test_change_password_success_invalidates_old_tokens_and_a_new_login_works(client):
    await make_bearer_token(email="changepw-ok@example.com", password=_PASSWORD)
    login_response = await client.post(
        "/api/auth/login", json={"email": "changepw-ok@example.com", "password": _PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login_response.json()['data']['accessToken']}"}

    new_password = "BrandNewPass123!"
    change_response = await client.post(
        "/api/auth/change-password",
        json={"currentPassword": _PASSWORD, "newPassword": new_password},
        headers=headers,
    )
    assert change_response.status_code == 200, change_response.text

    # Same invalidation check as logout: the pre-change token is dead.
    stale_request = await client.get("/api/users/me", headers=headers)
    assert stale_request.status_code == 401

    new_login = await client.post(
        "/api/auth/login", json={"email": "changepw-ok@example.com", "password": new_password}
    )
    assert new_login.status_code == 200, new_login.text
