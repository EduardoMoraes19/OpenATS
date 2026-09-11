"""Real end-to-end test of the pipeline module's reorder endpoint - ported
from pipeline.service.ts's reorder(), which takes explicit {id, position}
pairs (not a bare ordered list of ids) and returns only the stages it
touched, in the order given, using a two-phase negative-position update to
dodge the (job_id, position) unique constraint.
"""

from __future__ import annotations

import pytest

from tests.integration.helpers import create_job, get_pipeline_stages, manager_headers

pytestmark = pytest.mark.asyncio


async def test_reorder_swaps_two_stages_by_explicit_id_position_pairs(client, rsa_keypair):
    headers = await manager_headers(rsa_keypair)
    job = await create_job(client, headers)
    stages = await get_pipeline_stages(client, headers, job["id"])
    assert len(stages) >= 2, f"seeded pipeline too short to test a swap: {stages}"

    first, second = stages[0], stages[1]

    response = await client.post(
        f"/api/jobs/{job['id']}/pipeline/reorder",
        json={
            "stages": [
                {"id": first["id"], "position": second["position"]},
                {"id": second["id"], "position": first["position"]},
            ]
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    reordered = response.json()["data"]

    # Only the two swapped stages come back, in the order they were passed -
    # not the full pipeline re-fetched.
    assert len(reordered) == 2
    assert reordered[0]["id"] == first["id"]
    assert reordered[0]["position"] == second["position"]
    assert reordered[1]["id"] == second["id"]
    assert reordered[1]["position"] == first["position"]

    all_stages = await get_pipeline_stages(client, headers, job["id"])
    positions_by_id = {s["id"]: s["position"] for s in all_stages}
    assert positions_by_id[first["id"]] == second["position"]
    assert positions_by_id[second["id"]] == first["position"]
