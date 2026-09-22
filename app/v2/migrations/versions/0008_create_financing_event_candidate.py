"""Create v2.financing_event_candidate (+ _amount, _date)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-21

The first CAPITAL table: UNTRUSTED PROPOSALS about what evidence appears to say concerning a startup
financing. Not a financing, not verified, not a funding amount, not canonical: NO canonical financing_event
table exists at this revision, and nothing here can be promoted.

Shape (one concrete vertical, no generic fact/EAV system):
  financing_event_candidate         one proposal. Belongs to exactly one ProcessingAttempt and concerns exactly
                                    one canonical Company (real FK to v2.company; never a name/domain/URL).
                                    Identity (processing_attempt_id, candidate_ordinal). Carries mandatory
                                    EVENT-LEVEL evidence, plus optional stage and financing type, each with its own
                                    evidence; 'unknown' (the default) has none and is never inferred.
  financing_event_candidate_amount  at most one row per amount semantics: offering_amount | amount_sold |
                                    announced_round_amount. Exact BIGINT minor units + explicit currency; never a
                                    float; no default currency; no FX; no generic "amount".
  financing_event_candidate_date    at most one row per date kind: first_sale_date | filing_date | announcement_date,
                                    with the precision the source gave (year stays a year).

Database protections (the domain and repository verify first; these are the backstop for every writer):
  - INSERT triggers: the attempt must be PROCESSING (row-locked FOR SHARE), and every evidence span must lie inside
    the observation's stored payload and hash to its stored hash (v2.evidence_span_matches).
  - created_at is the database's clock. UPDATE/DELETE/TRUNCATE are rejected on all three tables. FKs are RESTRICT.

Downgrade removes only these objects and REFUSES to run while any financing candidate exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

STAGES = "('pre_seed', 'seed', 'series_a', 'series_b', 'growth', 'unknown')"
TYPES = "('equity', 'convertible', 'debt', 'other', 'unknown')"
SEMANTICS = "('offering_amount', 'amount_sold', 'announced_round_amount')"
DATE_KINDS = "('first_sale_date', 'filing_date', 'announcement_date')"

CREATE_EVIDENCE_FN = r"""
CREATE FUNCTION v2.evidence_span_matches(payload_hash TEXT, span_start INTEGER, span_end INTEGER, span_hash TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE AS $$
DECLARE
    stored_bytes BYTEA;
BEGIN
    IF span_start IS NULL OR span_end IS NULL OR span_start < 0 OR span_end <= span_start THEN
        RETURN false;
    END IF;
    SELECT payload_bytes INTO stored_bytes FROM v2.raw_payload WHERE content_hash = payload_hash;
    IF stored_bytes IS NULL OR span_end > octet_length(stored_bytes) THEN
        RETURN false;
    END IF;
    RETURN encode(sha256(substring(stored_bytes FROM span_start + 1 FOR span_end - span_start)), 'hex') = span_hash;
END
$$
"""

CREATE_CANDIDATE = f"""
CREATE TABLE v2.financing_event_candidate (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY,
    processing_attempt_id   BIGINT      NOT NULL,
    company_id              UUID        NOT NULL,
    candidate_ordinal       INTEGER     NOT NULL,
    event_evidence_start    INTEGER     NOT NULL,
    event_evidence_end      INTEGER     NOT NULL,
    event_evidence_hash     TEXT        NOT NULL,
    stage                   TEXT        NOT NULL DEFAULT 'unknown',
    stage_evidence_start    INTEGER     NULL,
    stage_evidence_end      INTEGER     NULL,
    stage_evidence_hash     TEXT        NULL,
    financing_type          TEXT        NOT NULL DEFAULT 'unknown',
    type_evidence_start     INTEGER     NULL,
    type_evidence_end       INTEGER     NULL,
    type_evidence_hash      TEXT        NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_financing_event_candidate PRIMARY KEY (id),
    CONSTRAINT fk_fec_processing_attempt_id FOREIGN KEY (processing_attempt_id) REFERENCES v2.processing_attempt (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fec_company_id FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT uq_financing_event_candidate_ordinal UNIQUE (processing_attempt_id, candidate_ordinal),
    CONSTRAINT ck_financing_event_candidate_ordinal_range CHECK (candidate_ordinal BETWEEN 1 AND 1000),
    CONSTRAINT ck_financing_event_candidate_event_evidence_span
        CHECK (event_evidence_start >= 0 AND event_evidence_end > event_evidence_start AND event_evidence_end - event_evidence_start <= 4096),
    CONSTRAINT ck_financing_event_candidate_event_evidence_hash_shape CHECK (event_evidence_hash ~ '^[0-9a-f]{{64}}$'),
    CONSTRAINT ck_financing_event_candidate_stage_allowed CHECK (stage IN {STAGES}),
    CONSTRAINT ck_financing_event_candidate_type_allowed CHECK (financing_type IN {TYPES}),
    CONSTRAINT ck_financing_event_candidate_stage_evidence_matches_stage
        CHECK ((stage = 'unknown') = (stage_evidence_start IS NULL AND stage_evidence_end IS NULL AND stage_evidence_hash IS NULL)
               AND (stage <> 'unknown') = (stage_evidence_start IS NOT NULL AND stage_evidence_end IS NOT NULL AND stage_evidence_hash IS NOT NULL)),
    CONSTRAINT ck_financing_event_candidate_type_evidence_matches_type
        CHECK ((financing_type = 'unknown') = (type_evidence_start IS NULL AND type_evidence_end IS NULL AND type_evidence_hash IS NULL)
               AND (financing_type <> 'unknown') = (type_evidence_start IS NOT NULL AND type_evidence_end IS NOT NULL AND type_evidence_hash IS NOT NULL)),
    CONSTRAINT ck_financing_event_candidate_optional_evidence_shape
        CHECK ((stage_evidence_start IS NULL OR (stage_evidence_start >= 0 AND stage_evidence_end > stage_evidence_start
                                                 AND stage_evidence_end - stage_evidence_start <= 4096 AND stage_evidence_hash ~ '^[0-9a-f]{{64}}$'))
               AND (type_evidence_start IS NULL OR (type_evidence_start >= 0 AND type_evidence_end > type_evidence_start
                                                    AND type_evidence_end - type_evidence_start <= 4096 AND type_evidence_hash ~ '^[0-9a-f]{{64}}$')))
)
"""

CREATE_AMOUNT = f"""
CREATE TABLE v2.financing_event_candidate_amount (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY,
    candidate_id          BIGINT  NOT NULL,
    amount_semantics      TEXT    NOT NULL,
    currency_code         TEXT    NOT NULL,
    amount_minor_units    BIGINT  NOT NULL,
    evidence_start        INTEGER NOT NULL,
    evidence_end          INTEGER NOT NULL,
    evidence_hash         TEXT    NOT NULL,
    CONSTRAINT pk_financing_event_candidate_amount PRIMARY KEY (id),
    CONSTRAINT fk_fec_amount_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.financing_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_financing_event_candidate_amount_semantics UNIQUE (candidate_id, amount_semantics),
    CONSTRAINT ck_financing_event_candidate_amount_semantics_allowed CHECK (amount_semantics IN {SEMANTICS}),
    CONSTRAINT ck_financing_event_candidate_amount_currency_shape CHECK (currency_code ~ '^[A-Z]{{3}}$'),
    CONSTRAINT ck_financing_event_candidate_amount_non_negative CHECK (amount_minor_units >= 0),
    CONSTRAINT ck_financing_event_candidate_amount_evidence_span
        CHECK (evidence_start >= 0 AND evidence_end > evidence_start AND evidence_end - evidence_start <= 4096),
    CONSTRAINT ck_financing_event_candidate_amount_evidence_hash_shape CHECK (evidence_hash ~ '^[0-9a-f]{{64}}$')
)
"""

CREATE_DATE = f"""
CREATE TABLE v2.financing_event_candidate_date (
    id               BIGINT GENERATED ALWAYS AS IDENTITY,
    candidate_id     BIGINT      NOT NULL,
    date_kind        TEXT        NOT NULL,
    date_precision   TEXT        NOT NULL,
    date_start       TIMESTAMPTZ NOT NULL,
    evidence_start   INTEGER     NOT NULL,
    evidence_end     INTEGER     NOT NULL,
    evidence_hash    TEXT        NOT NULL,
    CONSTRAINT pk_financing_event_candidate_date PRIMARY KEY (id),
    CONSTRAINT fk_fec_date_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.financing_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_financing_event_candidate_date_kind UNIQUE (candidate_id, date_kind),
    CONSTRAINT ck_financing_event_candidate_date_kind_allowed CHECK (date_kind IN {DATE_KINDS}),
    CONSTRAINT ck_financing_event_candidate_date_precision_allowed CHECK (date_precision IN ('instant', 'day', 'month', 'year')),
    CONSTRAINT ck_financing_event_candidate_date_start_matches_precision
        CHECK (CASE date_precision
                 WHEN 'instant' THEN true
                 WHEN 'day'     THEN date_trunc('day',   date_start AT TIME ZONE 'UTC') = date_start AT TIME ZONE 'UTC'
                 WHEN 'month'   THEN date_trunc('month', date_start AT TIME ZONE 'UTC') = date_start AT TIME ZONE 'UTC'
                 WHEN 'year'    THEN date_trunc('year',  date_start AT TIME ZONE 'UTC') = date_start AT TIME ZONE 'UTC'
                 ELSE false END),
    CONSTRAINT ck_financing_event_candidate_date_evidence_span
        CHECK (evidence_start >= 0 AND evidence_end > evidence_start AND evidence_end - evidence_start <= 4096),
    CONSTRAINT ck_financing_event_candidate_date_evidence_hash_shape CHECK (evidence_hash ~ '^[0-9a-f]{{64}}$')
)
"""

CREATE_CANDIDATE_GUARD = r"""
CREATE FUNCTION v2.financing_event_candidate_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    attempt_status TEXT;
    stored_hash    TEXT;
BEGIN
    SELECT a.status, o.content_hash INTO attempt_status, stored_hash
      FROM v2.processing_attempt a JOIN v2.observation o ON o.id = a.observation_id
     WHERE a.id = NEW.processing_attempt_id
       FOR SHARE OF a;
    IF NOT FOUND THEN
        RETURN NEW;   -- the foreign key reports the missing attempt
    END IF;
    IF attempt_status <> 'processing' THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.financing_event_candidate: candidates can only be added while the attempt is processing',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NOT v2.evidence_span_matches(stored_hash, NEW.event_evidence_start, NEW.event_evidence_end, NEW.event_evidence_hash)
       OR (NEW.stage <> 'unknown'
           AND NOT v2.evidence_span_matches(stored_hash, NEW.stage_evidence_start, NEW.stage_evidence_end, NEW.stage_evidence_hash))
       OR (NEW.financing_type <> 'unknown'
           AND NOT v2.evidence_span_matches(stored_hash, NEW.type_evidence_start, NEW.type_evidence_end, NEW.type_evidence_hash)) THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.financing_event_candidate: evidence does not match the stored payload bytes',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    NEW.created_at := clock_timestamp();   -- the database's clock, whatever the writer supplied
    RETURN NEW;
END
$$
"""


def _child_guard(table: str) -> str:
    return f"""
CREATE FUNCTION v2.{table}_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    attempt_status TEXT;
    stored_hash    TEXT;
BEGIN
    SELECT a.status, o.content_hash INTO attempt_status, stored_hash
      FROM v2.financing_event_candidate c
      JOIN v2.processing_attempt a ON a.id = c.processing_attempt_id
      JOIN v2.observation o ON o.id = a.observation_id
     WHERE c.id = NEW.candidate_id
       FOR SHARE OF a;
    IF NOT FOUND THEN
        RETURN NEW;   -- the foreign key reports the missing candidate
    END IF;
    IF attempt_status <> 'processing' THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.{table}: facts can only be added while the attempt is processing',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NOT v2.evidence_span_matches(stored_hash, NEW.evidence_start, NEW.evidence_end, NEW.evidence_hash) THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.{table}: evidence does not match the stored payload bytes',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END
$$
"""


TABLES = ("financing_event_candidate", "financing_event_candidate_amount", "financing_event_candidate_date")


def _triggers() -> list[str]:
    statements = []
    for table in TABLES:
        statements += [
            f"CREATE TRIGGER trg_{table}_guard BEFORE INSERT ON v2.{table} FOR EACH ROW EXECUTE FUNCTION v2.{table}_guard()",
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON v2.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change()",
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON v2.{table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change()",
        ]
    return statements


COMMENTS = [
    "COMMENT ON TABLE v2.financing_event_candidate IS "
    "'UNTRUSTED PROPOSALS about what evidence appears to say concerning a startup financing. Not a verified or canonical financing.'",
    "COMMENT ON TABLE v2.financing_event_candidate_amount IS "
    "'UNTRUSTED proposed amount of a financing candidate; the semantics column says what the amount claims to be. Not a verified round size.'",
    "COMMENT ON TABLE v2.financing_event_candidate_date IS "
    "'UNTRUSTED proposed dated fact of a financing candidate, with the precision the source gave.'",
]

REFUSE_IF_CANDIDATES_EXIST = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.financing_event_candidate) OR EXISTS (SELECT 1 FROM v2.financing_event_candidate_amount)
       OR EXISTS (SELECT 1 FROM v2.financing_event_candidate_date) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0008: v2.financing_event_candidate contains candidate history',
            HINT = 'Candidate history is never discarded by a migration. Back it up and drop the tables by hand if you truly mean to.',
            ERRCODE = 'restrict_violation';
    END IF;
END
$$
"""


def upgrade() -> None:
    op.execute(sa.text(CREATE_EVIDENCE_FN))
    op.execute(sa.text(CREATE_CANDIDATE))
    op.execute(sa.text(CREATE_AMOUNT))
    op.execute(sa.text(CREATE_DATE))
    op.execute(sa.text(CREATE_CANDIDATE_GUARD))
    op.execute(sa.text(_child_guard("financing_event_candidate_amount")))
    op.execute(sa.text(_child_guard("financing_event_candidate_date")))
    for statement in _triggers() + COMMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_CANDIDATES_EXIST))
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE v2.{table}")
    for function in ("financing_event_candidate_date_guard()", "financing_event_candidate_amount_guard()",
                     "financing_event_candidate_guard()", "evidence_span_matches(text, integer, integer, text)"):
        op.execute(f"DROP FUNCTION v2.{function}")
