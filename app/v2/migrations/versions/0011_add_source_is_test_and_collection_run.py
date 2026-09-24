"""Add v2.source.is_test and create v2.collection_run

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-23

Increment 18.5 -- scheduled SEC collection & review queue operations.

**v2.source.is_test** (new column, NOT NULL DEFAULT false): marks a Source as synthetic/test evidence rather
than a real one. Defaults false, so every existing row and every ordinarily-registered future row stays real
with zero code change anywhere. The v2.source_guard() trigger function is replaced (CREATE OR REPLACE, same
signature) to treat is_test as mutable, alongside source_name/source_url/is_active -- it was immutable-by-
omission before this migration only because the column did not exist yet, not by any deliberate choice this
migration reverses. The ONLY application code path that ever sets it True is
app.v2.repositories.sources.mark_source_as_test(), gated on a human Authority; there is no rule authority and
no HTTP endpoint for it. Existing rows (including the sources already carrying Increment 18.4's deliberately
tampered "Zztest V2 Review" test candidates) are NOT reclassified by this migration -- see
docs/v2/RUNBOOK_18_5.md's "marking a source as test" procedure for the explicit, separate administrative step.

**v2.collection_run**: an operational record of one bounded collection attempt against the EXISTING, unmodified
collection pipeline (app.v2.tools.sec_form_d_collector + app.v2.tools.cli). Not evidence, not a candidate, not
a canonical fact -- a job-history row. Mutable while status='running' (progress is written as it happens);
frozen (UPDATE and DELETE both refused) once it reaches any terminal status (succeeded/failed/partial/
interrupted), by the same "history is never rewritten" principle used everywhere else in V2. A partial unique
index (job_name) WHERE status='running' is the single-active-run lock this increment's "no overlapping
collection runs" requirement needs -- enforced by Postgres itself, so it holds across process crashes and
concurrent CLI invocations, not just within one Python process's memory.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


ADD_SOURCE_IS_TEST = """
ALTER TABLE v2.source ADD COLUMN is_test BOOLEAN NOT NULL DEFAULT false
"""

REPLACE_SOURCE_GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION v2.source_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.created_at := now();
        NEW.updated_at := NEW.created_at;
        RETURN NEW;
    END IF;

    IF NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION 'v2.source.id is immutable' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.source_key IS DISTINCT FROM OLD.source_key THEN
        RAISE EXCEPTION 'v2.source.source_key is immutable' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.source_type IS DISTINCT FROM OLD.source_type THEN
        RAISE EXCEPTION 'v2.source.source_type is immutable' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.collection_method IS DISTINCT FROM OLD.collection_method THEN
        RAISE EXCEPTION 'v2.source.collection_method is immutable' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'v2.source.created_at is immutable' USING ERRCODE = 'integrity_constraint_violation';
    END IF;

    IF NEW.source_name IS DISTINCT FROM OLD.source_name
       OR NEW.source_url IS DISTINCT FROM OLD.source_url
       OR NEW.is_active IS DISTINCT FROM OLD.is_active
       OR NEW.is_test IS DISTINCT FROM OLD.is_test THEN
        NEW.updated_at := GREATEST(clock_timestamp(), OLD.updated_at);
    ELSE
        NEW.updated_at := OLD.updated_at;  -- a no-op update is not a modification
    END IF;
    RETURN NEW;
END
$$
"""

CREATE_COLLECTION_RUN = r"""
CREATE TABLE v2.collection_run (
    id               BIGINT      GENERATED ALWAYS AS IDENTITY,
    job_name         TEXT        NOT NULL,
    trigger_type     TEXT        NOT NULL,
    triggered_by     TEXT        NOT NULL,
    status           TEXT        NOT NULL,
    query            TEXT        NOT NULL,
    max_filings      INTEGER     NOT NULL,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at     TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ NOT NULL,
    discovered_count INTEGER     NOT NULL DEFAULT 0,
    collected_count  INTEGER     NOT NULL DEFAULT 0,
    duplicate_count  INTEGER     NOT NULL DEFAULT 0,
    failed_count     INTEGER     NOT NULL DEFAULT 0,
    candidate_count  INTEGER     NOT NULL DEFAULT 0,
    failure_detail   TEXT,
    result_detail    TEXT,
    CONSTRAINT pk_collection_run PRIMARY KEY (id),
    CONSTRAINT ck_collection_run_job_name_shape
        CHECK (job_name ~ '^[a-z][a-z0-9_]{1,63}$'),
    CONSTRAINT ck_collection_run_trigger_type_allowed
        CHECK (trigger_type IN ('manual', 'scheduled')),
    CONSTRAINT ck_collection_run_status_allowed
        CHECK (status IN ('running', 'succeeded', 'failed', 'partial', 'interrupted')),
    CONSTRAINT ck_collection_run_triggered_by_shape
        CHECK (triggered_by ~ '^[a-z][a-z0-9_]{0,31}:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
    CONSTRAINT ck_collection_run_query_valid
        CHECK (char_length(query) BETWEEN 1 AND 200 AND query !~ '[\x01-\x1f\x7f]'),
    CONSTRAINT ck_collection_run_max_filings_bounded
        CHECK (max_filings BETWEEN 1 AND 25),
    CONSTRAINT ck_collection_run_counts_nonneg
        CHECK (discovered_count >= 0 AND collected_count >= 0 AND duplicate_count >= 0
               AND failed_count >= 0 AND candidate_count >= 0),
    CONSTRAINT ck_collection_run_completed_iff_terminal
        CHECK ((status IN ('succeeded', 'failed', 'partial', 'interrupted')) = (completed_at IS NOT NULL)),
    CONSTRAINT ck_collection_run_completed_not_before_started
        CHECK (completed_at IS NULL OR completed_at >= started_at),
    CONSTRAINT ck_collection_run_failure_detail_len
        CHECK (failure_detail IS NULL OR char_length(failure_detail) <= 4000),
    CONSTRAINT ck_collection_run_result_detail_len
        CHECK (result_detail IS NULL OR char_length(result_detail) <= 20000)
)
"""

