"""Create v2.processing_attempt

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-21

Durable operational history: "VentureGPS attempted to process this immutable
Observation using this versioned processor". It is NOT evidence, canonical
truth, an Observation status, an AI result or a candidate. Observations never
change; the absence of any attempt IS "collected, not yet processed".

Identity: (observation_id, processor_id, attempt_number). Attempt numbers are
linear per observation + processor_id regardless of processor_version, so a
v1 failure, a v1 success and a later v2 reprocessing form one history.

Two constraints are the final authority under concurrency (the repository also
serialises starts by locking the Observation row, which is a lock, not a write):
  uq_processing_attempt_number      UNIQUE (observation_id, processor_id, attempt_number)
  uq_processing_attempt_one_active  UNIQUE (observation_id, processor_id) WHERE status = 'processing'

Lifecycle (one trigger, specific to this table):
  INSERT   must be 'processing'; started_at is the database's clock.
  UPDATE   identity (id, observation_id, processor_id, processor_version,
           attempt_number, started_at) never changes. A terminal row is
           immutable. A processing row may renew its lease (never backwards)
           or make ONE transition to a terminal state, at which point
           finished_at is the database's clock.
  DELETE / TRUNCATE  rejected: history is never removed.
CHECK constraints fix the legal combinations of status, finished_at, lease and
failure metadata. Failure metadata is bounded machine codes only: never
payload excerpts, exception text, prompts or AI output.

Downgrade removes only this table and its function, and REFUSES to run while
any attempt exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

CREATE_TABLE = """
CREATE TABLE v2.processing_attempt (
    id                BIGINT GENERATED ALWAYS AS IDENTITY,
    observation_id    BIGINT      NOT NULL,
    processor_id      TEXT        NOT NULL,
    processor_version TEXT        NOT NULL,
    attempt_number    INTEGER     NOT NULL,
    status            TEXT        NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at       TIMESTAMPTZ,
    lease_expires_at  TIMESTAMPTZ,
    reason_code       TEXT,
    detail_code       TEXT,
    CONSTRAINT pk_processing_attempt PRIMARY KEY (id),
    CONSTRAINT fk_processing_attempt_observation_id_observation
        FOREIGN KEY (observation_id) REFERENCES v2.observation (id) ON DELETE RESTRICT,
    CONSTRAINT uq_processing_attempt_number UNIQUE (observation_id, processor_id, attempt_number),
    CONSTRAINT ck_processing_attempt_processor_id_shape
        CHECK (processor_id ~ '^[a-z][a-z0-9_]{1,63}$'),
    CONSTRAINT ck_processing_attempt_processor_version_shape
        CHECK (processor_version ~ '^[a-z][a-z0-9_]{0,63}\\.v[1-9][0-9]{0,5}$'
               AND split_part(processor_version, '.v', 1) = processor_id),
    CONSTRAINT ck_processing_attempt_attempt_number_positive
        CHECK (attempt_number >= 1),
    CONSTRAINT ck_processing_attempt_status_allowed
        CHECK (status IN ('processing', 'processed', 'failed', 'quarantined')),
    CONSTRAINT ck_processing_attempt_reason_code_shape
        CHECK (reason_code IS NULL OR reason_code ~ '^[a-z][a-z0-9_]{1,63}$'),
    CONSTRAINT ck_processing_attempt_detail_code_shape
        CHECK (detail_code IS NULL OR detail_code ~ '^[a-z][a-z0-9_]{1,63}$'),
    CONSTRAINT ck_processing_attempt_state_shape
        CHECK (CASE status
                 WHEN 'processing'  THEN finished_at IS NULL AND lease_expires_at IS NOT NULL
                                         AND reason_code IS NULL AND detail_code IS NULL
                 WHEN 'processed'   THEN finished_at IS NOT NULL AND lease_expires_at IS NULL
                                         AND reason_code IS NULL AND detail_code IS NULL
                 WHEN 'failed'      THEN finished_at IS NOT NULL AND lease_expires_at IS NULL
                                         AND reason_code IS NOT NULL
                 WHEN 'quarantined' THEN finished_at IS NOT NULL AND lease_expires_at IS NULL
                                         AND reason_code IS NOT NULL
                 ELSE false END),
    CONSTRAINT ck_processing_attempt_finished_not_before_started
        CHECK (finished_at IS NULL OR finished_at >= started_at)
)
"""

CREATE_ACTIVE_INDEX = """
CREATE UNIQUE INDEX uq_processing_attempt_one_active
    ON v2.processing_attempt (observation_id, processor_id)
    WHERE status = 'processing'
