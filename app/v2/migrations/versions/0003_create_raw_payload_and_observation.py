"""Create v2.raw_payload and v2.observation

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-21

Immutable evidence storage. Storage and integrity only: no ingestion, no
sightings, no processing state, no interpretation.

raw_payload   the EXACT received bytes, content-addressed by
              content_hash = sha256(bytes) (lowercase hex). Identical bytes are
              stored once. A CHECK recomputes sha256 so the database itself
              refuses bytes that do not match their key. Inline storage only
              (<= 1 MiB); storage_kind leaves room for external storage later
              without a schema rewrite.

observation   "this Source exposed these bytes at this observed time".
              Evidence only: no status, no AI fields, no company identity.
              Times stay distinct: event_time (+ explicit precision, paired),
              observed_time (caller-supplied), recorded_time (database-assigned
              by trigger, never trusted from the caller).

Dedup identity: (source_id, source_record_identifier, content_hash), with
"no record identifier" a first-class value. Ordinary UNIQUE treats NULLs as
distinct, and UNIQUE NULLS NOT DISTINCT needs PostgreSQL 15, so identity is
two partial unique indexes: one where the identifier is present, one where it
is absent. Together they make the rule deterministic on any supported version.

Append-only: UPDATE, DELETE and TRUNCATE on both tables are rejected by
trigger for every writer (restrict_violation). Foreign keys are ON DELETE
RESTRICT, so a Source or payload that evidence references can never be removed.

CHECKs guard integrity; the domain models stay the richer validators. The
inline size limit (1048576) is defined ONCE in app/v2/domain/payload.py
(MAX_INLINE_PAYLOAD_BYTES); it appears here as a literal because a migration
must stay a frozen snapshot, and a test asserts the two agree.

Downgrade removes only these objects, and REFUSES to run if either table
holds rows: evidence is never silently destroyed by a migration. (Back up and
drop by hand if you really mean to discard evidence.)
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

MEDIA_TYPES = ("text/plain", "text/html", "application/json", "application/pdf", "unknown")
PRECISIONS = ("instant", "day", "month", "year")


def _in_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


CREATE_RAW_PAYLOAD = """
CREATE TABLE v2.raw_payload (
    content_hash  TEXT   NOT NULL,
    storage_kind  TEXT   NOT NULL,
    size_bytes    BIGINT NOT NULL,
    payload_bytes BYTEA,
    CONSTRAINT pk_raw_payload PRIMARY KEY (content_hash),
    CONSTRAINT ck_raw_payload_content_hash_shape
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_raw_payload_storage_kind_allowed
        CHECK (storage_kind IN ('inline')),
    CONSTRAINT ck_raw_payload_size_within_limit
        CHECK (size_bytes >= 0 AND size_bytes <= 1048576),
    CONSTRAINT ck_raw_payload_inline_bytes_present
        CHECK ((storage_kind = 'inline') = (payload_bytes IS NOT NULL)),
    CONSTRAINT ck_raw_payload_size_matches_bytes
        CHECK (payload_bytes IS NULL OR octet_length(payload_bytes) = size_bytes),
    CONSTRAINT ck_raw_payload_hash_matches_bytes
        CHECK (payload_bytes IS NULL OR encode(sha256(payload_bytes), 'hex') = content_hash)
)
"""

CREATE_OBSERVATION = f"""
CREATE TABLE v2.observation (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY,
    source_id                BIGINT      NOT NULL,
    source_record_identifier TEXT,
    observation_type         TEXT        NOT NULL,
    event_time               TIMESTAMPTZ,
    event_time_precision     TEXT,
    observed_time            TIMESTAMPTZ NOT NULL,
    recorded_time            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    collection_version       TEXT        NOT NULL,
    collector_id             TEXT        NOT NULL,
    content_hash             TEXT        NOT NULL,
    declared_media_type      TEXT,
    sniffed_media_type       TEXT        NOT NULL,
    CONSTRAINT pk_observation PRIMARY KEY (id),
    CONSTRAINT fk_observation_source_id_source
        FOREIGN KEY (source_id) REFERENCES v2.source (id) ON DELETE RESTRICT,
    CONSTRAINT fk_observation_content_hash_raw_payload
        FOREIGN KEY (content_hash) REFERENCES v2.raw_payload (content_hash) ON DELETE RESTRICT,
    CONSTRAINT ck_observation_source_record_identifier_valid
        CHECK (source_record_identifier IS NULL
               OR (char_length(source_record_identifier) BETWEEN 1 AND 512
                   AND source_record_identifier !~ '[\\x01-\\x1f\\x7f]')),
    CONSTRAINT ck_observation_observation_type_shape
        CHECK (observation_type ~ '^[a-z][a-z0-9_]{{1,63}}$'),
    CONSTRAINT ck_observation_event_time_paired
        CHECK ((event_time IS NULL) = (event_time_precision IS NULL)),
    CONSTRAINT ck_observation_event_time_precision_allowed
        CHECK (event_time_precision IS NULL OR event_time_precision IN ({_in_list(PRECISIONS)})),
    CONSTRAINT ck_observation_event_time_start_matches_precision
        CHECK (event_time IS NULL OR CASE event_time_precision
                 WHEN 'instant' THEN true
                 WHEN 'day'     THEN date_trunc('day',   event_time AT TIME ZONE 'UTC') = event_time AT TIME ZONE 'UTC'
                 WHEN 'month'   THEN date_trunc('month', event_time AT TIME ZONE 'UTC') = event_time AT TIME ZONE 'UTC'
                 WHEN 'year'    THEN date_trunc('year',  event_time AT TIME ZONE 'UTC') = event_time AT TIME ZONE 'UTC'
                 ELSE false END),
    CONSTRAINT ck_observation_collection_version_shape
        CHECK (collection_version ~ '^[a-z][a-z0-9_]{{0,63}}\\.v[1-9][0-9]{{0,5}}$'),
    CONSTRAINT ck_observation_collector_id_shape
        CHECK (collector_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:@/-]{{0,127}}$'),
    CONSTRAINT ck_observation_declared_media_type_shape
        CHECK (declared_media_type IS NULL
               OR (char_length(declared_media_type) <= 255
                   AND declared_media_type ~ '^[a-z0-9][a-z0-9!#$&^_.+-]{{0,126}}/[a-z0-9][a-z0-9!#$&^_.+-]{{0,126}}$')),
    CONSTRAINT ck_observation_sniffed_media_type_allowed
        CHECK (sniffed_media_type IN ({_in_list(MEDIA_TYPES)}))
)
"""

CREATE_DEDUP_INDEXES = """
CREATE UNIQUE INDEX uq_observation_dedup_with_record_id
    ON v2.observation (source_id, source_record_identifier, content_hash)
    WHERE source_record_identifier IS NOT NULL;
