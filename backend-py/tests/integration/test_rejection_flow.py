"""Real end-to-end test of the rejection module - ported from
rejections.routes.ts's POST /candidates/:id/reject, which returns the
rejection record plus renderedSubject/renderedHtml as top-level siblings
of the rejection fields inside "data" (rendered once, independently of
rejection.service.ts's own internal render-and-send for the actual email).
"""

from __future__ import annotations

import pytest

from tests.integration.helpers import apply_candidate, create_job, manager_headers

pytestmark = pytest.mark.asyncio


async def _create_rejection_template(client, headers) -> dict:
    response = await client.post(
        "/api/templates",
        json={
            "name": "Standard Rejection",
            "type": "email",
            "subject": "Update on your application",
            "bodyJson": "<p>Thanks for applying, {{candidate_name}}.</p>",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_reject_with_sent_email_returns_rendered_subject_and_html(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])
    template = await _create_rejection_template(client, headers)

    response = await client.post(
        f"/api/candidates/{candidate['id']}/reject",
        json={
            "reason": "Not a fit at this time",
            "templateId": template["id"],
            "emailStatus": "sent",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    rejection = response.json()["data"]

    assert rejection["reason"] == "Not a fit at this time"
    assert rejection["emailStatus"] == "sent"
    assert rejection["renderedSubject"] == "Update on your application"
    assert "Thanks for applying" in rejection["renderedHtml"]

    candidate_response = await client.get(f"/api/candidates/{candidate['id']}", headers=headers)
    assert candidate_response.json()["data"]["status"] == "rejected"


async def test_reject_without_sending_email_leaves_rendered_fields_null(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])

    response = await client.post(
        f"/api/candidates/{candidate['id']}/reject",
        json={"reason": "Not enough experience", "emailStatus": "not_sent"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    rejection = response.json()["data"]

    assert rejection["renderedSubject"] is None
    assert rejection["renderedHtml"] is None


async def test_template_preview_uses_raw_body_as_context_with_no_candidate_enrichment(client):
    """template.controller.ts's previewTemplate is the only reachable
    handler for POST /templates/:id/preview - Express registers
    template.routes.ts (mounted at "/templates") before rejections.routes.ts's
    duplicate definition of the same resolved path, so the winning handler
    never does candidate-id enrichment or a generic-context fallback: it
    compiles the template against the raw request body verbatim, and
    returns the full compileTemplate() result (subject, bodyJson, html)."""
    headers = await manager_headers()
    template = await _create_rejection_template(client, headers)

    response = await client.post(
        f"/api/templates/{template['id']}/preview",
        json={"candidate_name": "Ada Lovelace"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]

    assert result["subject"] == "Update on your application"
    assert "Ada Lovelace" in result["html"]
    assert "bodyJson" in result
