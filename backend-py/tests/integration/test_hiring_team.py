"""Real end-to-end tests of the hiring-team module - equivalent to
hiring-team.service.ts. Mounted under /api/jobs/:jobId/team by job/router.py.
"""

from __future__ import annotations

import pytest

from tests.conftest import make_bearer_token
from tests.integration.helpers import create_job, manager_headers

pytestmark = pytest.mark.asyncio


async def _create_second_user(client, headers, *, email: str = "member@example.com") -> int:
    response = await client.post(
        "/api/users",
        json={
            "firstName": "Team",
            "lastName": "Member",
            "email": email,
            "password": "TestPassword123!",
            "role": "hiring_manager",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


async def test_list_starts_with_just_the_creator(client):
    """job.service.ts adds the creator to job_hiring_team as part of job
    creation, so the team is never truly empty."""
    headers = await manager_headers()
    job = await create_job(client, headers)

    response = await client.get(f"/api/jobs/{job['id']}/team", headers=headers)
    assert response.status_code == 200, response.text
    members = response.json()["data"]
    assert len(members) == 1
    assert members[0]["userId"] == job["createdBy"]


async def test_add_member_then_list_returns_them_with_profile_fields(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    member_id = await _create_second_user(client, headers)

    add_response = await client.post(
        f"/api/jobs/{job['id']}/team", json={"userId": member_id}, headers=headers
    )
    assert add_response.status_code == 201, add_response.text

    list_response = await client.get(f"/api/jobs/{job['id']}/team", headers=headers)
    members = list_response.json()["data"]
    assert len(members) == 2  # the creator (added on job creation) + this new member
    new_member = next(m for m in members if m["userId"] == member_id)
    assert new_member["email"] == "member@example.com"
    assert new_member["firstName"] == "Team"


async def test_adding_the_same_member_twice_is_rejected(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    member_id = await _create_second_user(client, headers)

    first = await client.post(f"/api/jobs/{job['id']}/team", json={"userId": member_id}, headers=headers)
    assert first.status_code == 201

    second = await client.post(f"/api/jobs/{job['id']}/team", json={"userId": member_id}, headers=headers)
    assert second.status_code == 409, second.text


async def test_non_manager_cannot_add_or_remove_members(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    member_id = await _create_second_user(client, headers)

    interviewer_token = await make_bearer_token(email="interviewer@example.com", role="interviewer")
    interviewer_headers = {"Authorization": f"Bearer {interviewer_token}"}

    add_response = await client.post(
        f"/api/jobs/{job['id']}/team", json={"userId": member_id}, headers=interviewer_headers
    )
    assert add_response.status_code == 403

    remove_response = await client.delete(
        f"/api/jobs/{job['id']}/team/{member_id}", headers=interviewer_headers
    )
    assert remove_response.status_code == 403


async def test_remove_member_then_list_no_longer_shows_them(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    member_id = await _create_second_user(client, headers)
    await client.post(f"/api/jobs/{job['id']}/team", json={"userId": member_id}, headers=headers)

    remove_response = await client.delete(f"/api/jobs/{job['id']}/team/{member_id}", headers=headers)
    assert remove_response.status_code == 204

    list_response = await client.get(f"/api/jobs/{job['id']}/team", headers=headers)
    remaining = list_response.json()["data"]
    assert [m["userId"] for m in remaining] == [job["createdBy"]]


async def test_removing_someone_not_on_the_team_is_a_404(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    member_id = await _create_second_user(client, headers)

    response = await client.delete(f"/api/jobs/{job['id']}/team/{member_id}", headers=headers)
    assert response.status_code == 404


async def test_cannot_remove_the_job_creator_from_the_hiring_team(client):
    """job.service.ts adds the creator to job_hiring_team on job creation, and
    hiring-team.service.ts refuses to remove them - a job must always keep at
    least its creator as a hiring-team member."""
    headers = await manager_headers(email="creator@example.com")
    job = await create_job(client, headers)
    creator_id = job["createdBy"]

    response = await client.delete(f"/api/jobs/{job['id']}/team/{creator_id}", headers=headers)
    assert response.status_code == 403
