"""Real end-to-end tests of the upload module - equivalent to
upload.routes.ts (staff /api/upload/*) and the public.routes.ts resume
upload handler (/public/upload/resume).

Real R2 credentials aren't available in the test environment, so the actual
network call (`r2_service.upload_file`) is monkeypatched for the success-path
tests - every FastAPI-level concern (content-type validation, size cap, auth,
rate limiting, response shape, the company.logoUrl side effect) still runs
against the real app and a real database.
"""

from __future__ import annotations

import pytest

from app.shared.services import r2_service
from tests.integration.helpers import manager_headers

pytestmark = pytest.mark.asyncio


def _fake_upload_file(*, content: bytes, content_type: str, folder: str) -> str:
    return f"https://fake-r2.example.com/{folder}/fake-file"


@pytest.fixture(autouse=True)
def _stub_r2_upload(monkeypatch):
    monkeypatch.setattr(r2_service, "upload_file", _fake_upload_file)


async def test_upload_resume_requires_authentication(client):
    response = await client.post(
        "/api/upload/resume", files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")}
    )
    assert response.status_code == 401


async def test_upload_resume_rejects_non_pdf(client):
    headers = await manager_headers()
    response = await client.post(
        "/api/upload/resume",
        files={"file": ("resume.png", b"not a pdf", "image/png")},
        headers=headers,
    )
    assert response.status_code == 400


async def test_upload_resume_rejects_files_over_10mb(client):
    headers = await manager_headers()
    oversized = b"%" * (10 * 1024 * 1024 + 1)
    response = await client.post(
        "/api/upload/resume",
        files={"file": ("resume.pdf", oversized, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 400


async def test_upload_resume_success_returns_the_stored_url(client):
    headers = await manager_headers()
    response = await client.post(
        "/api/upload/resume",
        files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["url"] == "https://fake-r2.example.com/resumes/fake-file"
    assert body["filename"] == "resume.pdf"
    assert body["mimetype"] == "application/pdf"
    assert body["size"] == len(b"%PDF-1.4 fake")


async def test_upload_logo_rejects_unsupported_type(client):
    headers = await manager_headers()
    response = await client.post(
        "/api/upload/logo",
        files={"file": ("logo.pdf", b"not an image", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 400


async def test_upload_logo_success_sets_the_companys_logo_url(client):
    headers = await manager_headers()
    company_response = await client.put(
        "/api/company", json={"name": "Logo Co", "email": "logo@example.com"}, headers=headers
    )
    assert company_response.status_code == 200

    response = await client.post(
        "/api/upload/logo",
        files={"file": ("logo.png", b"fake png bytes", "image/png")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["url"] == "https://fake-r2.example.com/logos/fake-file"

    company_after = await client.get("/api/company", headers=headers)
    assert company_after.json()["data"]["logoUrl"] == "https://fake-r2.example.com/logos/fake-file"


async def test_public_upload_resume_rejects_non_pdf(client):
    response = await client.post(
        "/public/upload/resume", files={"file": ("resume.png", b"not a pdf", "image/png")}
    )
    assert response.status_code == 400


async def test_public_upload_resume_rejects_files_over_10mb(client):
    oversized = b"%" * (10 * 1024 * 1024 + 1)
    response = await client.post(
        "/public/upload/resume", files={"file": ("resume.pdf", oversized, "application/pdf")}
    )
    assert response.status_code == 400


async def test_public_upload_resume_success_needs_no_auth(client):
    response = await client.post(
        "/public/upload/resume", files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["url"] == "https://fake-r2.example.com/resumes/fake-file"
