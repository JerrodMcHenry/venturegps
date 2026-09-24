"""Create v2.lifecycle_event_candidate (+4 typed fact tables), v2.lifecycle_resolution_decision, and the four
canonical lifecycle fact tables (company_name_history, company_operating_status, company_acquisition,
company_successor_relationship)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-24

The lifecycle resolution boundary (Increment 18.7): the ONLY path from an UNTRUSTED LifecycleEventCandidate to
an accepted canonical lifecycle fact about an ALREADY-canonical Company.

    LifecycleEventCandidate [untrusted] -> LifecycleResolutionDecision [human only] -> accepted fact(s) [trusted]

Unlike financing, there is no separate "event" identity being created here -- a lifecycle candidate always
proposes facts about a Company that already exists; the decision annotates it directly. Four narrow, typed
fact kinds (never a generic event/knowledge-graph table):

  company_name_history               the SAME legal entity was renamed; company_name's own canonical row is
                                      never touched -- "current legal name" is a derived read (latest by date)
  company_operating_status           active | acquired | ceased_operations | unknown; unknown is a legitimate,
                                      explicit accepted claim, not merely the absence of a row
  company_acquisition                a relationship between DISTINCT entities; NEVER implies a status change
                                      (accepting this writes nothing to company_operating_status)
  company_successor_relationship     possible_successor | confirmed_successor between DISTINCT entities; NEVER
                                      transfers identifiers, financing, or classifications

decided_by_kind is CHECKed to 'rule' | 'human', matching every other resolution table's shape -- but the guard
trigger refuses EVERY rule decision unconditionally (LIFECYCLE_RULE_AUTHORITY is empty in the domain layer;
this is the same defense-in-depth the database already enforces a second time for financing and classification
rule authority). A candidate has at most one FINAL decision (partial unique index): accepted, rejected, or
deferred (not final). Each of the four fact tables' own guard trigger re-verifies, at INSERT time, that the
accepted value exactly matches what the resolved candidate itself proposed (mirrors financing_event_stage's
own STAGE_GUARD pattern) -- a fact can never be accepted with a different value than the candidate proposed.

CORRECTIONS: nothing here has a "one fact per company" uniqueness constraint (deliberately, unlike financing's
"one stage per event") -- a company may accumulate MANY accepted name/status/acquisition/successor facts over
time, each its own candidate and decision; "current" is always the most-recently-accepted row, a derived read,
never a rewrite. All tables are append-only (UPDATE/DELETE/TRUNCATE rejected), created_at is the database's,
every FK is ON DELETE RESTRICT.

Downgrade removes only these objects and REFUSES to run while any lifecycle candidate or resolution history exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_FINAL = "('accept_lifecycle_event', 'reject_candidate')"
_PRECISIONS = "('instant', 'day', 'month', 'year')"
_STATUSES = "('active', 'acquired', 'ceased_operations', 'unknown')"
_RELATIONSHIP_KINDS = "('possible_successor', 'confirmed_successor')"
_PRECISION_MATCH = """(CASE {prefix}_precision
                 WHEN 'instant' THEN true
                 WHEN 'day'     THEN date_trunc('day',   {prefix}_start AT TIME ZONE 'UTC') = {prefix}_start AT TIME ZONE 'UTC'
                 WHEN 'month'   THEN date_trunc('month', {prefix}_start AT TIME ZONE 'UTC') = {prefix}_start AT TIME ZONE 'UTC'
                 WHEN 'year'    THEN date_trunc('year',  {prefix}_start AT TIME ZONE 'UTC') = {prefix}_start AT TIME ZONE 'UTC'
                 ELSE false END)"""

CANDIDATE_TABLES = ("lifecycle_event_candidate", "lifecycle_event_candidate_name_change",
                    "lifecycle_event_candidate_operating_status", "lifecycle_event_candidate_acquisition",
                    "lifecycle_event_candidate_successor")
DECISION_TABLE = "lifecycle_resolution_decision"
CANONICAL_TABLES = ("company_name_history", "company_operating_status", "company_acquisition", "company_successor_relationship")
ALL_TABLES = CANDIDATE_TABLES + (DECISION_TABLE,) + CANONICAL_TABLES

CREATE_CANDIDATE = """
CREATE TABLE v2.lifecycle_event_candidate (
    id                    BIGINT      GENERATED ALWAYS AS IDENTITY,
    processing_attempt_id BIGINT      NOT NULL,
    company_id            UUID        NOT NULL,
    candidate_ordinal     INTEGER     NOT NULL,
    event_evidence_start  INTEGER     NOT NULL,
    event_evidence_end    INTEGER     NOT NULL,
    event_evidence_hash   TEXT        NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_lifecycle_event_candidate PRIMARY KEY (id),
    CONSTRAINT fk_lec_processing_attempt_id FOREIGN KEY (processing_attempt_id) REFERENCES v2.processing_attempt (id) ON DELETE RESTRICT,
    CONSTRAINT fk_lec_company_id FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT uq_lec_attempt_ordinal UNIQUE (processing_attempt_id, candidate_ordinal),
    CONSTRAINT ck_lec_ordinal_positive CHECK (candidate_ordinal >= 1),
    CONSTRAINT ck_lec_evidence_span CHECK (event_evidence_end > event_evidence_start AND event_evidence_start >= 0)
)
"""

CREATE_CANDIDATE_NAME_CHANGE = f"""
CREATE TABLE v2.lifecycle_event_candidate_name_change (
    id                  BIGINT      GENERATED ALWAYS AS IDENTITY,
    candidate_id        BIGINT      NOT NULL,
    new_name            TEXT        NOT NULL,
    effective_precision TEXT        NULL,
    effective_start     TIMESTAMPTZ NULL,
    evidence_start      INTEGER     NOT NULL,
    evidence_end        INTEGER     NOT NULL,
    evidence_hash       TEXT        NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_lec_name_change PRIMARY KEY (id),
    CONSTRAINT fk_lec_nc_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.lifecycle_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_lec_nc_candidate UNIQUE (candidate_id),
    CONSTRAINT ck_lec_nc_name_not_blank CHECK (char_length(btrim(new_name)) > 0),
    CONSTRAINT ck_lec_nc_precision_allowed CHECK (effective_precision IS NULL OR effective_precision IN {_PRECISIONS}),
    CONSTRAINT ck_lec_nc_effective_shape CHECK ((effective_precision IS NULL) = (effective_start IS NULL)),
    CONSTRAINT ck_lec_nc_effective_matches_precision
        CHECK (effective_precision IS NULL OR {_PRECISION_MATCH.format(prefix="effective")})
)
"""

CREATE_CANDIDATE_OPERATING_STATUS = f"""
CREATE TABLE v2.lifecycle_event_candidate_operating_status (
    id             BIGINT      GENERATED ALWAYS AS IDENTITY,
    candidate_id   BIGINT      NOT NULL,
    status         TEXT        NOT NULL,
    as_of_precision TEXT       NULL,
    as_of_start    TIMESTAMPTZ NULL,
    evidence_start INTEGER     NOT NULL,
    evidence_end   INTEGER     NOT NULL,
    evidence_hash  TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_lec_operating_status PRIMARY KEY (id),
    CONSTRAINT fk_lec_os_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.lifecycle_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_lec_os_candidate UNIQUE (candidate_id),
    CONSTRAINT ck_lec_os_status_allowed CHECK (status IN {_STATUSES}),
    CONSTRAINT ck_lec_os_precision_allowed CHECK (as_of_precision IS NULL OR as_of_precision IN {_PRECISIONS}),
    CONSTRAINT ck_lec_os_as_of_shape CHECK ((as_of_precision IS NULL) = (as_of_start IS NULL)),
    CONSTRAINT ck_lec_os_as_of_matches_precision
        CHECK (as_of_precision IS NULL OR {_PRECISION_MATCH.format(prefix="as_of")})
)
"""

CREATE_CANDIDATE_ACQUISITION = f"""
CREATE TABLE v2.lifecycle_event_candidate_acquisition (
    id                       BIGINT      GENERATED ALWAYS AS IDENTITY,
    candidate_id             BIGINT      NOT NULL,
    acquirer_name            TEXT        NOT NULL,
    acquirer_company_id      UUID        NULL,
    transaction_date_precision TEXT      NULL,
    transaction_date_start   TIMESTAMPTZ NULL,
    evidence_start           INTEGER     NOT NULL,
    evidence_end             INTEGER     NOT NULL,
    evidence_hash            TEXT        NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_lec_acquisition PRIMARY KEY (id),
    CONSTRAINT fk_lec_acq_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.lifecycle_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT fk_lec_acq_acquirer_company_id FOREIGN KEY (acquirer_company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT uq_lec_acq_candidate UNIQUE (candidate_id),
    CONSTRAINT ck_lec_acq_name_not_blank CHECK (char_length(btrim(acquirer_name)) > 0),
    CONSTRAINT ck_lec_acq_precision_allowed CHECK (transaction_date_precision IS NULL OR transaction_date_precision IN {_PRECISIONS}),
    CONSTRAINT ck_lec_acq_date_shape CHECK ((transaction_date_precision IS NULL) = (transaction_date_start IS NULL)),
    CONSTRAINT ck_lec_acq_date_matches_precision
        CHECK (transaction_date_precision IS NULL OR {_PRECISION_MATCH.format(prefix="transaction_date")})
)
"""

CREATE_CANDIDATE_SUCCESSOR = f"""
CREATE TABLE v2.lifecycle_event_candidate_successor (
    id                   BIGINT      GENERATED ALWAYS AS IDENTITY,
    candidate_id         BIGINT      NOT NULL,
    related_entity_name  TEXT        NOT NULL,
    related_company_id   UUID        NULL,
    relationship_kind    TEXT        NOT NULL,
    evidence_start       INTEGER     NOT NULL,
    evidence_end         INTEGER     NOT NULL,
    evidence_hash        TEXT        NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_lec_successor PRIMARY KEY (id),
    CONSTRAINT fk_lec_succ_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.lifecycle_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT fk_lec_succ_related_company_id FOREIGN KEY (related_company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT uq_lec_succ_candidate UNIQUE (candidate_id),
    CONSTRAINT ck_lec_succ_name_not_blank CHECK (char_length(btrim(related_entity_name)) > 0),
    CONSTRAINT ck_lec_succ_kind_allowed CHECK (relationship_kind IN {_RELATIONSHIP_KINDS})
)
"""

CREATE_DECISION = rf"""
CREATE TABLE v2.lifecycle_resolution_decision (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY,
    candidate_id    BIGINT      NOT NULL,
    decision_kind   TEXT        NOT NULL,
    decided_by_kind TEXT        NOT NULL,
    decided_by_id   TEXT        NOT NULL,
    reason_code     TEXT        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_lifecycle_resolution_decision PRIMARY KEY (id),
    CONSTRAINT fk_lrd_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.lifecycle_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT ck_lrd_kind_allowed CHECK (decision_kind IN ('accept_lifecycle_event', 'reject_candidate', 'defer_candidate')),
    CONSTRAINT ck_lrd_authority_allowed CHECK (decided_by_kind IN ('rule', 'human')),
    CONSTRAINT ck_lrd_actor_human
        CHECK (decided_by_kind <> 'human'
               OR decided_by_id ~ '^[a-z][a-z0-9_]{{0,31}}:[A-Za-z0-9][A-Za-z0-9_.-]{{0,63}}$'),
    CONSTRAINT ck_lrd_actor_rule
        CHECK (decided_by_kind <> 'rule' OR decided_by_id ~ '^[a-z][a-z0-9_]{{0,62}}\.v[0-9]{{1,4}}$'),
    CONSTRAINT ck_lrd_actor_is_not_ai
        CHECK (decided_by_id !~* '(^|[^a-z])(ai|llm|gpt|chatgpt|openai|anthropic|claude|gemini|copilot|model|bot|agent)([^a-z]|$)'),
    CONSTRAINT ck_lrd_reason_matches_kind
        CHECK ((decision_kind IN ('reject_candidate', 'defer_candidate')) = (reason_code IS NOT NULL)),
    CONSTRAINT ck_lrd_reason_shape CHECK (reason_code IS NULL OR reason_code ~ '^[a-z][a-z0-9_]{{1,63}}$')
)
"""

CREATE_NAME_HISTORY = """
CREATE TABLE v2.company_name_history (
    id                      BIGINT      GENERATED ALWAYS AS IDENTITY,
    company_id              UUID        NOT NULL,
    new_name                TEXT        NOT NULL,
    effective_precision     TEXT        NULL,
    effective_start         TIMESTAMPTZ NULL,
    resolution_decision_id  BIGINT      NOT NULL,
    candidate_id            BIGINT      NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_company_name_history PRIMARY KEY (id),
    CONSTRAINT fk_cnh_company_id FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT fk_cnh_resolution_decision_id FOREIGN KEY (resolution_decision_id) REFERENCES v2.lifecycle_resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_cnh_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.lifecycle_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_cnh_resolution_decision UNIQUE (resolution_decision_id),
    CONSTRAINT uq_cnh_candidate UNIQUE (candidate_id)
)
"""

CREATE_OPERATING_STATUS = """
CREATE TABLE v2.company_operating_status (
    id                      BIGINT      GENERATED ALWAYS AS IDENTITY,
    company_id              UUID        NOT NULL,
    status                  TEXT        NOT NULL,
    as_of_precision         TEXT        NULL,
    as_of_start             TIMESTAMPTZ NULL,
    resolution_decision_id  BIGINT      NOT NULL,
    candidate_id            BIGINT      NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_company_operating_status PRIMARY KEY (id),
    CONSTRAINT fk_cos_company_id FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT fk_cos_resolution_decision_id FOREIGN KEY (resolution_decision_id) REFERENCES v2.lifecycle_resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_cos_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.lifecycle_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_cos_resolution_decision UNIQUE (resolution_decision_id),
    CONSTRAINT uq_cos_candidate UNIQUE (candidate_id)
)
"""

CREATE_ACQUISITION = """
CREATE TABLE v2.company_acquisition (
    id                        BIGINT      GENERATED ALWAYS AS IDENTITY,
    company_id                UUID        NOT NULL,
    acquirer_name              TEXT        NOT NULL,
    acquirer_company_id        UUID        NULL,
    transaction_date_precision TEXT        NULL,
    transaction_date_start     TIMESTAMPTZ NULL,
    resolution_decision_id     BIGINT      NOT NULL,
    candidate_id                BIGINT      NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_company_acquisition PRIMARY KEY (id),
    CONSTRAINT fk_ca_company_id FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT fk_ca_acquirer_company_id FOREIGN KEY (acquirer_company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT fk_ca_resolution_decision_id FOREIGN KEY (resolution_decision_id) REFERENCES v2.lifecycle_resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_ca_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.lifecycle_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_ca_resolution_decision UNIQUE (resolution_decision_id),
    CONSTRAINT uq_ca_candidate UNIQUE (candidate_id)
)
"""

CREATE_SUCCESSOR = """
CREATE TABLE v2.company_successor_relationship (
    id                      BIGINT      GENERATED ALWAYS AS IDENTITY,
    company_id              UUID        NOT NULL,
    related_entity_name     TEXT        NOT NULL,
    related_company_id      UUID        NULL,
    relationship_kind       TEXT        NOT NULL,
    resolution_decision_id  BIGINT      NOT NULL,
    candidate_id            BIGINT      NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_company_successor_relationship PRIMARY KEY (id),
    CONSTRAINT fk_csr_company_id FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT fk_csr_related_company_id FOREIGN KEY (related_company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT fk_csr_resolution_decision_id FOREIGN KEY (resolution_decision_id) REFERENCES v2.lifecycle_resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_csr_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.lifecycle_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_csr_resolution_decision UNIQUE (resolution_decision_id),
    CONSTRAINT uq_csr_candidate UNIQUE (candidate_id)
)
"""

CREATE_INDEXES = f"""
CREATE UNIQUE INDEX uq_lrd_one_final ON v2.lifecycle_resolution_decision (candidate_id) WHERE decision_kind IN {_FINAL};
CREATE INDEX ix_lec_company_id ON v2.lifecycle_event_candidate (company_id)
"""

CREATE_CANDIDATE_GUARD = """
CREATE FUNCTION v2.lifecycle_event_candidate_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

# Shared shape for the four candidate fact-table guards: just stamp created_at (each candidate's facts are
# independently written once, alongside the candidate row itself, inside one persist_lifecycle_event_candidates
# transaction -- there is no cross-row consistency to check here, unlike the CANONICAL fact tables below, which
# must re-verify against what the candidate itself proposed).
def _stamp_guard(function_name: str) -> str:
    return f"""
CREATE FUNCTION v2.{function_name}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""


CREATE_DECISION_GUARD = """
CREATE FUNCTION v2.lifecycle_resolution_decision_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    candidate_company UUID;
BEGIN
    SELECT company_id INTO candidate_company FROM v2.lifecycle_event_candidate WHERE id = NEW.candidate_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RETURN NEW;   -- the foreign key reports the missing candidate
    END IF;
    IF NEW.decided_by_kind = 'rule' THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.lifecycle_resolution_decision: no lifecycle rule is enabled; only a human may decide',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM v2.lifecycle_resolution_decision d
                WHERE d.candidate_id = NEW.candidate_id AND d.decision_kind IN ('accept_lifecycle_event', 'reject_candidate')) THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.lifecycle_resolution_decision: the candidate already has a final resolution',
            ERRCODE = 'unique_violation', CONSTRAINT = 'uq_lrd_one_final';
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

# Each canonical fact table's guard re-verifies, at INSERT time, that: the decision is a human accept_lifecycle_event
# decision FOR THIS candidate, the candidate belongs to THIS company, and the accepted value EXACTLY matches what the
# candidate itself proposed (mirrors financing_event_stage's own STAGE_GUARD pattern) -- defense in depth beyond the
# application layer.
_FACT_REFUSAL = """
        RAISE EXCEPTION USING MESSAGE = 'v2.{table}: a fact is accepted only by a human accept_lifecycle_event decision, from the candidate that proposed it, with its exact value',
            ERRCODE = 'integrity_constraint_violation';"""


def _fact_guard(table: str, candidate_table: str, value_match: str) -> str:
    return f"""
CREATE FUNCTION v2.{table}_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    ok BOOLEAN;
BEGIN
    SELECT (d.decision_kind = 'accept_lifecycle_event' AND d.decided_by_kind = 'human' AND d.candidate_id = NEW.candidate_id
            AND c.company_id = NEW.company_id AND ({value_match}))
      INTO ok
      FROM v2.lifecycle_resolution_decision d
      JOIN v2.lifecycle_event_candidate c ON c.id = d.candidate_id
      JOIN v2.{candidate_table} f ON f.candidate_id = d.candidate_id
     WHERE d.id = NEW.resolution_decision_id;
    IF ok IS NOT TRUE THEN{_FACT_REFUSAL.format(table=table)}
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""


NAME_HISTORY_GUARD = _fact_guard(
    "company_name_history", "lifecycle_event_candidate_name_change",
    "f.new_name = NEW.new_name AND f.effective_precision IS NOT DISTINCT FROM NEW.effective_precision "
    "AND f.effective_start IS NOT DISTINCT FROM NEW.effective_start")
OPERATING_STATUS_GUARD = _fact_guard(
    "company_operating_status", "lifecycle_event_candidate_operating_status",
    "f.status = NEW.status AND f.as_of_precision IS NOT DISTINCT FROM NEW.as_of_precision "
    "AND f.as_of_start IS NOT DISTINCT FROM NEW.as_of_start")
ACQUISITION_GUARD = _fact_guard(
    "company_acquisition", "lifecycle_event_candidate_acquisition",
    "f.acquirer_name = NEW.acquirer_name AND f.acquirer_company_id IS NOT DISTINCT FROM NEW.acquirer_company_id "
    "AND f.transaction_date_precision IS NOT DISTINCT FROM NEW.transaction_date_precision "
    "AND f.transaction_date_start IS NOT DISTINCT FROM NEW.transaction_date_start")
SUCCESSOR_GUARD = _fact_guard(
    "company_successor_relationship", "lifecycle_event_candidate_successor",
    "f.related_entity_name = NEW.related_entity_name AND f.related_company_id IS NOT DISTINCT FROM NEW.related_company_id "
    "AND f.relationship_kind = NEW.relationship_kind")


def _triggers() -> list[str]:
    statements = ["CREATE TRIGGER trg_lifecycle_event_candidate_guard BEFORE INSERT ON v2.lifecycle_event_candidate "
                  "FOR EACH ROW EXECUTE FUNCTION v2.lifecycle_event_candidate_guard()"]
    for table in CANDIDATE_TABLES[1:]:
        fn = f"{table.replace('lifecycle_event_candidate_', 'lec_')}_stamp"
        statements.append(f"CREATE TRIGGER trg_{table}_guard BEFORE INSERT ON v2.{table} FOR EACH ROW EXECUTE FUNCTION v2.{fn}()")
    statements.append("CREATE TRIGGER trg_lifecycle_resolution_decision_guard BEFORE INSERT ON v2.lifecycle_resolution_decision "
                      "FOR EACH ROW EXECUTE FUNCTION v2.lifecycle_resolution_decision_guard()")
    for table in CANONICAL_TABLES:
        statements.append(f"CREATE TRIGGER trg_{table}_guard BEFORE INSERT ON v2.{table} FOR EACH ROW EXECUTE FUNCTION v2.{table}_guard()")
    for table in ALL_TABLES:
        statements += [
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON v2.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change()",
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON v2.{table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change()",
        ]
    return statements


COMMENTS = [
    "COMMENT ON TABLE v2.lifecycle_event_candidate IS 'UNTRUSTED lifecycle-event candidate about an already-canonical Company. Never creates or merges a Company.'",
    "COMMENT ON TABLE v2.lifecycle_resolution_decision IS 'Append-only decisions by a HUMAN (rule vocabulary exists, none enabled; never AI) that resolve an untrusted lifecycle candidate.'",
    "COMMENT ON TABLE v2.company_name_history IS 'A legal rename explicitly accepted by a human decision. company_name''s own canonical row is never rewritten; current name is a derived, latest-wins read.'",
    "COMMENT ON TABLE v2.company_operating_status IS 'Dated operating status explicitly accepted by a human decision. unknown is a legitimate accepted claim, not merely an absent row.'",
    "COMMENT ON TABLE v2.company_acquisition IS 'A documented relationship between distinct entities, explicitly accepted by a human decision. Never implies a status change by itself.'",
    "COMMENT ON TABLE v2.company_successor_relationship IS 'A possible or confirmed relationship between distinct entities, explicitly accepted by a human decision. Never transfers identifiers, financing, or classifications.'",
]

REFUSE_IF_HISTORY_EXISTS = f"""
DO $$
BEGIN
    IF {" OR ".join(f"EXISTS (SELECT 1 FROM v2.{t})" for t in ALL_TABLES)} THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0012: lifecycle candidate or resolution history exists',
            HINT = 'Lifecycle history is never discarded by a migration. Back it up and drop the tables by hand if you truly mean to.',
            ERRCODE = 'restrict_violation';
    END IF;
END
$$
"""

FUNCTIONS = (
    "company_successor_relationship_guard()", "company_acquisition_guard()", "company_operating_status_guard()",
    "company_name_history_guard()", "lifecycle_resolution_decision_guard()",
    "lec_successor_stamp()", "lec_acquisition_stamp()", "lec_operating_status_stamp()", "lec_name_change_stamp()",
    "lifecycle_event_candidate_guard()",
)


def upgrade() -> None:
    for ddl in (CREATE_CANDIDATE, CREATE_CANDIDATE_NAME_CHANGE, CREATE_CANDIDATE_OPERATING_STATUS,
               CREATE_CANDIDATE_ACQUISITION, CREATE_CANDIDATE_SUCCESSOR, CREATE_DECISION,
               CREATE_NAME_HISTORY, CREATE_OPERATING_STATUS, CREATE_ACQUISITION, CREATE_SUCCESSOR):
        op.execute(sa.text(ddl))
    for statement in CREATE_INDEXES.strip().split(";\n"):
        if statement.strip():
            op.execute(sa.text(statement))
    op.execute(sa.text(CREATE_CANDIDATE_GUARD))
    for fn_name in ("lec_name_change_stamp", "lec_operating_status_stamp", "lec_acquisition_stamp", "lec_successor_stamp"):
        op.execute(sa.text(_stamp_guard(fn_name)))
    op.execute(sa.text(CREATE_DECISION_GUARD))
    for function in (NAME_HISTORY_GUARD, OPERATING_STATUS_GUARD, ACQUISITION_GUARD, SUCCESSOR_GUARD):
        op.execute(sa.text(function))
    for statement in _triggers() + COMMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_HISTORY_EXISTS))
    for table in reversed(ALL_TABLES):
        op.execute(f"DROP TABLE v2.{table}")
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION v2.{function}")
