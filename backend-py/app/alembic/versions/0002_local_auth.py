"""local auth: replace Asgardeo identity columns with password + role

The original app delegated authentication entirely to Asgardeo (WSO2) - no
password was ever stored, and role was derived from the JWT on every
request, never persisted. This migration moves `users` to self-hosted JWT
auth (bcrypt password hash, a real `role` column, `token_version` for
session invalidation), modeled on labs-contaja's admin-auth pattern.

Revision ID: 0002_local_auth
Revises: 0001_baseline
Create Date: 2026-09-11 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_local_auth"
down_revision: str | None = "0001_baseline"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("CREATE TYPE \"app_role\" AS ENUM('super_admin', 'hiring_manager', 'interviewer')"))
    op.execute(sa.text('ALTER TABLE "users" DROP CONSTRAINT "users_asgardeo_user_id_unique"'))
    op.execute(sa.text('ALTER TABLE "users" DROP COLUMN "asgardeo_user_id"'))
    op.execute(sa.text('ALTER TABLE "users" ADD COLUMN "password_hash" varchar(255) NOT NULL DEFAULT \'\''))
    op.execute(sa.text('ALTER TABLE "users" ALTER COLUMN "password_hash" DROP DEFAULT'))
    op.execute(
        sa.text('ALTER TABLE "users" ADD COLUMN "role" "app_role" NOT NULL DEFAULT \'interviewer\'')
    )
    op.execute(sa.text('ALTER TABLE "users" ALTER COLUMN "role" DROP DEFAULT'))
    op.execute(sa.text('ALTER TABLE "users" ADD COLUMN "token_version" integer NOT NULL DEFAULT 0'))


def downgrade() -> None:
    op.execute(sa.text('ALTER TABLE "users" DROP COLUMN "token_version"'))
    op.execute(sa.text('ALTER TABLE "users" DROP COLUMN "role"'))
    op.execute(sa.text('ALTER TABLE "users" DROP COLUMN "password_hash"'))
    op.execute(
        sa.text('ALTER TABLE "users" ADD COLUMN "asgardeo_user_id" varchar(255) NOT NULL DEFAULT \'\'')
    )
    op.execute(sa.text('ALTER TABLE "users" ALTER COLUMN "asgardeo_user_id" DROP DEFAULT'))
    op.execute(
        sa.text('ALTER TABLE "users" ADD CONSTRAINT "users_asgardeo_user_id_unique" UNIQUE("asgardeo_user_id")')
    )
    op.execute(sa.text('DROP TYPE "app_role"'))
