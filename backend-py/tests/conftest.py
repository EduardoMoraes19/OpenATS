"""Shared test fixtures.

`bearer_token` mints a real RS256 JWT and monkeypatches
`verify_token._jwks_client.get_signing_key_from_jwt` to hand back the
matching public key directly, instead of fetching a real JWKS over HTTP -
the same technique backend/tests/helpers/jwt.ts uses (mocking the JWKS
fetch), adapted to PyJWT's `PyJWKClient`.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.base import engine
from app.settings import settings
from app.shared.auth import verify_token
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


@dataclass
class _SigningKey:
    key: object


@pytest.fixture(scope="session")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(autouse=True)
def _patch_jwks(rsa_keypair, monkeypatch):
    _, public_key = rsa_keypair
    monkeypatch.setattr(
        verify_token._jwks_client,
        "get_signing_key_from_jwt",
        lambda token: _SigningKey(key=public_key),
    )


def make_bearer_token(
    rsa_keypair, *, sub: str, email: str, role: str = "super_admin", first_name: str = "Test", last_name: str = "User"
) -> str:
    private_key, _ = rsa_keypair
    payload = {
        "sub": sub,
        "email": email,
        "given_name": first_name,
        "family_name": last_name,
        "roles": [role],
        "iss": settings.asgardeo_issuer,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


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
