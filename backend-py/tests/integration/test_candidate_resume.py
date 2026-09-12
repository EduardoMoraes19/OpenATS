"""Real end-to-end tests of GET /api/candidates/:id/resume - the PDF
streaming proxy behind the candidate's resume viewer. Ported from
candidate.controller.ts's getCandidateResume, which was added to the TS
backend after the initial backend-py port and never carried over.
"""

from __future__ import annotations

import pytest

from app.settings import settings
from app.shared.services import r2_service
from tests.integration.helpers import apply_candidate, create_job, manager_headers

pytestmark = pytest.mark.asyncio


def _fake_upload_file(*, content: bytes, content_type: str, folder: str) -> str:
    return f"{settings.r2_public_url.rstrip('/')}/{folder}/fake-file.pdf"


def _fake_download_with_content_type(key: str) -> tuple[bytes, str]:
    return b"%PDF-1.4 fake resume bytes", "application/pdf"


@pytest.fixture(autouse=True)
def _stub_r2(monkeypatch):
    monkeypatch.setattr(r2_service, "upload_file", _fake_upload_file)
    monkeypatch.setattr(r2_service, "download_file_with_content_type", _fake_download_with_content_type)


async def _candidate_with_resume(client, headers) -> dict:
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])
    response = await client.patch(
        f"/api/candidates/{candidate['id']}",
        files={"resume": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return candidate


async def test_resume_requires_authentication(client):
    headers = await manager_headers()
    candidate = await _candidate_with_resume(client, headers)

    response = await client.get(f"/api/candidates/{candidate['id']}/resume")

    assert response.status_code == 401


async def test_resume_streams_pdf_bytes(client):
    headers = await manager_headers()
    candidate = await _candidate_with_resume(client, headers)

    response = await client.get(f"/api/candidates/{candidate['id']}/resume", headers=headers)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == "inline"
    assert response.content == b"%PDF-1.4 fake resume bytes"


async def test_resume_404s_when_candidate_has_none(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])

    response = await client.get(f"/api/candidates/{candidate['id']}/resume", headers=headers)

    assert response.status_code == 404
