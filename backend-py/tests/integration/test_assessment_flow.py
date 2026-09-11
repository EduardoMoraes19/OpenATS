"""Real end-to-end tests of the assessment + assessment-execution modules:
invite deduplication, the public token-based attempt flow, and grading -
ported from assessment-execution.service.ts.
"""

from __future__ import annotations

import pytest

from tests.integration.helpers import apply_candidate, create_job, manager_headers

pytestmark = pytest.mark.asyncio


async def _create_assessment_with_mc_question(client, headers) -> dict:
    response = await client.post(
        "/api/assessments",
        json={
            "title": "Basic Python Quiz",
            "timeLimit": 30,
            "questions": [
                {
                    "title": "Which keyword defines a function in Python?",
                    "questionType": "multiple_choice",
                    "points": "10",
                    "position": 1,
                    "options": [
                        {"label": "def", "isCorrect": True, "position": 1},
                        {"label": "func", "isCorrect": False, "position": 2},
                    ],
                }
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_invite_reuses_active_attempt_instead_of_duplicating(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])
    assessment = await _create_assessment_with_mc_question(client, headers)

    first_invite = await client.post(
        "/api/assessment-execution/invite",
        json={"candidateId": candidate["id"], "assessmentId": assessment["id"]},
        headers=headers,
    )
    assert first_invite.status_code == 201, first_invite.text
    assert first_invite.json()["data"]["didSendInvite"] is True

    second_invite = await client.post(
        "/api/assessment-execution/invite",
        json={"candidateId": candidate["id"], "assessmentId": assessment["id"]},
        headers=headers,
    )
    assert second_invite.status_code == 201
    assert second_invite.json()["data"]["didSendInvite"] is False
    assert second_invite.json()["data"]["attemptId"] == first_invite.json()["data"]["attemptId"]


async def test_public_attempt_flow_start_answer_complete_grades_correctly(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])
    assessment = await _create_assessment_with_mc_question(client, headers)

    invite = await client.post(
        "/api/assessment-execution/invite",
        json={"candidateId": candidate["id"], "assessmentId": assessment["id"]},
        headers=headers,
    )
    token = invite.json()["data"]["token"]

    detail_response = await client.get(f"/public/assessment/{token}")
    assert detail_response.status_code == 200
    question = detail_response.json()["data"]["questions"][0]
    correct_option_id = next(o["id"] for o in question["options"] if o["label"] == "def")

    start_response = await client.post(f"/public/assessment/{token}/start")
    assert start_response.status_code == 200
    assert start_response.json()["data"]["status"] == "started"

    answer_response = await client.post(
        f"/public/assessment/{token}/answer",
        json={"questionId": question["id"], "optionIds": [correct_option_id]},
    )
    assert answer_response.status_code == 200, answer_response.text

    complete_response = await client.post(f"/public/assessment/{token}/complete")
    assert complete_response.status_code == 200, complete_response.text
    completed = complete_response.json()
    # completeAssessment's response is {message, data: {passed, scorePercentage}}
    # (both siblings of "data"), not the full attempt object.
    assert completed["message"] == "Assessment completed successfully"
    assert float(completed["data"]["scorePercentage"]) == 100.0
    assert completed["data"]["passed"] is None, "no pass/fail threshold is implemented - must stay null"


async def test_wrong_answer_scores_zero(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])
    assessment = await _create_assessment_with_mc_question(client, headers)

    invite = await client.post(
        "/api/assessment-execution/invite",
        json={"candidateId": candidate["id"], "assessmentId": assessment["id"]},
        headers=headers,
    )
    token = invite.json()["data"]["token"]
    detail = (await client.get(f"/public/assessment/{token}")).json()["data"]
    question = detail["questions"][0]
    wrong_option_id = next(o["id"] for o in question["options"] if o["label"] == "func")

    await client.post(f"/public/assessment/{token}/start")
    await client.post(
        f"/public/assessment/{token}/answer",
        json={"questionId": question["id"], "optionIds": [wrong_option_id]},
    )
    completed = (await client.post(f"/public/assessment/{token}/complete")).json()

    assert float(completed["data"]["scorePercentage"]) == 0.0