CREATE UNIQUE INDEX uq_observation_dedup_without_record_id
    ON v2.observation (source_id, content_hash)
    WHERE source_record_identifier IS NULL
"""

CREATE_FORBID_FUNCTION = """
CREATE FUNCTION v2.forbid_evidence_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'v2.' || TG_TABLE_NAME || ' is append-only: ' || TG_OP || ' is not permitted',
        ERRCODE = 'restrict_violation';
END
$$
"""

CREATE_STAMP_FUNCTION = """
CREATE FUNCTION v2.observation_stamp() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- recorded_time is when the database persisted the row, whatever the writer supplied.
    NEW.recorded_time := clock_timestamp();
    RETURN NEW;
END
$$
"""

CREATE_TRIGGERS = """
CREATE TRIGGER trg_raw_payload_append_only
    BEFORE UPDATE OR DELETE ON v2.raw_payload
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_raw_payload_no_truncate
    BEFORE TRUNCATE ON v2.raw_payload
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_observation_append_only
    BEFORE UPDATE OR DELETE ON v2.observation
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_observation_no_truncate
    BEFORE TRUNCATE ON v2.observation
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_observation_stamp
    BEFORE INSERT ON v2.observation
    FOR EACH ROW EXECUTE FUNCTION v2.observation_stamp()
"""

REFUSE_IF_EVIDENCE_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.observation) OR EXISTS (SELECT 1 FROM v2.raw_payload) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0003: v2.observation / v2.raw_payload contain evidence',
            HINT = 'Evidence is append-only. Back it up and drop these tables by hand if you truly mean to discard it.',
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
    op.execute(sa.text(CREATE_RAW_PAYLOAD))
    op.execute(sa.text(CREATE_OBSERVATION))
    _execute_each(CREATE_DEDUP_INDEXES)
    op.execute(sa.text(CREATE_FORBID_FUNCTION))
    op.execute(sa.text(CREATE_STAMP_FUNCTION))
    _execute_each(CREATE_TRIGGERS)


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_EVIDENCE_EXISTS))
    op.execute("DROP TABLE v2.observation")   # drops its indexes and triggers
    op.execute("DROP TABLE v2.raw_payload")
    op.execute("DROP FUNCTION v2.observation_stamp()")
    op.execute("DROP FUNCTION v2.forbid_evidence_change()")
