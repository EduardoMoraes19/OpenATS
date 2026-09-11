"""Shared test fixtures.

`make_bearer_token` creates a real `User` row in the test database (self-
hosted auth has no JIT provisioning any more - `get_user_from_token` does a
plain lookup by numeric id, so a token is only valid if a matching row
already exists) and returns a bearer token for it, signed the same way
`app.shared.auth.jwt_auth.create_access_token` signs a real login token
(HS256, `settings.secret_key`).
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.base import async_session_factory, engine
from app.db.models.enums import AppRole
from app.db.models.users import User
from app.settings import settings
from app.shared.auth.jwt_auth import create_access_token, hash_password
from app.shared.rate_limit import redis_client

if "_test" not in settings.database_url and ":5433" not in settings.database_url:
    raise RuntimeError(
        "Integration tests truncate every table before each test and refuse to run "
        "against anything but the dedicated test database (port 5433 / *_test). "
        f"DATABASE_URL was: {settings.database_url}"
    )

# pipeline_stage_templates is deliberately NOT in this list: it is global
# seed data (app/db/seed.py) the app requires to function, not per-test
# state - see the session-scoped _seed_pipeline_templates fixture below.
_APP_TABLES = (
    "company", "departments", "users", "templates", "jobs", "job_skills",
    "job_pipeline_stages", "job_hiring_team",
    "assessments", "assessment_questions", "assessment_question_options",
    "job_custom_questions", "job_custom_question_options", "job_assessment_attachments",
    "candidates", "candidate_stage_history", "candidate_custom_answers",
    "candidate_custom_answer_selections", "candidate_assessment_attempts",
    "candidate_assessment_answers", "candidate_assessment_answer_selections",
    "candidate_cv_analysis", "offers", "candidate_activities", "email_messages",
    "job_chat_messages", "candidate_chat_messages", "candidate_rejections",
    "candidate_interviews", "interview_feedback", "integration_connections",
    "public_page_settings",
)


async def make_bearer_token(
    *,
    email: str,
    role: str = "super_admin",
    password: str = "TestPassword123!",
    first_name: str = "Test",
    last_name: str = "User",
) -> str:
    """Creates a real, active `User` row with a bcrypt-hashed password and
    `token_version=0`, then mints a valid access token for it - the local-
    auth replacement for the old RS256/JWKS-mocked `make_bearer_token`.
    Every caller needs a unique `email` per user it wants to exist (tests
    already pick distinct emails for isolation; `_clean_database` truncates
    `users` between tests, so the same email is safe to reuse across
    different test functions)."""
    async with async_session_factory() as session:
        user = User(
            email=email,
            password_hash=hash_password(password),
            role=AppRole(role),
            token_version=0,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    return create_access_token(user_id=user_id, role=role, token_version=0)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _seed_pipeline_templates():
    from app.db.seed import seed_pipeline_stage_templates

    await seed_pipeline_stage_templates()


@pytest_asyncio.fixture(autouse=True)
async def _clean_database():
    """Gives every test a clean slate - each test's fixtures/assertions
    should not depend on what an earlier test left behind."""
    tables = ", ".join(_APP_TABLES)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_rate_limits():
    """The test Redis is the same instance dev/prod would use (docker-compose.yml
    has one Redis, not a separate test one), so this only ever deletes
    `ratelimit:*` keys - never a blanket FLUSHDB - to avoid clobbering
    unrelated data. Without this, apply_limiter's 5-per-15-min cap (keyed by
    the constant "IP" every ASGITransport request shares) would fail later
    tests in the same run, not because of a real bug but because the whole
    suite looks like one client hammering the endpoint."""
    async for key in redis_client.scan_iter(match="ratelimit:*"):
        await redis_client.delete(key)
    yield


@pytest_asyncio.fixture
async def client():
    from app.main import fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
