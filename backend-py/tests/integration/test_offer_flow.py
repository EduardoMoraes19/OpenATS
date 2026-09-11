"""Real end-to-end tests of the offer module: the status state machine,
auto-draft-creation on stage move, the send/accept flow, and mark-as-hired -
the highest-risk business logic ported from offer.service.ts.
"""

from __future__ import annotations

import pytest

from app.modules.offer import service as offer_service
from tests.integration.helpers import (
    apply_candidate,
    create_job,
    get_pipeline_stages,
    manager_headers,
    move_candidate_to_stage,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _stub_offer_email(monkeypatch):
    """offer.service.ts's send() awaits the email with no try/catch - a real
    provider failure (these tests use a dummy RESEND_API_KEY, never a real
    network call) would surface as a 400, ported in offer/service.py's
    send_offer(). Stub the send itself so these tests exercise the offer
    state machine, not Resend's reachability."""

    async def _noop(**kwargs: object) -> None:
        return None

    monkeypatch.setattr(offer_service.mail_service, "send_offer_email", _noop)


def _stage_id_by_type(stages: list[dict], stage_type: str) -> int:
    matches = [s for s in stages if s["stageType"] == stage_type]
    assert matches, f"no {stage_type}-type stage found in seeded pipeline: {stages}"
    return matches[0]["id"]


async def test_moving_candidate_into_offer_stage_auto_creates_draft_offer(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    offer_stage_id = _stage_id_by_type(stages, "offer")

    candidate = await apply_candidate(client, job["id"])
    move_result = await move_candidate_to_stage(client, headers, candidate["id"], offer_stage_id)

    # candidate.service.ts's StageAutomationFlags never reports offer-draft
    # creation to the client - only the assessment-invite outcome, and only
    # when an assessment is actually attached to the target stage (it isn't
    # here), so stageAutomation is an empty object.
    assert move_result["stageAutomation"] == {}
    assert move_result["data"]["status"] == "offered"

    offers_response = await client.get(f"/api/offers/job/{job['id']}", headers=headers)
    assert offers_response.status_code == 200
    offers = offers_response.json()["data"]
    assert len(offers) == 1
    assert offers[0]["status"] == "draft"
    assert offers[0]["candidateId"] == candidate["id"]


async def test_offer_creation_is_idempotent_by_candidate_and_job(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])

    first = await client.post(
        "/api/offers", json={"candidateId": candidate["id"], "jobId": job["id"]}, headers=headers
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        "/api/offers", json={"candidateId": candidate["id"], "jobId": job["id"]}, headers=headers
    )
    assert second.status_code == 201
    assert second.json()["data"]["id"] == first.json()["data"]["id"], "must return the existing offer, not duplicate"


async def test_offer_status_machine_rejects_invalid_transition(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])
    create_response = await client.post(
        "/api/offers", json={"candidateId": candidate["id"], "jobId": job["id"]}, headers=headers
    )
    offer_id = create_response.json()["data"]["id"]

    # draft -> accepted is not an allowed direct transition (must go through sent/viewed).
    response = await client.patch(f"/api/offers/{offer_id}", json={"status": "accepted"}, headers=headers)
    assert response.status_code == 400


async def test_send_offer_requires_all_fields_then_succeeds(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])
    create_response = await client.post(
        "/api/offers", json={"candidateId": candidate["id"], "jobId": job["id"]}, headers=headers
    )
    offer_id = create_response.json()["data"]["id"]

    incomplete_send = await client.post(f"/api/offers/{offer_id}/send", headers=headers)
    assert incomplete_send.status_code == 400, "must reject sending an offer missing required fields"

    fill_response = await client.patch(
        f"/api/offers/{offer_id}",
        json={
            "salary": "120000.00",
            "currency": "USD",
            "employmentType": "full_time",
            "startDate": "2026-01-15",
            "reportingManager": "Alex Manager",
            "benefits": "Health, dental, 401k",
            "offerLetterHtml": "<p>Welcome!</p>",
        },
        headers=headers,
    )
    assert fill_response.status_code == 200, fill_response.text

    send_response = await client.post(f"/api/offers/{offer_id}/send", headers=headers)
    assert send_response.status_code == 200, send_response.text
    sent_offer = send_response.json()["data"]
    assert sent_offer["status"] == "sent"
    assert sent_offer["reviewToken"], "send() must generate a review token"


async def test_offer_detail_and_list_embed_candidate_job_template(client):
    """offer.service.ts's `getById`/`getAllDetails`/`getPaginated` embed the
    related candidate/job/template via Drizzle relational queries - the list
    variants additionally nest the candidate's current stage and the job's
    department, a level `getById` omits."""
    headers = await manager_headers()
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    candidate = await apply_candidate(client, job["id"])
    create_response = await client.post(
        "/api/offers", json={"candidateId": candidate["id"], "jobId": job["id"]}, headers=headers
    )
    offer_id = create_response.json()["data"]["id"]

    detail = (await client.get(f"/api/offers/{offer_id}", headers=headers)).json()["data"]
    assert detail["candidate"]["id"] == candidate["id"]
    assert detail["job"]["id"] == job["id"]
    assert "currentStage" not in detail["candidate"]
    assert "department" not in detail["job"]

    list_body = (await client.get("/api/offers", headers=headers)).json()
    listed = next(o for o in list_body["data"] if o["id"] == offer_id)
    assert listed["candidate"]["id"] == candidate["id"]
    assert listed["candidate"]["currentStage"]["id"] == stages[0]["id"]
    assert listed["job"]["id"] == job["id"]
    assert listed["job"]["department"]["id"] == job["departmentId"]

    paginated_body = (await client.get("/api/offers?page=1", headers=headers)).json()
    paginated = next(o for o in paginated_body["data"] if o["id"] == offer_id)
    assert paginated["candidate"]["currentStage"]["id"] == stages[0]["id"]
    assert paginated["job"]["department"]["id"] == job["departmentId"]


