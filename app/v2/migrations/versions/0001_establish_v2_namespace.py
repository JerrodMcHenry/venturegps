"""Establish the V2 namespace

Revision ID: 0001
Revises:
Create Date: 2026-09-21

Marks schema `v2` as owned by V2 migrations. The schema itself already exists
by the time this runs: Alembic must create its version table (v2.alembic_version)
before executing any revision, so app/v2/migrations/env.py bootstraps
`CREATE SCHEMA IF NOT EXISTS v2`. The statement below is idempotent and keeps
this history self-describing; the schema comment is the revision's real,
reversible change.

No tables are created here. Each later table arrives with the increment that
implements it.

Downgrade removes only what this revision added (the comment). Removing the
now-empty schema and version table when history is fully reverted is env.py's
job (see its module docstring).
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS v2")
    op.execute(
        "COMMENT ON SCHEMA v2 IS "
        "'VentureGPS V2 truth foundation. Managed exclusively by V2 Alembic migrations "
        "(app/v2/migrations). Legacy tables live in public and are never managed here.'"
    )


def downgrade() -> None:
    op.execute("COMMENT ON SCHEMA v2 IS NULL")
