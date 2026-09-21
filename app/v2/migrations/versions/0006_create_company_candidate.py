"""Create v2.company_candidate and v2.company_candidate_identifier

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-21

The Candidate layer: UNTRUSTED PROPOSALS that some evidence may describe a
company. Not canonical truth, not a Company, not a claim. Nothing here can be
promoted; no canonical, resolution or claim table exists.

Shape. A candidate belongs to exactly one ProcessingAttempt (which already
identifies the Observation, processor, version and attempt number; none of that
is duplicated here). Identity is (processing_attempt_id, candidate_ordinal):
the ordinal is the position in the proposer's output, so a replay of the same
persistence command cannot duplicate a candidate, and a name is never identity.
Each proposed value (the name, and each identifier) carries ONE evidence
locator: a half-open byte range of the exact RawPayload bytes plus the sha256
of those bytes. Evidence lives on the row it supports (no separate evidence
table), so a proposed value cannot exist without its locator.

Database protections (the domain and repository verify first; these are the
backstop for every writer, including direct SQL):
  - INSERT trigger: the attempt must be PROCESSING (row-locked FOR SHARE, so a
    concurrent transition cannot slip in), and the evidence span must lie inside
    the observation's stored payload and hash to the stored evidence_hash
    (substring/sha256 over the exact bytes).
  - created_at is the database's clock, whatever the writer supplied.
  - UPDATE, DELETE and TRUNCATE are rejected on both tables (reusing the
    table-agnostic v2.forbid_evidence_change()).
  - FKs are ON DELETE RESTRICT.

Downgrade removes only these objects and REFUSES to run while any candidate exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

CREATE_CANDIDATE = r"""
CREATE TABLE v2.company_candidate (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY,
    processing_attempt_id BIGINT      NOT NULL,
    candidate_ordinal     INTEGER     NOT NULL,
    proposed_name         TEXT        NOT NULL,
    name_evidence_start   INTEGER     NOT NULL,
    name_evidence_end     INTEGER     NOT NULL,
    name_evidence_hash    TEXT        NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_company_candidate PRIMARY KEY (id),
    CONSTRAINT fk_company_candidate_processing_attempt_id_processing_attempt
        FOREIGN KEY (processing_attempt_id) REFERENCES v2.processing_attempt (id) ON DELETE RESTRICT,
    CONSTRAINT uq_company_candidate_ordinal UNIQUE (processing_attempt_id, candidate_ordinal),
    CONSTRAINT ck_company_candidate_ordinal_range CHECK (candidate_ordinal BETWEEN 1 AND 1000),
    CONSTRAINT ck_company_candidate_proposed_name_valid
        CHECK (proposed_name = btrim(proposed_name)
               AND char_length(proposed_name) BETWEEN 1 AND 300
               AND proposed_name !~ '[\x01-\x1f\x7f]'),
    CONSTRAINT ck_company_candidate_name_evidence_span
        CHECK (name_evidence_start >= 0 AND name_evidence_end > name_evidence_start
               AND name_evidence_end - name_evidence_start <= 4096),
    CONSTRAINT ck_company_candidate_name_evidence_hash_shape
        CHECK (name_evidence_hash ~ '^[0-9a-f]{64}$')
)
"""

CREATE_IDENTIFIER = r"""
CREATE TABLE v2.company_candidate_identifier (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY,
    candidate_id        BIGINT  NOT NULL,
    identifier_ordinal  INTEGER NOT NULL,
    identifier_type     TEXT    NOT NULL,
    identifier_value    TEXT    NOT NULL,
    evidence_start      INTEGER NOT NULL,
    evidence_end        INTEGER NOT NULL,
    evidence_hash       TEXT    NOT NULL,
    CONSTRAINT pk_company_candidate_identifier PRIMARY KEY (id),
    CONSTRAINT fk_company_candidate_identifier_candidate_id_company_candidate
        FOREIGN KEY (candidate_id) REFERENCES v2.company_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_company_candidate_identifier_ordinal UNIQUE (candidate_id, identifier_ordinal),
    CONSTRAINT uq_company_candidate_identifier_value UNIQUE (candidate_id, identifier_type, identifier_value),
    CONSTRAINT ck_company_candidate_identifier_ordinal_range CHECK (identifier_ordinal BETWEEN 1 AND 100),
    CONSTRAINT ck_company_candidate_identifier_type_allowed CHECK (identifier_type IN ('domain', 'website_url')),
    CONSTRAINT ck_company_candidate_identifier_value_valid
        CHECK (CASE identifier_type
                 WHEN 'domain' THEN char_length(identifier_value) <= 253
                      AND identifier_value ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$'
                 WHEN 'website_url' THEN char_length(identifier_value) <= 2048
                      AND identifier_value ~ '^[\x21-\x5b\x5d-\x7e]+$'
                      AND identifier_value ~* '^https?://[^/?#]'
                      AND identifier_value !~* '^https?://[^/?#]*@'
                 ELSE false END),
    CONSTRAINT ck_company_candidate_identifier_evidence_span
        CHECK (evidence_start >= 0 AND evidence_end > evidence_start AND evidence_end - evidence_start <= 4096),
    CONSTRAINT ck_company_candidate_identifier_evidence_hash_shape
        CHECK (evidence_hash ~ '^[0-9a-f]{64}$')
)
"""

CREATE_CANDIDATE_GUARD = r"""
CREATE FUNCTION v2.company_candidate_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    attempt_status TEXT;
    stored_hash    TEXT;
    stored_bytes   BYTEA;
