"""Create canonical v2.financing_event, v2.financing_resolution_decision and the accepted-fact tables

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-21

The financing resolution boundary: the ONLY path from an UNTRUSTED FinancingEventCandidate to a canonical FinancingEvent.

    FinancingEventCandidate [untrusted] -> FinancingResolutionDecision [human; rule vocabulary, none enabled] -> FinancingEvent [trusted]

AI may propose. AI may not decide, promote, merge or verify an amount. In the database:
  - decided_by_kind is CHECKed to 'rule' | 'human'; actor ids are bounded shapes and ids that name an AI are refused.
    A rule may only attach, and the guard trigger refuses EVERY rule decision: no financing rule is enabled (deduplicating
    financing events is harder than company identifiers; enabling one takes a new migration).
  - financing_event is a bare anchor (uuid + its ONE Company + created_at). A deferred constraint trigger refuses to commit
    an event without a create_event decision, so even direct SQL cannot mint a canonical event with no provenance.
  - The decision row IS the candidate -> event link: a candidate has at most one FINAL decision (partial unique index), so it
    can never belong to two events; many candidates (different observations/sources) may point at one event. Nothing is merged,
    copied or deleted, and candidates are never modified. A candidate may only resolve into an event of ITS OWN Company.
  - Canonical facts are separate append-only rows (stage, financing type, verified round amount, dates), each naming the
    human decision that accepted it and the exact candidate (fact) it came from, with the value re-verified against the candidate.
    One row per event per fact (per kind for dates): a canonical fact is never overwritten. verified_round_amount can come ONLY
    from a candidate's announced_round_amount (offering_amount / amount_sold can never become it).
  - All tables are append-only (UPDATE/DELETE/TRUNCATE rejected), created_at is the database's, FKs are ON DELETE RESTRICT.

Downgrade removes only these objects and REFUSES to run while any canonical financing or resolution history exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_FINAL = "('create_event', 'attach_to_event', 'reject_candidate')"
STATED_STAGES = "('pre_seed', 'seed', 'series_a', 'series_b', 'growth')"
STATED_TYPES = "('equity', 'convertible', 'debt', 'other')"

TABLES = ("financing_event", "financing_resolution_decision", "financing_event_stage", "financing_event_type",
          "financing_event_verified_round_amount", "financing_event_date")

CREATE_EVENT = """
CREATE TABLE v2.financing_event (
    id         UUID        NOT NULL DEFAULT gen_random_uuid(),
    company_id UUID        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_financing_event PRIMARY KEY (id),
    CONSTRAINT fk_fe_company_id FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT
)
"""

CREATE_DECISION = rf"""
CREATE TABLE v2.financing_resolution_decision (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY,
    candidate_id       BIGINT      NOT NULL,
    decision_kind      TEXT        NOT NULL,
    financing_event_id UUID        NULL,
    decided_by_kind    TEXT        NOT NULL,
    decided_by_id      TEXT        NOT NULL,
    reason_code        TEXT        NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_financing_resolution_decision PRIMARY KEY (id),
    CONSTRAINT fk_frd_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.financing_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT fk_frd_financing_event_id FOREIGN KEY (financing_event_id) REFERENCES v2.financing_event (id) ON DELETE RESTRICT,
    CONSTRAINT ck_frd_kind_allowed
        CHECK (decision_kind IN ('create_event', 'attach_to_event', 'reject_candidate', 'defer_candidate')),
    CONSTRAINT ck_frd_authority_allowed CHECK (decided_by_kind IN ('rule', 'human')),
    CONSTRAINT ck_frd_actor_human
        CHECK (decided_by_kind <> 'human'
               OR decided_by_id ~ '^[a-z][a-z0-9_]{{0,31}}:[A-Za-z0-9][A-Za-z0-9_.-]{{0,63}}$'),
    CONSTRAINT ck_frd_actor_rule
        CHECK (decided_by_kind <> 'rule'
               OR (decided_by_id ~ '^[a-z][a-z0-9_]{{0,62}}\.v[0-9]{{1,4}}$' AND decision_kind = 'attach_to_event')),
    CONSTRAINT ck_frd_actor_is_not_ai
        CHECK (decided_by_id !~* '(^|[^a-z])(ai|llm|gpt|chatgpt|openai|anthropic|claude|gemini|copilot|model|bot|agent)([^a-z]|$)'),
    CONSTRAINT ck_frd_event_matches_kind
        CHECK ((decision_kind IN ('create_event', 'attach_to_event')) = (financing_event_id IS NOT NULL)),
    CONSTRAINT ck_frd_reason_matches_kind
        CHECK ((decision_kind IN ('reject_candidate', 'defer_candidate')) = (reason_code IS NOT NULL)),
    CONSTRAINT ck_frd_reason_shape CHECK (reason_code IS NULL OR reason_code ~ '^[a-z][a-z0-9_]{{1,63}}$')
)
"""

CREATE_STAGE = f"""
CREATE TABLE v2.financing_event_stage (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY,
    financing_event_id     UUID        NOT NULL,
    stage                  TEXT        NOT NULL,
    resolution_decision_id BIGINT      NOT NULL,
    candidate_id           BIGINT      NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_financing_event_stage PRIMARY KEY (id),
    CONSTRAINT fk_fes_financing_event_id FOREIGN KEY (financing_event_id) REFERENCES v2.financing_event (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fes_resolution_decision_id FOREIGN KEY (resolution_decision_id) REFERENCES v2.financing_resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fes_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.financing_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_fes_one_per_event UNIQUE (financing_event_id),
    CONSTRAINT ck_fes_stage_stated CHECK (stage IN {STATED_STAGES})
)
"""

CREATE_TYPE = f"""
CREATE TABLE v2.financing_event_type (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY,
    financing_event_id     UUID        NOT NULL,
    financing_type         TEXT        NOT NULL,
    resolution_decision_id BIGINT      NOT NULL,
    candidate_id           BIGINT      NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_financing_event_type PRIMARY KEY (id),
    CONSTRAINT fk_fet_financing_event_id FOREIGN KEY (financing_event_id) REFERENCES v2.financing_event (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fet_resolution_decision_id FOREIGN KEY (resolution_decision_id) REFERENCES v2.financing_resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fet_candidate_id FOREIGN KEY (candidate_id) REFERENCES v2.financing_event_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_fet_one_per_event UNIQUE (financing_event_id),
    CONSTRAINT ck_fet_type_stated CHECK (financing_type IN {STATED_TYPES})
)
"""

CREATE_AMOUNT = r"""
CREATE TABLE v2.financing_event_verified_round_amount (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY,
    financing_event_id     UUID        NOT NULL,
    currency_code          TEXT        NOT NULL,
    amount_minor_units     BIGINT      NOT NULL,
    resolution_decision_id BIGINT      NOT NULL,
    candidate_amount_id    BIGINT      NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_financing_event_verified_round_amount PRIMARY KEY (id),
    CONSTRAINT fk_fev_financing_event_id FOREIGN KEY (financing_event_id) REFERENCES v2.financing_event (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fev_resolution_decision_id FOREIGN KEY (resolution_decision_id) REFERENCES v2.financing_resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fev_candidate_amount_id FOREIGN KEY (candidate_amount_id) REFERENCES v2.financing_event_candidate_amount (id) ON DELETE RESTRICT,
    CONSTRAINT uq_fev_one_per_event UNIQUE (financing_event_id),
    CONSTRAINT uq_fev_candidate_amount UNIQUE (candidate_amount_id),
    CONSTRAINT ck_fev_currency_shape CHECK (currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_fev_non_negative CHECK (amount_minor_units >= 0)
)
"""

CREATE_DATE = """
CREATE TABLE v2.financing_event_date (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY,
    financing_event_id     UUID        NOT NULL,
    date_kind              TEXT        NOT NULL,
    date_precision         TEXT        NOT NULL,
    date_start             TIMESTAMPTZ NOT NULL,
    resolution_decision_id BIGINT      NOT NULL,
    candidate_date_id      BIGINT      NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_financing_event_date PRIMARY KEY (id),
    CONSTRAINT fk_fed_financing_event_id FOREIGN KEY (financing_event_id) REFERENCES v2.financing_event (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fed_resolution_decision_id FOREIGN KEY (resolution_decision_id) REFERENCES v2.financing_resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fed_candidate_date_id FOREIGN KEY (candidate_date_id) REFERENCES v2.financing_event_candidate_date (id) ON DELETE RESTRICT,
    CONSTRAINT uq_fed_kind_per_event UNIQUE (financing_event_id, date_kind),
    CONSTRAINT uq_fed_candidate_date UNIQUE (candidate_date_id),
    CONSTRAINT ck_fed_kind_allowed CHECK (date_kind IN ('first_sale_date', 'filing_date', 'announcement_date')),
    CONSTRAINT ck_fed_precision_allowed CHECK (date_precision IN ('instant', 'day', 'month', 'year')),
    CONSTRAINT ck_fed_start_matches_precision
        CHECK (CASE date_precision
                 WHEN 'instant' THEN true
                 WHEN 'day'     THEN date_trunc('day',   date_start AT TIME ZONE 'UTC') = date_start AT TIME ZONE 'UTC'
                 WHEN 'month'   THEN date_trunc('month', date_start AT TIME ZONE 'UTC') = date_start AT TIME ZONE 'UTC'
                 WHEN 'year'    THEN date_trunc('year',  date_start AT TIME ZONE 'UTC') = date_start AT TIME ZONE 'UTC'
                 ELSE false END)
)
"""

CREATE_INDEXES = f"""
CREATE UNIQUE INDEX uq_frd_one_final ON v2.financing_resolution_decision (candidate_id)
    WHERE decision_kind IN {_FINAL};
CREATE UNIQUE INDEX uq_frd_one_create_per_event ON v2.financing_resolution_decision (financing_event_id)
    WHERE decision_kind = 'create_event'
"""

CREATE_EVENT_GUARD = """
CREATE FUNCTION v2.financing_event_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.id := gen_random_uuid();              -- identity is generated here, never supplied
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

CREATE_EVENT_PROVENANCE = """
CREATE FUNCTION v2.financing_event_requires_create_decision() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM v2.financing_resolution_decision d
                    WHERE d.financing_event_id = NEW.id AND d.decision_kind = 'create_event') THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.financing_event: an event needs a create_event decision',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NULL;
END
$$
"""

CREATE_DECISION_GUARD = """
CREATE FUNCTION v2.financing_resolution_decision_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    candidate_company UUID;
    event_company     UUID;
BEGIN
    -- Serialise decisions per candidate, then look: nothing may follow a final decision.
    SELECT company_id INTO candidate_company FROM v2.financing_event_candidate WHERE id = NEW.candidate_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RETURN NEW;   -- the foreign key reports the missing candidate
    END IF;
    IF NEW.decided_by_kind = 'rule' THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.financing_resolution_decision: no financing rule is enabled; only a human may decide',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM v2.financing_resolution_decision d
                WHERE d.candidate_id = NEW.candidate_id
                  AND d.decision_kind IN ('create_event', 'attach_to_event', 'reject_candidate')) THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.financing_resolution_decision: the candidate already has a final resolution',
            ERRCODE = 'unique_violation', CONSTRAINT = 'uq_frd_one_final';
    END IF;
    IF NEW.financing_event_id IS NOT NULL THEN
        SELECT company_id INTO event_company FROM v2.financing_event WHERE id = NEW.financing_event_id;
        IF NOT FOUND THEN
            RETURN NEW;   -- the foreign key reports the missing event
        END IF;
        IF event_company <> candidate_company THEN
            RAISE EXCEPTION USING MESSAGE = 'v2.financing_resolution_decision: a candidate can only resolve into an event of its own company',
                ERRCODE = 'integrity_constraint_violation';
        END IF;
        IF NEW.decision_kind = 'attach_to_event' AND NOT EXISTS (
               SELECT 1 FROM v2.financing_resolution_decision d
                WHERE d.financing_event_id = NEW.financing_event_id AND d.decision_kind = 'create_event') THEN
            RAISE EXCEPTION USING MESSAGE = 'v2.financing_resolution_decision: cannot attach to an event that has no create_event decision',
                ERRCODE = 'integrity_constraint_violation';
        END IF;
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

# The candidate a fact may come from: the one the (human create/attach) decision resolved into THIS event; else NULL.
CREATE_FACT_CANDIDATE_FN = """
CREATE FUNCTION v2.financing_fact_candidate(decision_id BIGINT, event_id UUID) RETURNS BIGINT
LANGUAGE sql STABLE AS $$
    SELECT d.candidate_id FROM v2.financing_resolution_decision d
     WHERE d.id = decision_id AND d.financing_event_id = event_id
       AND d.decided_by_kind = 'human' AND d.decision_kind IN ('create_event', 'attach_to_event')
$$
"""

_FACT_REFUSAL = """
        RAISE EXCEPTION USING MESSAGE = 'v2.{table}: a fact is accepted only by a human decision, from the candidate that resolved into this event, with its exact value',
            ERRCODE = 'integrity_constraint_violation';"""


def _fact_guard(table: str, condition: str) -> str:
    return f"""
CREATE FUNCTION v2.{table}_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    resolved_candidate BIGINT;
BEGIN
    resolved_candidate := v2.financing_fact_candidate(NEW.resolution_decision_id, NEW.financing_event_id);
    IF resolved_candidate IS NULL OR NOT ({condition}) THEN{_FACT_REFUSAL.format(table=table)}
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""


STAGE_GUARD = _fact_guard(
    "financing_event_stage",
    "NEW.candidate_id = resolved_candidate AND EXISTS (SELECT 1 FROM v2.financing_event_candidate c WHERE c.id = NEW.candidate_id AND c.stage = NEW.stage)")
TYPE_GUARD = _fact_guard(
    "financing_event_type",
    "NEW.candidate_id = resolved_candidate AND EXISTS (SELECT 1 FROM v2.financing_event_candidate c WHERE c.id = NEW.candidate_id AND c.financing_type = NEW.financing_type)")
AMOUNT_GUARD = _fact_guard(
    "financing_event_verified_round_amount",
    "EXISTS (SELECT 1 FROM v2.financing_event_candidate_amount a WHERE a.id = NEW.candidate_amount_id AND a.candidate_id = resolved_candidate "
    "AND a.amount_semantics = 'announced_round_amount' AND a.currency_code = NEW.currency_code AND a.amount_minor_units = NEW.amount_minor_units)")
DATE_GUARD = _fact_guard(
    "financing_event_date",
    "EXISTS (SELECT 1 FROM v2.financing_event_candidate_date a WHERE a.id = NEW.candidate_date_id AND a.candidate_id = resolved_candidate "
    "AND a.date_kind = NEW.date_kind AND a.date_precision = NEW.date_precision AND a.date_start = NEW.date_start)")


def _triggers() -> list[str]:
    statements = [
        "CREATE TRIGGER trg_financing_event_guard BEFORE INSERT ON v2.financing_event FOR EACH ROW EXECUTE FUNCTION v2.financing_event_guard()",
        "CREATE CONSTRAINT TRIGGER trg_financing_event_requires_create_decision AFTER INSERT ON v2.financing_event "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION v2.financing_event_requires_create_decision()",
    ]
    for table in TABLES[1:]:
        statements.append(f"CREATE TRIGGER trg_{table}_guard BEFORE INSERT ON v2.{table} FOR EACH ROW EXECUTE FUNCTION v2.{table}_guard()")
    for table in TABLES:
        statements += [
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON v2.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change()",
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON v2.{table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change()",
        ]
    return statements


COMMENTS = [
    "COMMENT ON TABLE v2.financing_event IS 'TRUSTED canonical financing-event identity anchor for ONE company. Created only through a create_event FinancingResolutionDecision.'",
    "COMMENT ON TABLE v2.financing_resolution_decision IS 'Append-only decisions by a HUMAN (a rule vocabulary exists, none is enabled; never AI) that resolve an untrusted financing-event candidate.'",
    "COMMENT ON TABLE v2.financing_event_stage IS 'Canonical stage explicitly accepted by a human decision from one candidate. Never inferred; never overwritten.'",
    "COMMENT ON TABLE v2.financing_event_type IS 'Canonical financing type explicitly accepted by a human decision from one candidate. Never inferred; never overwritten.'",
    "COMMENT ON TABLE v2.financing_event_verified_round_amount IS 'Round amount VentureGPS explicitly accepted as canonical, only from a candidate announced_round_amount, only by a human decision.'",
    "COMMENT ON TABLE v2.financing_event_date IS 'Canonical semantic date explicitly accepted by a human decision from one candidate date, with its precision.'",
]

REFUSE_IF_HISTORY_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.financing_event) OR EXISTS (SELECT 1 FROM v2.financing_resolution_decision)
       OR EXISTS (SELECT 1 FROM v2.financing_event_stage) OR EXISTS (SELECT 1 FROM v2.financing_event_type)
       OR EXISTS (SELECT 1 FROM v2.financing_event_verified_round_amount) OR EXISTS (SELECT 1 FROM v2.financing_event_date) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0009: canonical financing or resolution history exists',
            HINT = 'Canonical financing history is never discarded by a migration. Back it up and drop the tables by hand if you truly mean to.',
            ERRCODE = 'restrict_violation';
    END IF;
END
$$
"""

FUNCTIONS = ("financing_event_date_guard()", "financing_event_verified_round_amount_guard()", "financing_event_type_guard()",
             "financing_event_stage_guard()", "financing_fact_candidate(bigint, uuid)", "financing_resolution_decision_guard()",
             "financing_event_requires_create_decision()", "financing_event_guard()")


def _execute_each(script: str) -> None:
    for statement in script.split(";\n"):
        if statement.strip():
            op.execute(sa.text(statement))


def upgrade() -> None:
    for ddl in (CREATE_EVENT, CREATE_DECISION, CREATE_STAGE, CREATE_TYPE, CREATE_AMOUNT, CREATE_DATE):
        op.execute(sa.text(ddl))
    _execute_each(CREATE_INDEXES)
    for function in (CREATE_EVENT_GUARD, CREATE_EVENT_PROVENANCE, CREATE_DECISION_GUARD, CREATE_FACT_CANDIDATE_FN,
                     STAGE_GUARD, TYPE_GUARD, AMOUNT_GUARD, DATE_GUARD):
        op.execute(sa.text(function))
    for statement in _triggers() + COMMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_HISTORY_EXISTS))
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE v2.{table}")
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION v2.{function}")