"""

CREATE_GUARD_FUNCTION = """
CREATE FUNCTION v2.processing_attempt_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'processing' THEN
            RAISE EXCEPTION USING MESSAGE = 'v2.processing_attempt: an attempt must start in processing',
                ERRCODE = 'integrity_constraint_violation';
        END IF;
        NEW.started_at := clock_timestamp();   -- the database's clock, whatever the writer supplied
        RETURN NEW;
    END IF;

    IF NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.processing_attempt.id is immutable', ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.observation_id IS DISTINCT FROM OLD.observation_id THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.processing_attempt.observation_id is immutable', ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.processor_id IS DISTINCT FROM OLD.processor_id THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.processing_attempt.processor_id is immutable', ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.processor_version IS DISTINCT FROM OLD.processor_version THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.processing_attempt.processor_version is immutable', ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.attempt_number IS DISTINCT FROM OLD.attempt_number THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.processing_attempt.attempt_number is immutable', ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.started_at IS DISTINCT FROM OLD.started_at THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.processing_attempt.started_at is immutable', ERRCODE = 'integrity_constraint_violation';
    END IF;

    IF OLD.status <> 'processing' THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.processing_attempt: a terminal attempt is immutable',
            ERRCODE = 'integrity_constraint_violation';
    END IF;

    IF NEW.status = 'processing' THEN
        -- lease renewal: forward only
        IF NEW.lease_expires_at < OLD.lease_expires_at THEN
            RAISE EXCEPTION USING MESSAGE = 'v2.processing_attempt.lease_expires_at cannot move backwards',
                ERRCODE = 'integrity_constraint_violation';
        END IF;
    ELSE
        NEW.finished_at := clock_timestamp();  -- the single transition to a terminal state
    END IF;
    RETURN NEW;
END
$$
"""

CREATE_TRIGGERS = """
CREATE TRIGGER trg_processing_attempt_guard
    BEFORE INSERT OR UPDATE ON v2.processing_attempt
    FOR EACH ROW EXECUTE FUNCTION v2.processing_attempt_guard();
CREATE TRIGGER trg_processing_attempt_no_delete
    BEFORE DELETE ON v2.processing_attempt
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_processing_attempt_no_truncate
    BEFORE TRUNCATE ON v2.processing_attempt
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change()
"""

REFUSE_IF_HISTORY_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.processing_attempt) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0005: v2.processing_attempt contains processing history',
            HINT = 'Processing history is never discarded by a migration. Back it up and drop the table by hand if you truly mean to.',
            ERRCODE = 'restrict_violation';
    END IF;
END
$$
"""


def _execute_each(script: str) -> None:
    for statement in script.split(";\n"):
        if statement.strip():
            op.execute(sa.text(statement))


def upgrade() -> None:
    op.execute(sa.text(CREATE_TABLE))
    op.execute(sa.text(CREATE_ACTIVE_INDEX))
    op.execute(sa.text(CREATE_GUARD_FUNCTION))
    _execute_each(CREATE_TRIGGERS)


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_HISTORY_EXISTS))
    op.execute("DROP TABLE v2.processing_attempt")  # drops its indexes and triggers
    op.execute("DROP FUNCTION v2.processing_attempt_guard()")