async def test_public_offer_flow_view_then_accept_then_mark_hired(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    offer_stage_id = _stage_id_by_type(stages, "offer")
    candidate = await apply_candidate(client, job["id"])
    await move_candidate_to_stage(client, headers, candidate["id"], offer_stage_id)

    offer = (await client.get(f"/api/offers/job/{job['id']}", headers=headers)).json()["data"][0]
    await client.patch(
        f"/api/offers/{offer['id']}",
        json={
            "salary": "95000.00",
            "currency": "USD",
            "employmentType": "full_time",
            "startDate": "2026-02-01",
            "reportingManager": "Sam Lead",
            "benefits": "PTO",
            "offerLetterHtml": "<p>Offer</p>",
        },
        headers=headers,
    )
    sent = (await client.post(f"/api/offers/{offer['id']}/send", headers=headers)).json()["data"]
    token = sent["reviewToken"]

    # First public view transitions sent -> viewed (side effect of get_public_by_token).
    view_response = await client.get(f"/public/offers/{token}")
    assert view_response.status_code == 200
    view_data = view_response.json()["data"]
    assert view_data["status"] == "viewed"
    # offer.service.ts's `getPublicByToken` returns the curated view shape:
    # id/timestamps/candidateEmail included, but no candidateId/jobId/
    # reviewToken/createdBy - those only appear on the accept/decline shape.
    assert view_data["id"] == offer["id"]
    assert view_data["candidateEmail"] == candidate["email"]
    assert view_data["candidateName"] == f"{candidate['firstName']} {candidate['lastName']}"
    assert view_data["jobTitle"] == job["title"]
    assert view_data["sentAt"] is not None
    assert view_data["viewedAt"] is not None
    assert view_data["acceptedAt"] is None
    assert view_data["declinedAt"] is None
    assert "reviewToken" not in view_data
    assert "candidateId" not in view_data

    accept_response = await client.post(f"/public/offers/{token}/accept")
    assert accept_response.status_code == 200
    accept_data = accept_response.json()["data"]
    assert accept_data["status"] == "accepted"
    # Unlike the view endpoint, accept (and decline, see below) return the
    # full raw offer row - same shape as the authenticated
    # `GET /api/offers/:id` base object, reviewToken/createdBy included -
    # not the curated candidateName/jobTitle shape. Preserved asymmetry.
    assert accept_data["id"] == offer["id"]
    assert accept_data["candidateId"] == candidate["id"]
    assert accept_data["jobId"] == job["id"]
    assert accept_data["reviewToken"] == token
    assert accept_data["createdBy"] is not None
    assert accept_data["acceptedAt"] is not None
    assert accept_data["createdAt"] is not None
    assert accept_data["updatedAt"] is not None
    assert "candidateName" not in accept_data
    assert "jobTitle" not in accept_data

    hire_response = await client.post(f"/api/offers/{offer['id']}/mark-hired", headers=headers)
    assert hire_response.status_code == 200, hire_response.text
    hire_data = hire_response.json()["data"]
    # markAsHired's response is {candidate, hiredStage} - not the offer object.
    assert hire_data["candidate"]["status"] == "hired"
    assert hire_data["hiredStage"]["name"].lower() == "hired"

    candidate_response = await client.get(f"/api/candidates/{candidate['id']}", headers=headers)
    assert candidate_response.json()["data"]["status"] == "hired"
    assert candidate_response.json()["data"]["currentStageId"] == hire_data["hiredStage"]["id"]


async def test_public_offer_decline_also_returns_the_full_raw_offer_shape(client):
    """Same asymmetry as accept in the flow test above: offer.controller.ts's
    `declinePublicOffer` also returns the full raw offer row, not the
    curated public view shape."""
    headers = await manager_headers()
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    offer_stage_id = _stage_id_by_type(stages, "offer")
    candidate = await apply_candidate(client, job["id"], email="decliner@example.com")
    await move_candidate_to_stage(client, headers, candidate["id"], offer_stage_id)

    offer = (await client.get(f"/api/offers/job/{job['id']}", headers=headers)).json()["data"][0]
    await client.patch(
        f"/api/offers/{offer['id']}",
        json={
            "salary": "80000.00",
            "currency": "USD",
            "employmentType": "full_time",
            "startDate": "2026-03-01",
            "reportingManager": "Sam Lead",
            "benefits": "PTO",
            "offerLetterHtml": "<p>Offer</p>",
        },
        headers=headers,
    )
    sent = (await client.post(f"/api/offers/{offer['id']}/send", headers=headers)).json()["data"]
    token = sent["reviewToken"]

    decline_response = await client.post(f"/public/offers/{token}/decline")
    assert decline_response.status_code == 200
    decline_data = decline_response.json()["data"]
    assert decline_data["status"] == "declined"
    assert decline_data["candidateId"] == candidate["id"]
    assert decline_data["jobId"] == job["id"]
    assert decline_data["reviewToken"] == token
    assert decline_data["declinedAt"] is not None
    assert "candidateName" not in decline_data
    assert "jobTitle" not in decline_data
