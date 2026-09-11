"""Real end-to-end integration tests against the live postgres-test database
(port 5433) - exercises auth (JWT verify + JIT provisioning), the DB layer,
and representative business logic through actual HTTP requests.
"""

from __future__ import annotations

import pytest

from tests.conftest import make_bearer_token

pytestmark = pytest.mark.asyncio


async def test_health_reports_db_and_redis_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["redis"] == "ok"


async def test_unauthenticated_request_is_rejected(client):
    response = await client.get("/api/company")
    assert response.status_code == 401


async def test_jit_provisioning_and_me_endpoint(client, rsa_keypair):
    token = make_bearer_token(rsa_keypair, sub="user-1", email="admin@example.com", role="super_admin")
    response = await client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["email"] == "admin@example.com"
    assert body["role"] == "super_admin"


async def test_reprovisioning_reconciles_by_email_not_duplicate(client, rsa_keypair):
    """Same email, different `sub` (asgardeo_user_id) - the second call must
    reconcile onto the same user row, not violate the email unique constraint
    or create a duplicate - port of verify-token.ts's JIT provisioning order."""
    token_a = make_bearer_token(rsa_keypair, sub="sub-a", email="reconcile@example.com")
    token_b = make_bearer_token(rsa_keypair, sub="sub-b", email="reconcile@example.com")

    response_a = await client.get("/api/users/me", headers={"Authorization": f"Bearer {token_a}"})
    response_b = await client.get("/api/users/me", headers={"Authorization": f"Bearer {token_b}"})

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert response_a.json()["data"]["id"] == response_b.json()["data"]["id"]


async def test_create_company_then_department_then_job_full_flow(client, rsa_keypair):
    admin_token = make_bearer_token(rsa_keypair, sub="flow-admin", email="flow-admin@example.com", role="super_admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    company_response = await client.put(
        "/api/company",
        json={"name": "Acme Inc", "email": "hr@acme-example.com"},
        headers=headers,
    )
    assert company_response.status_code == 200, company_response.text
    assert company_response.json()["data"]["name"] == "Acme Inc"

    department_response = await client.post(
        "/api/company/departments", json={"name": "Engineering"}, headers=headers
    )
    assert department_response.status_code == 201, department_response.text
    department_id = department_response.json()["data"]["id"]

    job_response = await client.post(
        "/api/jobs",
        json={
            "title": "Backend Engineer",
            "department_id": department_id,
            "employment_type": "full_time",
            "status": "published",
        },
        headers=headers,
    )
    assert job_response.status_code == 201, job_response.text
    job_body = job_response.json()["data"]
    assert job_body["title"] == "Backend Engineer"
    assert job_body["status"] == "published"
    slug = job_body["slug"]

    # The job's pipeline should have been cloned from the 7 seeded
    # pipeline_stage_templates rows (seed.py) inside create_job()'s transaction.
    pipeline_response = await client.get(f"/api/jobs/{job_body['id']}/pipeline", headers=headers)
    assert pipeline_response.status_code == 200
    assert len(pipeline_response.json()["data"]) == 7

    # Public careers page should now list the published job with no auth.
    public_response = await client.get("/public/jobs")
    assert public_response.status_code == 200
    assert any(j["slug"] == slug for j in public_response.json()["data"])


async def test_responses_are_camel_case_matching_the_frontend(client, rsa_keypair):
    """The TS backend's Drizzle models map snake_case DB columns to camelCase
    TS properties (e.g. `firstName: varchar("first_name")`), and the
    frontend's TS types are written against that camelCase shape. Every
    Pydantic schema here must alias to camelCase on the way out (see
    app/shared/schema.py) or the frontend would silently receive undefined
    for every multi-word field."""
    admin_token = make_bearer_token(rsa_keypair, sub="camel-admin", email="camel-admin@example.com", role="super_admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    company_response = await client.put(
        "/api/company", json={"name": "Camel Co", "email": "camel@example.com"}, headers=headers
    )
    assert company_response.status_code == 200
    body = company_response.json()["data"]
    assert "logoUrl" in body, f"expected camelCase 'logoUrl', got keys: {list(body)}"
    assert "logo_url" not in body

    department_response = await client.post(
        "/api/company/departments", json={"name": "Camel Dept"}, headers=headers
    )
    assert department_response.status_code == 201
    dept_body = department_response.json()["data"]
    assert "companyId" in dept_body, f"expected camelCase 'companyId', got keys: {list(dept_body)}"

    me_response = await client.get("/api/users/me", headers=headers)
    me_body = me_response.json()["data"]
    assert "avatarUrl" in me_body, f"expected camelCase 'avatarUrl', got keys: {list(me_body)}"

    # The request side must also accept camelCase, matching what the
    # frontend actually sends (not just snake_case, which is only a
    # convenience for internal Python callers/tests).
    camel_department_response = await client.post(
        "/api/company/departments", json={"name": "Sent As CamelCase"}, headers=headers
    )
    assert camel_department_response.status_code == 201


async def test_manager_role_required_for_write_routes(client, rsa_keypair):
    interviewer_token = make_bearer_token(
        rsa_keypair, sub="interviewer-1", email="interviewer@example.com", role="interviewer"
    )
    response = await client.post(
        "/api/company/departments",
        json={"name": "Should Be Forbidden"},
        headers={"Authorization": f"Bearer {interviewer_token}"},
    )
    assert response.status_code == 403
