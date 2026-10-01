"""Create evidence_v1_analyses

Revision ID: 0001
Revises:
Create Date: 2026-09-30

The persisted form of one Evidence Engine v1 product-integration run
(Task 31). Lives in the default/public schema -- no new Postgres schema,
per the explicit architectural decision recorded in
docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md. Independent of,
and never referenced by, the legacy `analyses` table or any V2 (`v2.*`)
table -- no foreign key crosses either boundary.

Design notes:

- `id` is an application-generated UUID4 hex string (TEXT), not a
  sequential integer -- a sequential id would make cross-user analysis
  enumeration trivial (Task 31 item 20's own explicit security check);
  a UUID primary key removes that guess-the-next-id risk without
  requiring the pgcrypto extension (the id is generated in Python, not
  by a server-side DEFAULT).
- Relational columns exist ONLY for what ownership/listing/filtering/
  report-selection genuinely needs (owner_user_id, company_name,
  canonical_website, engine, methodology_version, coverage/confidence/
  publishable, stage, run_status, created_at). The full, rich,
  immutable Evidence Engine result (FullCompanyAnalysis + accepted
  ledger claims) is NOT flattened into further columns -- it lives in
  `result` (JSONB). `telemetry` is a SEPARATE JSONB column (not nested
  inside `result`) so an operational query (token usage, provider call
  counts, routing/semantic-fit outcomes) never has to parse the much
  larger analysis artifact just to read it.
- No UPDATE path exists anywhere in this table's own design -- a row is
  written once, by the adapter, after a completed run, and never
  mutated afterward (the product's own "immutable analysis artifact"
  requirement) -- so, unlike v2.source's own mutability trigger, no
  trigger or updated_at column is needed here at all.
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CREATE_TABLE = """
CREATE TABLE evidence_v1_analyses (
    id                    TEXT        NOT NULL,
    owner_user_id         TEXT        NOT NULL,
    company_name          TEXT        NOT NULL,
    canonical_website     TEXT        NOT NULL,
    engine                TEXT        NOT NULL,
    methodology_version   TEXT        NOT NULL,
    stage                 TEXT,
    run_status            TEXT        NOT NULL,
    company_coverage_pct  DOUBLE PRECISION,
    company_confidence    TEXT,
    company_publishable   BOOLEAN,
    result                JSONB       NOT NULL,
    telemetry             JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_evidence_v1_analyses PRIMARY KEY (id),
    CONSTRAINT ck_evidence_v1_analyses_engine
        CHECK (engine = 'evidence_v1'),
    CONSTRAINT ck_evidence_v1_analyses_run_status
        CHECK (run_status IN ('completed', 'failed')),
    CONSTRAINT ck_evidence_v1_analyses_confidence
        CHECK (company_confidence IS NULL OR company_confidence IN ('Low', 'Medium', 'High'))
);
"""

# owner_user_id + created_at DESC: the "My Analyses" listing's own access
# pattern -- a user's analyses, most recent first. owner_user_id alone
# (implied by the composite index's leading column) also serves the
# ownership-check-by-id-then-owner query the retrieval endpoint runs.
CREATE_OWNER_INDEX = """
CREATE INDEX ix_evidence_v1_analyses_owner_created
    ON evidence_v1_analyses (owner_user_id, created_at DESC);
"""


def upgrade() -> None:
    op.execute(CREATE_TABLE)
    op.execute(CREATE_OWNER_INDEX)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_evidence_v1_analyses_owner_created")
    op.execute("DROP TABLE IF EXISTS evidence_v1_analyses")
