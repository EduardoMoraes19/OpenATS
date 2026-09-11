"""Real end-to-end tests of the interview module: the candidate
self-scheduling flow (time slots + public token), the atomic slot-claim
that prevents double-booking on the same interview, and the cross-interview
collision / expired-token guards - ported from public.routes.ts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.db.base import async_session_factory
from app.db.models.interviews import CandidateInterview
from tests.integration.helpers import apply_candidate, create_job, get_pipeline_stages, manager_headers

pytestmark = pytest.mark.asyncio


def _future_slots(count: int = 2, *, start_offset_hours: int = 0) -> list[str]:
    base = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3, hours=start_offset_hours)
    return [(base + timedelta(hours=i)).isoformat() for i in range(count)]


async def _interviewer_id(client, headers: dict) -> int:
    response = await client.get("/api/users/me", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


async def _expire_token(token: str) -> None:
    """Directly back-dates an interview's token_expires_at, bypassing the
    5-day TTL the schedule endpoint sets, to exercise the expired-link path."""
    async with async_session_factory() as session:
        await session.execute(
            update(CandidateInterview)
            .where(CandidateInterview.public_token == token)
            .values(token_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1))
        )
        await session.commit()


async def test_schedule_interview_then_public_select_slot(client, rsa_keypair):
    headers = await manager_headers(rsa_keypair)
    interviewer_id = await _interviewer_id(client, headers)
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    interview_stage = next(s for s in stages if s["stageType"] == "interview")
    candidate = await apply_candidate(client, job["id"])

    schedule_response = await client.post(
        f"/api/candidates/{candidate['id']}/schedule",
        json={
            "stageId": interview_stage["id"],
            "eventName": "Technical Interview",
            "eventType": "onsite",
            "location": "HQ, 3rd floor",
            "interviewerId": interviewer_id,
            "timeSlots": [{"datetime": dt, "selected": False} for dt in _future_slots()],
        },
        headers=headers,
    )
    assert schedule_response.status_code == 201, schedule_response.text
    interview = schedule_response.json()["data"]
    assert interview["status"] == "pending_schedule"
    token = interview["publicToken"]
    assert token

    public_view = await client.get(f"/public/interview/{token}")
    assert public_view.status_code == 200
    public_body = public_view.json()["data"]
    assert len(public_body["timeSlots"]) == 2
    assert all(not slot["taken"] for slot in public_body["timeSlots"])

    select_response = await client.patch(f"/public/interview/{token}/select", json={"slotIndex": 0})
    assert select_response.status_code == 200, select_response.text
    body = select_response.json()["data"]
    assert body["confirmed"] is True
    assert body["slot"]["selected"] is True
    assert body["slot"]["datetime"] == public_body["timeSlots"][0]["datetime"]


async def test_selecting_a_slot_twice_is_rejected_as_conflict(client, rsa_keypair):
    """The atomic UPDATE ... WHERE status='pending_schedule' claim must
    reject a second selection attempt on the same interview token - this is
    the double-booking guard."""
    headers = await manager_headers(rsa_keypair)
    interviewer_id = await _interviewer_id(client, headers)
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    interview_stage = next(s for s in stages if s["stageType"] == "interview")
    candidate = await apply_candidate(client, job["id"])

    schedule_response = await client.post(
        f"/api/candidates/{candidate['id']}/schedule",
        json={
            "stageId": interview_stage["id"],
            "eventName": "Technical Interview",
            "eventType": "onsite",
            "location": "HQ",
            "interviewerId": interviewer_id,
            "timeSlots": [{"datetime": dt, "selected": False} for dt in _future_slots()],
        },
        headers=headers,
    )
    assert schedule_response.status_code == 201, schedule_response.text
    token = schedule_response.json()["data"]["publicToken"]

    first = await client.patch(f"/public/interview/{token}/select", json={"slotIndex": 0})
    assert first.status_code == 200, first.text

    second = await client.patch(f"/public/interview/{token}/select", json={"slotIndex": 1})
    assert second.status_code == 409, "must not allow re-selecting a slot on an already-scheduled interview"
    assert second.json().get("code") is None, "the 'already scheduled' conflict is a plain error, not SLOT_TAKEN"


async def test_selecting_a_taken_slot_on_another_interview_is_rejected(client, rsa_keypair):
    """Two different interviews, same interviewer, an overlapping time slot:
    confirming the slot on the first interview must make it unavailable on
    the second - the cross-interview `takenTimes` collision check, distinct
    from the same-interview double-booking guard above."""
    headers = await manager_headers(rsa_keypair)
    interviewer_id = await _interviewer_id(client, headers)
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    interview_stage = next(s for s in stages if s["stageType"] == "interview")
    shared_slots = _future_slots()

    async def _schedule(email: str) -> str:
        candidate = await apply_candidate(client, job["id"], email=email)
        response = await client.post(
            f"/api/candidates/{candidate['id']}/schedule",
            json={
                "stageId": interview_stage["id"],
                "eventName": "Technical Interview",
                "eventType": "onsite",
                "location": "HQ",
                "interviewerId": interviewer_id,
                "timeSlots": [{"datetime": dt, "selected": False} for dt in shared_slots],
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]["publicToken"]

    token_a = await _schedule("candidate-a@example.com")
    token_b = await _schedule("candidate-b@example.com")

    first = await client.patch(f"/public/interview/{token_a}/select", json={"slotIndex": 0})
    assert first.status_code == 200, first.text

    second = await client.patch(f"/public/interview/{token_b}/select", json={"slotIndex": 0})
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "SLOT_TAKEN"


async def test_selecting_a_slot_on_an_expired_link_is_rejected(client, rsa_keypair):
    headers = await manager_headers(rsa_keypair)
    interviewer_id = await _interviewer_id(client, headers)
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    interview_stage = next(s for s in stages if s["stageType"] == "interview")
    candidate = await apply_candidate(client, job["id"])

    schedule_response = await client.post(
        f"/api/candidates/{candidate['id']}/schedule",
        json={
            "stageId": interview_stage["id"],
            "eventName": "Technical Interview",
            "eventType": "onsite",
            "location": "HQ",
            "interviewerId": interviewer_id,
            "timeSlots": [{"datetime": dt, "selected": False} for dt in _future_slots()],
        },
        headers=headers,
    )
    assert schedule_response.status_code == 201, schedule_response.text
    token = schedule_response.json()["data"]["publicToken"]

    await _expire_token(token)

    select_response = await client.patch(f"/public/interview/{token}/select", json={"slotIndex": 0})
    assert select_response.status_code == 410
    assert select_response.json()["error"] == "This scheduling link has expired"


async def test_direct_create_interview_and_feedback_crud(client, rsa_keypair):
    headers = await manager_headers(rsa_keypair)
    interviewer_id = await _interviewer_id(client, headers)
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    interview_stage = next(s for s in stages if s["stageType"] == "interview")
    candidate = await apply_candidate(client, job["id"])

    create_response = await client.post(
        f"/api/candidates/{candidate['id']}/interviews",
        json={"stageId": interview_stage["id"], "interviewerId": interviewer_id},
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    interview_id = create_response.json()["data"]["id"]

    feedback_response = await client.post(
        f"/api/interviews/{interview_id}/feedback",
        json={"content": "Strong communication skills.", "rating": 4},
        headers=headers,
    )
    assert feedback_response.status_code == 201, feedback_response.text
    assert feedback_response.json()["data"]["rating"] == 4

    list_response = await client.get(f"/api/interviews/{interview_id}/feedback", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1

    feedback_id = feedback_response.json()["data"]["id"]
    delete_response = await client.delete(f"/api/interviews/{interview_id}/feedback/{feedback_id}", headers=headers)
    assert delete_response.status_code == 204

    list_after_delete = await client.get(f"/api/interviews/{interview_id}/feedback", headers=headers)
    assert list_after_delete.json()["data"] == []
