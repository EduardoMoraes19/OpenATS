"""Real end-to-end integration tests against the live postgres-test database
(port 5433) - exercises auth (JWT verification against a real `User` row),
the DB layer, and representative business logic through actual HTTP
requests.
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


async def test_me_endpoint_returns_the_authenticated_user(client):
    token = await make_bearer_token(email="admin@example.com", role="super_admin")
    response = await client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["email"] == "admin@example.com"
    assert body["role"] == "super_admin"


async def test_create_company_then_department_then_job_full_flow(client):
    admin_token = await make_bearer_token(email="flow-admin@example.com", role="super_admin")
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


async def test_public_jobs_list_returns_minimal_curated_shape(client):
    """job.service.ts's `listPublishedForCareers` deliberately curates the
    careers index down to id/slug/title/employmentType/location/
    departmentName/createdAt - it must not leak departmentId, description,
    the salary breakdown, or skills, and must join in the department's name
    rather than its id."""
    admin_token = await make_bearer_token(email="careers-admin@example.com", role="super_admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    company_response = await client.put(
        "/api/company", json={"name": "Careers Co", "email": "careers@example.com"}, headers=headers
    )
    assert company_response.status_code == 200

    department_response = await client.post(
        "/api/company/departments", json={"name": "Careers Dept"}, headers=headers
    )
    assert department_response.status_code == 201, department_response.text
    department_id = department_response.json()["data"]["id"]

    job_response = await client.post(
        "/api/jobs",
        json={
            "title": "Support Engineer",
            "departmentId": department_id,
            "employmentType": "full_time",
            "status": "published",
            "salaryType": "fixed",
            "currency": "USD",
            "payFrequency": "yearly",
            "salaryFixed": 90000,
            "skills": ["SQL"],
        },
        headers=headers,
    )
    assert job_response.status_code == 201, job_response.text
    slug = job_response.json()["data"]["slug"]

    public_response = await client.get("/public/jobs")
    assert public_response.status_code == 200
    listed = next(j for j in public_response.json()["data"] if j["slug"] == slug)

    assert listed == {
        "id": listed["id"],
        "slug": slug,
        "title": "Support Engineer",
        "employmentType": "full_time",
        "location": None,
        "departmentName": "Careers Dept",
        "createdAt": listed["createdAt"],
    }


async def test_public_job_detail_adds_status_and_timestamps_to_the_full_shape(client):
    """job.controller.ts's `getPublicJobById` returns the full internal job
    row (departmentId and the salary breakdown included) minus hiringTeam/
    pipelineStages/createdBy, plus status/applicationEmailTemplateId/
    createdAt/updatedAt."""
    admin_token = await make_bearer_token(email="job-detail-admin@example.com", role="super_admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    company_response = await client.put(
        "/api/company", json={"name": "Detail Co", "email": "detail@example.com"}, headers=headers
    )
    assert company_response.status_code == 200

    department_response = await client.post(
        "/api/company/departments", json={"name": "Detail Dept"}, headers=headers
    )
    assert department_response.status_code == 201, department_response.text
    department_id = department_response.json()["data"]["id"]

    job_response = await client.post(
        "/api/jobs",
        json={
            "title": "Platform Engineer",
            "departmentId": department_id,
            "employmentType": "full_time",
            "status": "published",
        },
        headers=headers,
    )
    job = job_response.json()["data"]

    detail_response = await client.get(f"/public/jobs/{job['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]

    assert detail["id"] == job["id"]
    assert detail["departmentId"] == department_id
    assert detail["status"] == "published"
    assert detail["applicationEmailTemplateId"] is None
    assert detail["createdAt"] == job["createdAt"]
    assert detail["updatedAt"] == job["updatedAt"]
    assert "hiringTeam" not in detail
    assert "pipelineStages" not in detail
    assert "createdBy" not in detail


async def test_responses_are_camel_case_matching_the_frontend(client):
    """The TS backend's Drizzle models map snake_case DB columns to camelCase
    TS properties (e.g. `firstName: varchar("first_name")`), and the
    frontend's TS types are written against that camelCase shape. Every
    Pydantic schema here must alias to camelCase on the way out (see
    app/shared/schema.py) or the frontend would silently receive undefined
    for every multi-word field."""
    admin_token = await make_bearer_token(email="camel-admin@example.com", role="super_admin")
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


async def test_timestamps_are_z_suffixed_matching_the_frontend(client):
    """Every `timestamp` column here is WITHOUT TIME ZONE (see
    app/shared/schema.py's UtcDatetime), but the TS backend's
    `Date.toISOString()` always emits a `Z`-suffixed UTC string. A bare,
    offset-less timestamp is ambiguous to a JS `Date` parser and can shift
    displayed times by the viewer's local UTC offset."""
    admin_token = await make_bearer_token(email="tz-admin@example.com", role="super_admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    company_response = await client.put(
        "/api/company", json={"name": "TZ Co", "email": "tz@example.com"}, headers=headers
    )
    assert company_response.status_code == 200

    department_response = await client.post(
        "/api/company/departments", json={"name": "TZ Dept"}, headers=headers
    )
    assert department_response.status_code == 201
    body = department_response.json()["data"]
    assert body["createdAt"].endswith("Z"), f"expected a Z-suffixed timestamp, got: {body['createdAt']!r}"


async def test_manager_role_required_for_write_routes(client):
    interviewer_token = await make_bearer_token(email="interviewer@example.com", role="interviewer")
    response = await client.post(
        "/api/company/departments",
        json={"name": "Should Be Forbidden"},
        headers={"Authorization": f"Bearer {interviewer_token}"},
    )
    assert response.status_code == 403