BEGIN
    SELECT a.status, o.content_hash INTO attempt_status, stored_hash
      FROM v2.processing_attempt a JOIN v2.observation o ON o.id = a.observation_id
     WHERE a.id = NEW.processing_attempt_id
       FOR SHARE OF a;
    IF NOT FOUND THEN
        RETURN NEW;   -- the foreign key reports the missing attempt
    END IF;
    IF attempt_status <> 'processing' THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company_candidate: candidates can only be added while the attempt is processing',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.name_evidence_start < 0 OR NEW.name_evidence_end <= NEW.name_evidence_start THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company_candidate: name evidence span is malformed',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT payload_bytes INTO stored_bytes FROM v2.raw_payload WHERE content_hash = stored_hash;
    IF stored_bytes IS NULL
       OR NEW.name_evidence_end > octet_length(stored_bytes)
       OR encode(sha256(substring(stored_bytes FROM NEW.name_evidence_start + 1
                                  FOR NEW.name_evidence_end - NEW.name_evidence_start)), 'hex') <> NEW.name_evidence_hash THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company_candidate: name evidence does not match the stored payload bytes',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    NEW.created_at := clock_timestamp();   -- the database's clock, whatever the writer supplied
    RETURN NEW;
END
$$
"""

CREATE_IDENTIFIER_GUARD = r"""
CREATE FUNCTION v2.company_candidate_identifier_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    attempt_status TEXT;
    stored_hash    TEXT;
    stored_bytes   BYTEA;
BEGIN
    SELECT a.status, o.content_hash INTO attempt_status, stored_hash
      FROM v2.company_candidate c
      JOIN v2.processing_attempt a ON a.id = c.processing_attempt_id
      JOIN v2.observation o ON o.id = a.observation_id
     WHERE c.id = NEW.candidate_id
       FOR SHARE OF a;
    IF NOT FOUND THEN
        RETURN NEW;   -- the foreign key reports the missing candidate
    END IF;
    IF attempt_status <> 'processing' THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company_candidate_identifier: identifiers can only be added while the attempt is processing',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.evidence_start < 0 OR NEW.evidence_end <= NEW.evidence_start THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company_candidate_identifier: evidence span is malformed',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT payload_bytes INTO stored_bytes FROM v2.raw_payload WHERE content_hash = stored_hash;
    IF stored_bytes IS NULL
       OR NEW.evidence_end > octet_length(stored_bytes)
       OR encode(sha256(substring(stored_bytes FROM NEW.evidence_start + 1
                                  FOR NEW.evidence_end - NEW.evidence_start)), 'hex') <> NEW.evidence_hash THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company_candidate_identifier: evidence does not match the stored payload bytes',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END
$$
"""

CREATE_TRIGGERS = """
CREATE TRIGGER trg_company_candidate_guard
    BEFORE INSERT ON v2.company_candidate
    FOR EACH ROW EXECUTE FUNCTION v2.company_candidate_guard();
CREATE TRIGGER trg_company_candidate_append_only
    BEFORE UPDATE OR DELETE ON v2.company_candidate
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_company_candidate_no_truncate
    BEFORE TRUNCATE ON v2.company_candidate
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_company_candidate_identifier_guard
    BEFORE INSERT ON v2.company_candidate_identifier
    FOR EACH ROW EXECUTE FUNCTION v2.company_candidate_identifier_guard();
CREATE TRIGGER trg_company_candidate_identifier_append_only
    BEFORE UPDATE OR DELETE ON v2.company_candidate_identifier
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_company_candidate_identifier_no_truncate
    BEFORE TRUNCATE ON v2.company_candidate_identifier
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change()
"""

COMMENTS = """
COMMENT ON TABLE v2.company_candidate IS
    'UNTRUSTED PROPOSALS that evidence may describe a company. Not canonical truth: nothing here is a Company, claim or accepted identity.';
COMMENT ON TABLE v2.company_candidate_identifier IS
    'UNTRUSTED proposed identifiers of a company candidate. Not canonical identifiers.'
"""

REFUSE_IF_CANDIDATES_EXIST = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.company_candidate) OR EXISTS (SELECT 1 FROM v2.company_candidate_identifier) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0006: v2.company_candidate contains candidate history',
            HINT = 'Candidate history is never discarded by a migration. Back it up and drop the tables by hand if you truly mean to.',
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
    op.execute(sa.text(CREATE_CANDIDATE))
    op.execute(sa.text(CREATE_IDENTIFIER))
    op.execute(sa.text(CREATE_CANDIDATE_GUARD))
    op.execute(sa.text(CREATE_IDENTIFIER_GUARD))
    _execute_each(CREATE_TRIGGERS)
    _execute_each(COMMENTS)


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_CANDIDATES_EXIST))
    op.execute("DROP TABLE v2.company_candidate_identifier")
    op.execute("DROP TABLE v2.company_candidate")
    op.execute("DROP FUNCTION v2.company_candidate_identifier_guard()")
    op.execute("DROP FUNCTION v2.company_candidate_guard()")
