"""seed: default pipeline stage templates

Bakes the 7 default pipeline stage templates into the migration chain
instead of leaving them to the separate `make seed` step
(app/db/seed.py) - a fresh `alembic upgrade head` now leaves the app in
a state where job creation works immediately, since job/service.py
clones these templates into job_pipeline_stages on every new job.
app/db/seed.py is unchanged and still safe to run (it deletes and
re-inserts the same rows), for resetting templates back to default on
an existing database.

Revision ID: 0003_seed_pipeline_stages
Revises: 0002_local_auth
Create Date: 2026-09-12 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_seed_pipeline_stages"
down_revision: str | None = "0002_local_auth"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STAGE_TEMPLATES = [
    ("Screening", 1, "screening", False),
    ("Screening Qualified", 2, "screening", False),
    ("Screening Disqualified", 3, "screening", False),
    ("Interviews", 4, "interview", False),
    ("Shortlisted", 5, "interview", False),
    ("Offer", 6, "offer", False),
    ("Hired", 7, "offer", False),
]


def upgrade() -> None:
    for name, position, stage_type, is_deletable in _STAGE_TEMPLATES:
        op.execute(
            sa.text(
                """
                INSERT INTO "pipeline_stage_templates" ("name", "position", "stage_type", "is_deletable")
                VALUES (:name, :position, CAST(:stage_type AS stage_type), :is_deletable)
                ON CONFLICT ("name") DO NOTHING
                """
            ).bindparams(name=name, position=position, stage_type=stage_type, is_deletable=is_deletable)
        )


def downgrade() -> None:
    names = [row[0] for row in _STAGE_TEMPLATES]
    op.execute(
        sa.text('DELETE FROM "pipeline_stage_templates" WHERE "name" IN :names').bindparams(
            sa.bindparam("names", value=names, expanding=True)
        )
    )
