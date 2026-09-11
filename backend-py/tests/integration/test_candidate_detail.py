"""Real end-to-end test of candidate.service.ts's `getById` composition
(GET /api/candidates/:id) - exercises every relation it embeds alongside
the bare candidate row: custom-question answers/selections, stage history,
an auto-created offer draft, and the activity it generates. cvAnalysis and
interviews are asserted null/empty here since neither is exercised by this
flow (covered separately by the CV-analysis worker tests and
test_interview_flow.py).
"""

from __future__ import annotations

import pytest

from tests.integration.helpers import create_job, get_pipeline_stages, manager_headers, move_candidate_to_stage

pytestmark = pytest.mark.asyncio


async def _create_question(client, headers, job_id: int, **kwargs) -> dict:
    response = await client.post(f"/api/jobs/{job_id}/questions", json=kwargs, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_candidate_detail_embeds_answers_history_offer_and_activities(client):
    headers = await manager_headers()
    job = await create_job(client, headers)

    short_answer_question = await _create_question(
        client, headers, job["id"],
        title="Why do you want this job?", questionType="short_answer", isRequired=True, position=1,
    )
    radio_question = await _create_question(
        client, headers, job["id"],
        title="Preferred language",
        questionType="radio",
        isRequired=True,
        position=2,
        options=[{"label": "Python", "position": 1}, {"label": "TypeScript", "position": 2}],
    )
    python_option_id = radio_question["options"][0]["id"]

    apply_response = await client.post(
        f"/public/jobs/{job['id']}/apply",
        json={
            "firstName": "Jane",
            "lastName": "Doe",
            "email": "jane.detail@example.com",
            "customAnswers": [
                {"questionId": short_answer_question["id"], "answerText": "Because I love this domain."},
                {"questionId": radio_question["id"], "optionIds": [python_option_id]},
            ],
        },
    )
    assert apply_response.status_code == 201, apply_response.text
    candidate_id = apply_response.json()["data"]["id"]

    stages = await get_pipeline_stages(client, headers, job["id"])
    offer_stage = next(s for s in stages if s["name"] == "Offer")
    await move_candidate_to_stage(client, headers, candidate_id, offer_stage["id"])

    response = await client.get(f"/api/candidates/{candidate_id}", headers=headers)
    assert response.status_code == 200, response.text
    detail = response.json()["data"]

    assert detail["id"] == candidate_id
    assert detail["stageName"] == "Offer"
    assert detail["jobTitle"] == job["title"]

    # apply_for_job writes one CandidateCustomAnswer row per submitted answer
    # regardless of question type, so the radio question's own (text-less)
    # answer row shows up here too, alongside its selection row below.
    assert len(detail["answers"]) == 2
    text_answer = next(a for a in detail["answers"] if a["questionId"] == short_answer_question["id"])
    assert text_answer["answerText"] == "Because I love this domain."
    assert text_answer["questionTitle"] == "Why do you want this job?"

    assert len(detail["selections"]) == 1
    selection = detail["selections"][0]
    assert selection["questionTitle"] == "Preferred language"
    assert selection["optionLabel"] == "Python"

    # One history row from the initial stage assignment on application,
    # one from the move into "Offer".
    assert len(detail["history"]) == 2
    assert detail["history"][-1]["stageId"] == offer_stage["id"]

    assert detail["offer"] is not None
    assert detail["offer"]["status"] == "draft"
    assert detail["offer"]["candidateId"] == candidate_id

    assert detail["cvAnalysis"] is None
    assert detail["rejections"] == []
    assert detail["interviews"] == []

    assert len(detail["activities"]) == 1
    activity = detail["activities"][0]
    assert activity["eventType"] == "offer_created"
    assert activity["stage"] is not None
    assert activity["stage"]["id"] == offer_stage["id"]
