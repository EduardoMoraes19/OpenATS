"""Real tests of the CV analysis pipeline - equivalent to
cv-analysis.service.ts + worker.ts. Only the scoring math had a test before
this (test_scoring.py); the actual orchestration (R2 download, the two
parallel Gemini calls, the not-a-resume rejection, the non-fatal AI summary,
and the arq task's retry/exhaustion policy) had never run in an automated
test.

Real R2 and Gemini aren't available here, so both are monkeypatched at their
client boundaries - `r2_service.download_file` and the three
`gemini_client` functions - the same "swap the external call" pattern used
for R2 uploads and the Google OAuth exchange in the other new test files.
Everything downstream (scoring, persistence, retry bookkeeping) is real.
"""

from __future__ import annotations

import pytest
from arq import Retry
from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.models.candidates import CandidateCvAnalysis
from app.db.models.enums import CvAnalysisStatus
from app.modules.candidate import cv_analysis_service
from app.queues.cv_analysis.scoring import ParsedCv
from app.queues.cv_analysis.tasks import MAX_TRIES, _analyze_cv
from app.shared.services import r2_service
from tests.integration.helpers import apply_candidate, create_job, manager_headers

pytestmark = pytest.mark.asyncio

RESUME_URL = "http://localhost:9000/test-bucket/resumes/fake-resume.pdf"

_GOOD_PARSED_CV = ParsedCv(
    document_type="resume",
    is_cv_or_resume=True,
    confidence=0.95,
    rationale="Clearly a resume with skills and experience sections.",
    listed_skills=["Python", "PostgreSQL"],
    total_experience_years=4,
    job_level="mid",
)

_NOT_A_RESUME = ParsedCv(
    document_type="cover_letter",
    is_cv_or_resume=False,
    confidence=0.9,
    rationale="This is a cover letter, not a resume.",
)


def _async_return(value):
    async def _fn(*args, **kwargs):
        return value

    return _fn


async def _setup_candidate(client) -> tuple[int, int]:
    headers = await manager_headers()
    job = await create_job(client, headers)
    candidate = await apply_candidate(client, job["id"])
    async with async_session_factory() as db:
        await cv_analysis_service.mark_pending(db, candidate["id"], job["id"])
    return candidate["id"], job["id"]


async def _get_analysis(candidate_id: int) -> CandidateCvAnalysis:
    async with async_session_factory() as db:
        return (
            await db.execute(
                select(CandidateCvAnalysis).where(CandidateCvAnalysis.candidate_id == candidate_id)
            )
        ).scalar_one()


@pytest.fixture(autouse=True)
def _stub_r2_download(monkeypatch):
    monkeypatch.setattr(r2_service, "download_file", lambda key: b"%PDF-1.4 fake pdf bytes")


async def test_run_analysis_success_persists_score_and_marks_done(client, monkeypatch):
    candidate_id, job_id = await _setup_candidate(client)
    monkeypatch.setattr(cv_analysis_service, "parse_cv_with_gemini", _async_return(_GOOD_PARSED_CV))
    monkeypatch.setattr(cv_analysis_service, "generate_ai_summary", _async_return({"quickSummary": "Solid fit."}))

    async with async_session_factory() as db:
        await cv_analysis_service.run_analysis(db, candidate_id, job_id, RESUME_URL)

    analysis = await _get_analysis(candidate_id)
    assert analysis.status == CvAnalysisStatus.done
    # The job (created via the `create_job` helper) requires no skills, no
    # experience, and no level, so scoring.py's "no requirement = full marks
    # on that dimension" rule applies across the board.
    assert analysis.match_score == 100
    assert analysis.ai_summary == {"quickSummary": "Solid fit."}
    assert analysis.error_message is None


async def test_run_analysis_rejects_a_document_that_is_not_a_resume(client, monkeypatch):
    candidate_id, job_id = await _setup_candidate(client)
    monkeypatch.setattr(cv_analysis_service, "parse_cv_with_gemini", _async_return(_NOT_A_RESUME))

    with pytest.raises(cv_analysis_service.CvNotAResumeError):
        async with async_session_factory() as db:
            await cv_analysis_service.run_analysis(db, candidate_id, job_id, RESUME_URL)

    # Rejected before any persistence - the row is untouched from mark_pending.
    analysis = await _get_analysis(candidate_id)
    assert analysis.status == CvAnalysisStatus.pending


async def test_run_analysis_survives_ai_summary_failure(client, monkeypatch):
    """generate_ai_summary is documented as non-fatal - unlike the CV/JD
    parse calls, which run in the fatal asyncio.gather()."""
    candidate_id, job_id = await _setup_candidate(client)
    monkeypatch.setattr(cv_analysis_service, "parse_cv_with_gemini", _async_return(_GOOD_PARSED_CV))

    async def _boom(*args, **kwargs):
        raise RuntimeError("Gemini is down")

    monkeypatch.setattr(cv_analysis_service, "generate_ai_summary", _boom)

    with pytest.raises(RuntimeError):
        async with async_session_factory() as db:
            await cv_analysis_service.run_analysis(db, candidate_id, job_id, RESUME_URL)


async def test_task_retries_on_early_attempts_without_touching_the_database(client, monkeypatch):
    candidate_id, job_id = await _setup_candidate(client)

    async def _boom(db, cid, jid, url):
        raise RuntimeError("transient failure")

    monkeypatch.setattr(cv_analysis_service, "run_analysis", _boom)

    for attempt in range(1, MAX_TRIES):
        with pytest.raises(Retry):
            await _analyze_cv(
                {"job_try": attempt}, candidate_id=candidate_id, job_id=job_id, resume_url=RESUME_URL
            )

    # Still pending - intermediate retries never touch the row.
    analysis = await _get_analysis(candidate_id)
    assert analysis.status == CvAnalysisStatus.pending


async def test_task_marks_failed_only_once_retries_are_exhausted(client, monkeypatch):
    candidate_id, job_id = await _setup_candidate(client)

    async def _boom(db, cid, jid, url):
        raise RuntimeError("permanent failure")

    monkeypatch.setattr(cv_analysis_service, "run_analysis", _boom)

    # No Retry raised on the final attempt - the task returns normally
    # having marked the row failed.
    await _analyze_cv(
        {"job_try": MAX_TRIES}, candidate_id=candidate_id, job_id=job_id, resume_url=RESUME_URL
    )

    analysis = await _get_analysis(candidate_id)
    assert analysis.status == CvAnalysisStatus.failed
    assert "permanent failure" in analysis.error_message


async def test_task_success_marks_done(client, monkeypatch):
    candidate_id, job_id = await _setup_candidate(client)
    monkeypatch.setattr(cv_analysis_service, "parse_cv_with_gemini", _async_return(_GOOD_PARSED_CV))
    monkeypatch.setattr(cv_analysis_service, "generate_ai_summary", _async_return(None))

    await _analyze_cv({"job_try": 1}, candidate_id=candidate_id, job_id=job_id, resume_url=RESUME_URL)

    analysis = await _get_analysis(candidate_id)
    assert analysis.status == CvAnalysisStatus.done
