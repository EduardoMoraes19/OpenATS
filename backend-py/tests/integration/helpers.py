"""Shared setup helpers for integration tests - plain async functions, not
fixtures, so they always run after the autouse `_clean_database` fixture has
already truncated the tables (fixture-vs-fixture ordering between two
same-scope fixtures isn't guaranteed, but "fixtures finish before the test
body runs" is - calling these explicitly at the top of a test body sidesteps
the ambiguity entirely).
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import make_bearer_token


async def manager_headers(*, email: str = "manager@example.com") -> dict:
    token = await make_bearer_token(email=email, role="super_admin")
    return {"Authorization": f"Bearer {token}"}


async def create_job(client: AsyncClient, headers: dict, *, title: str = "Backend Engineer") -> dict:
    """Creates company -> department -> job, returns the created job body
    (including its auto-cloned pipeline stages fetched separately)."""
    company_response = await client.put(
        "/api/company", json={"name": "Acme Inc", "email": "hr@acme-example.com"}, headers=headers
    )
    assert company_response.status_code == 200, company_response.text

    department_response = await client.post(
        "/api/company/departments", json={"name": f"Dept for {title}"}, headers=headers
    )
    assert department_response.status_code == 201, department_response.text
    department_id = department_response.json()["data"]["id"]

    job_response = await client.post(
        "/api/jobs",
        json={
            "title": title,
            "departmentId": department_id,
            "employmentType": "full_time",
            "status": "published",
        },
        headers=headers,
    )
    assert job_response.status_code == 201, job_response.text
    return job_response.json()["data"]


async def get_pipeline_stages(client: AsyncClient, headers: dict, job_id: int) -> list[dict]:
    response = await client.get(f"/api/jobs/{job_id}/pipeline", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def apply_candidate(
    client: AsyncClient, job_id: int, *, email: str = "candidate@example.com", first_name: str = "Jane"
) -> dict:
    response = await client.post(
        f"/public/jobs/{job_id}/apply",
        json={"firstName": first_name, "lastName": "Doe", "email": email},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def move_candidate_to_stage(client: AsyncClient, headers: dict, candidate_id: int, stage_id: int) -> dict:
    response = await client.put(
        f"/api/candidates/{candidate_id}/stage", json={"newStageId": stage_id}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()
