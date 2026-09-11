"""Real end-to-end tests of the report module: port of the analytics
computation in report.service.ts. Mostly shape assertions (the TS source's
numeric edge cases - safePct, the 6-bucket date windows, the 5-month offer
trend window - are exercised structurally here, not value-by-value, since
seeding enough historical data to pin exact deltas would mean backdating
rows past what the HTTP API exposes)."""

from __future__ import annotations

import pytest

from tests.integration.helpers import apply_candidate, create_job, manager_headers

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clear_report_cache():
    """The report service's 60s in-memory cache (app/modules/report/service.py,
    `_cache`) is a process-level singleton, matching the TS source's `Map`
    cache exactly - but that means it survives across tests in the same
    pytest run even though `_clean_database` truncates the DB between them.
    Clear it so each test observes the freshly-truncated DB, not a stale
    same-cache-key ("7d|all") result from an earlier test."""
    from app.modules.report.service import _cache

    _cache.clear()
    yield


async def test_analytics_returns_full_shape(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    await apply_candidate(client, job["id"])

    response = await client.get("/api/reports/analytics", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert set(data.keys()) == {
        "summary",
        "pipelineReport",
        "candidateVolume",
        "sourceOfCandidates",
        "timeToHireByDepartment",
        "offerTrends",
    }

    summary = data["summary"]
    assert set(summary.keys()) == {
        "totalCandidates",
        "totalCandidatesDeltaPct",
        "openPositions",
        "openPositionsDelta",
        "avgTimeToHireDays",
        "avgTimeToHireDeltaDays",
        "offerAcceptanceRate",
        "offerAcceptanceRateDeltaPct",
    }
    assert summary["totalCandidates"] >= 1
    assert summary["openPositions"] >= 1

    # 6 date buckets covering the period window.
    assert len(data["candidateVolume"]) == 6
    for bucket in data["candidateVolume"]:
        assert set(bucket.keys()) == {"date", "applications", "hires"}

    # No candidates moved past "Applied" yet -> falls back to the
    # sourceOfCandidates the candidate's current stage produces (not the
    # `[{"name": "Website", "value": 100}]` fallback, since there IS data).
    assert data["sourceOfCandidates"], "expected at least one source row"
    for row in data["sourceOfCandidates"]:
        assert set(row.keys()) == {"name", "value"}

    # 5 months including the current one.
    assert len(data["offerTrends"]) == 5
    for row in data["offerTrends"]:
        assert set(row.keys()) == {"month", "sent", "accepted"}

    for row in data["pipelineReport"]:
        assert set(row.keys()) == {"stage", "current", "previous"}

    for row in data["timeToHireByDepartment"]:
        assert set(row.keys()) == {"dept", "days"}


async def test_analytics_accepts_period_and_department_filter(client):
    headers = await manager_headers()
    job = await create_job(client, headers)

    response = await client.get(
        "/api/reports/analytics",
        params={"period": "30d", "departmentId": job["departmentId"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["summary"]["openPositions"] >= 1


async def test_analytics_rejects_invalid_period(client):
    headers = await manager_headers()
    response = await client.get("/api/reports/analytics", params={"period": "1d"}, headers=headers)
    assert response.status_code == 400


async def test_analytics_no_data_falls_back_to_website_source(client):
    """No candidates/offers seeded at all -> sourceOfCandidates falls back
    to the TS source's `[{"name": "Website", "value": 100}]` sentinel."""
    headers = await manager_headers()
    response = await client.get("/api/reports/analytics", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["sourceOfCandidates"] == [{"name": "Website", "value": 100}]


async def test_export_json_returns_plain_json_body_not_a_file(client):
    """Critically, the TS export endpoint does not stream a file - it's a
    plain `{data: {format, fileName, mimeType, content}}` JSON body."""
    headers = await manager_headers()
    job = await create_job(client, headers)
    await apply_candidate(client, job["id"])

    response = await client.get(
        "/api/reports/analytics/export", params={"format": "json"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert "attachment" not in response.headers.get("content-disposition", "")
    assert response.headers["content-type"].startswith("application/json")

    data = response.json()["data"]
    assert set(data.keys()) == {"format", "fileName", "mimeType", "content"}
    assert data["format"] == "json"
    assert data["fileName"] == "openats-report-7d.json"
    assert data["mimeType"] == "application/json"

    import json

    parsed_content = json.loads(data["content"])
    assert set(parsed_content.keys()) == {
        "summary",
        "pipelineReport",
        "candidateVolume",
        "sourceOfCandidates",
        "timeToHireByDepartment",
        "offerTrends",
    }


async def test_export_csv_returns_plain_json_body_with_csv_string(client):
    headers = await manager_headers()
    job = await create_job(client, headers)
    await apply_candidate(client, job["id"])

    response = await client.get(
        "/api/reports/analytics/export", params={"format": "csv"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert "attachment" not in response.headers.get("content-disposition", "")

    data = response.json()["data"]
    assert set(data.keys()) == {"format", "fileName", "mimeType", "content"}
    assert data["format"] == "csv"
    assert data["fileName"] == "openats-report-7d.csv"
    assert data["mimeType"] == "text/csv"

    content = data["content"]
    assert content.startswith('"=== Summary ==="')
    assert '"=== Pipeline Report ==="' in content
    assert '"=== Candidate Volume ==="' in content
    assert '"=== Source of Candidates ==="' in content
    assert '"=== Time to Hire by Dept ==="' in content
    assert '"=== Offer Trends ==="' in content


async def test_export_requires_manager_role(client):
    from tests.conftest import make_bearer_token

    interviewer_token = await make_bearer_token(email="interviewer@example.com", role="interviewer")
    response = await client.get(
        "/api/reports/analytics/export",
        headers={"Authorization": f"Bearer {interviewer_token}"},
    )
    assert response.status_code == 403