CREATE_INDEXES = (
    "CREATE UNIQUE INDEX uq_collection_run_one_active_per_job "
    "ON v2.collection_run (job_name) WHERE status = 'running'",
    # Plain ascending (matches app.v2.db.tables' Index declarations exactly, for Alembic's autogenerate-diff
    # check): Postgres scans a plain btree index backwards just as efficiently for an ORDER BY ... DESC query,
    # so there is no correctness or performance reason to declare it DESC here.
    "CREATE INDEX ix_collection_run_started_at ON v2.collection_run (started_at)",
    "CREATE INDEX ix_collection_run_job_name_started_at ON v2.collection_run (job_name, started_at)",
)

CREATE_COLLECTION_RUN_GUARD_FUNCTION = """
CREATE FUNCTION v2.collection_run_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'v2.collection_run is append-only: DELETE is not permitted' USING ERRCODE = 'integrity_constraint_violation';
    END IF;

    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    -- TG_OP = 'UPDATE'
    IF OLD.status IN ('succeeded', 'failed', 'partial', 'interrupted') THEN
        RAISE EXCEPTION 'v2.collection_run is immutable once it reaches a terminal status' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.job_name IS DISTINCT FROM OLD.job_name
       OR NEW.trigger_type IS DISTINCT FROM OLD.trigger_type
       OR NEW.triggered_by IS DISTINCT FROM OLD.triggered_by
       OR NEW.query IS DISTINCT FROM OLD.query
       OR NEW.max_filings IS DISTINCT FROM OLD.max_filings
       OR NEW.started_at IS DISTINCT FROM OLD.started_at THEN
        RAISE EXCEPTION 'v2.collection_run identity/configuration fields are immutable' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END
$$
"""

CREATE_TRIGGERS = (
    """
    CREATE TRIGGER trg_collection_run_guard
        BEFORE INSERT OR UPDATE ON v2.collection_run
        FOR EACH ROW EXECUTE FUNCTION v2.collection_run_guard()
    """,
    """
    CREATE TRIGGER trg_collection_run_no_delete
        BEFORE DELETE ON v2.collection_run
        FOR EACH ROW EXECUTE FUNCTION v2.collection_run_guard()
    """,
)

COMMENTS = (
    "COMMENT ON COLUMN v2.source.is_test IS "
    "'Synthetic/test evidence marker. Defaults false. Set ONLY by app.v2.repositories.sources.mark_source_as_test "
    "under an explicit human Authority -- never inferred, never reachable from the review API.'",
    "COMMENT ON TABLE v2.collection_run IS "
    "'Operational job history for one bounded collection attempt (Increment 18.5). Not evidence, not a candidate, "
    "not a canonical fact. Mutable while running; frozen once terminal.'",
)

REFUSE_IF_HISTORY_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.collection_run) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0011: collection_run history exists',
            HINT = 'Collection job history is never discarded by a migration. Back it up and drop the table by hand if you truly mean to.',
            ERRCODE = 'restrict_violation';
    END IF;
END
$$
"""

REFUSE_IF_TEST_SOURCES_EXIST = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.source WHERE is_test) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0011: a source is marked is_test=true',
            HINT = 'Dropping this column would silently discard that classification. Unmark it by hand first if you truly mean to downgrade.',
            ERRCODE = 'restrict_violation';
    END IF;
END
$$
"""


def upgrade() -> None:
    op.execute(sa.text(ADD_SOURCE_IS_TEST))
    op.execute(sa.text(REPLACE_SOURCE_GUARD_FUNCTION))
    op.execute(sa.text(CREATE_COLLECTION_RUN))
    for statement in CREATE_INDEXES:
        op.execute(sa.text(statement))
    op.execute(sa.text(CREATE_COLLECTION_RUN_GUARD_FUNCTION))
    for statement in CREATE_TRIGGERS:
        op.execute(sa.text(statement))
    for statement in COMMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_HISTORY_EXISTS))
    op.execute(sa.text(REFUSE_IF_TEST_SOURCES_EXIST))
    op.execute(sa.text("DROP TABLE v2.collection_run"))
    op.execute(sa.text("DROP FUNCTION v2.collection_run_guard()"))
    op.execute(sa.text("ALTER TABLE v2.source DROP COLUMN is_test"))
    # Restore the pre-0011 source_guard() function (without is_test in the mutability check).
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION v2.source_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                NEW.created_at := now();
                NEW.updated_at := NEW.created_at;
                RETURN NEW;
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id THEN
                RAISE EXCEPTION 'v2.source.id is immutable' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.source_key IS DISTINCT FROM OLD.source_key THEN
                RAISE EXCEPTION 'v2.source.source_key is immutable' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.source_type IS DISTINCT FROM OLD.source_type THEN
                RAISE EXCEPTION 'v2.source.source_type is immutable' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.collection_method IS DISTINCT FROM OLD.collection_method THEN
                RAISE EXCEPTION 'v2.source.collection_method is immutable' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'v2.source.created_at is immutable' USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.source_name IS DISTINCT FROM OLD.source_name
               OR NEW.source_url IS DISTINCT FROM OLD.source_url
               OR NEW.is_active IS DISTINCT FROM OLD.is_active THEN
                NEW.updated_at := GREATEST(clock_timestamp(), OLD.updated_at);
            ELSE
                NEW.updated_at := OLD.updated_at;
            END IF;
            RETURN NEW;
        END
        $$
    """))
