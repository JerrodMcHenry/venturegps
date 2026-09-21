"""Create v2.resolution_decision, v2.company, v2.company_name and v2.company_identifier

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-21

The resolution boundary: the ONLY path from an UNTRUSTED CompanyCandidate to
canonical Company identity.

    CompanyCandidate [untrusted] -> ResolutionDecision [rule or human] -> Company [trusted]

AI may propose. AI may not decide. AI may not promote. In the database:
  - resolution_decision.decided_by_kind is CHECKed to 'rule' | 'human'. There is
    no third value, no enum member and no table that could carry one; actor ids
    are bounded shapes and ids that name an AI system are refused.
  - A rule may only decide attach_to_company, and the insert trigger re-verifies
    that the candidate's identifiers exactly match ONE company's identifiers.
  - Company is a bare anchor (uuid + created_at). The database generates the id
    and the clock. A deferred constraint trigger refuses to commit a Company that
    lacks a create_company decision and a canonical name, so even direct SQL cannot
    mint a Company with no provenance.
  - Canonical names and identifiers are accepted facts: each names the decision
    that accepted it and the candidate (identifier) it came from. They can only be
    accepted by a HUMAN decision (a rule accepts no new facts).
  - v2.normalize_company_identifier() is the SQL twin of the Python normalization
    policy (app.v2.domain.company); identifiers are stored only in normalized form.
  - A canonical (type, value) identifier belongs to one Company, ever
    (uq_company_identifier_value). There is no merge.
  - A candidate has at most one FINAL decision (create/attach/reject); defer is not
    final; nothing may be decided after a final decision (per-candidate row lock,
    then check). Resolution state is derived; candidates stay immutable.
  - All four tables are append-only (UPDATE/DELETE/TRUNCATE rejected), have
    database-owned created_at, and FKs are ON DELETE RESTRICT.

Downgrade removes only these objects and REFUSES to run while any company or
resolution history exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_FINAL = "('create_company', 'attach_to_company', 'reject_candidate')"

CREATE_COMPANY = r"""
CREATE TABLE v2.company (
    id         UUID        NOT NULL DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_company PRIMARY KEY (id)
)
"""

CREATE_DECISION = r"""
CREATE TABLE v2.resolution_decision (
    id             BIGINT GENERATED ALWAYS AS IDENTITY,
    candidate_id   BIGINT      NOT NULL,
    decision_kind  TEXT        NOT NULL,
    company_id     UUID        NULL,
    decided_by_kind TEXT       NOT NULL,
    decided_by_id  TEXT        NOT NULL,
    reason_code    TEXT        NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_resolution_decision PRIMARY KEY (id),
    CONSTRAINT fk_resolution_decision_candidate_id_company_candidate
        FOREIGN KEY (candidate_id) REFERENCES v2.company_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT fk_resolution_decision_company_id_company
        FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT ck_resolution_decision_kind_allowed
        CHECK (decision_kind IN ('create_company', 'attach_to_company', 'reject_candidate', 'defer_candidate')),
    CONSTRAINT ck_resolution_decision_authority_allowed CHECK (decided_by_kind IN ('rule', 'human')),
    CONSTRAINT ck_resolution_decision_actor_human
        CHECK (decided_by_kind <> 'human'
               OR decided_by_id ~ '^[a-z][a-z0-9_]{0,31}:[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
    CONSTRAINT ck_resolution_decision_actor_rule
        CHECK (decided_by_kind <> 'rule'
               OR (decided_by_id ~ '^[a-z][a-z0-9_]{0,62}\.v[0-9]{1,4}$' AND decision_kind = 'attach_to_company')),
    CONSTRAINT ck_resolution_decision_actor_is_not_ai
        CHECK (decided_by_id !~* '(^|[^a-z])(ai|llm|gpt|chatgpt|openai|anthropic|claude|gemini|copilot|model|bot|agent)([^a-z]|$)'),
    CONSTRAINT ck_resolution_decision_company_matches_kind
        CHECK ((decision_kind IN ('create_company', 'attach_to_company')) = (company_id IS NOT NULL)),
    CONSTRAINT ck_resolution_decision_reason_matches_kind
        CHECK ((decision_kind IN ('reject_candidate', 'defer_candidate')) = (reason_code IS NOT NULL)),
    CONSTRAINT ck_resolution_decision_reason_shape
        CHECK (reason_code IS NULL OR reason_code ~ '^[a-z][a-z0-9_]{1,63}$')
)
"""

CREATE_NAME = r"""
CREATE TABLE v2.company_name (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY,
    company_id             UUID        NOT NULL,
    name                   TEXT        NOT NULL,
    name_role              TEXT        NOT NULL,
    resolution_decision_id BIGINT      NOT NULL,
    candidate_id           BIGINT      NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_company_name PRIMARY KEY (id),
    CONSTRAINT fk_company_name_company_id_company
        FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT fk_company_name_resolution_decision_id_resolution_decision
        FOREIGN KEY (resolution_decision_id) REFERENCES v2.resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_company_name_candidate_id_company_candidate
        FOREIGN KEY (candidate_id) REFERENCES v2.company_candidate (id) ON DELETE RESTRICT,
    CONSTRAINT uq_company_name_company_name UNIQUE (company_id, name),
    CONSTRAINT ck_company_name_role_allowed CHECK (name_role IN ('canonical', 'alias')),
    CONSTRAINT ck_company_name_valid
        CHECK (name = btrim(name) AND char_length(name) BETWEEN 1 AND 300 AND name !~ '[\x01-\x1f\x7f]')
)
"""

CREATE_IDENTIFIER = r"""
CREATE TABLE v2.company_identifier (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY,
    company_id               UUID        NOT NULL,
    identifier_type          TEXT        NOT NULL,
    identifier_value         TEXT        NOT NULL,
    resolution_decision_id   BIGINT      NOT NULL,
    candidate_identifier_id  BIGINT      NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_company_identifier PRIMARY KEY (id),
    CONSTRAINT fk_company_identifier_company_id_company
        FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT fk_company_identifier_resolution_decision_id_resolution_decision
        FOREIGN KEY (resolution_decision_id) REFERENCES v2.resolution_decision (id) ON DELETE RESTRICT,
    CONSTRAINT fk_company_identifier_candidate_identifier_id_company_candidate_identifier
        FOREIGN KEY (candidate_identifier_id) REFERENCES v2.company_candidate_identifier (id) ON DELETE RESTRICT,
    CONSTRAINT uq_company_identifier_value UNIQUE (identifier_type, identifier_value),
    CONSTRAINT uq_company_identifier_candidate_identifier UNIQUE (candidate_identifier_id),
    CONSTRAINT ck_company_identifier_type_allowed CHECK (identifier_type IN ('domain', 'website_url')),
    CONSTRAINT ck_company_identifier_value_is_normalized
        CHECK (identifier_value = v2.normalize_company_identifier(identifier_type, identifier_value))
)
"""

# The unique partial indexes that make contradictory resolutions unrepresentable.
CREATE_INDEXES = f"""
CREATE UNIQUE INDEX uq_resolution_decision_one_final ON v2.resolution_decision (candidate_id)
    WHERE decision_kind IN {_FINAL};
CREATE UNIQUE INDEX uq_resolution_decision_one_create_per_company ON v2.resolution_decision (company_id)
    WHERE decision_kind = 'create_company';
CREATE UNIQUE INDEX uq_company_name_one_canonical ON v2.company_name (company_id)
    WHERE name_role = 'canonical'
"""

CREATE_NORMALIZE = r"""
CREATE FUNCTION v2.normalize_company_identifier(identifier_type TEXT, raw_value TEXT) RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    v      TEXT;
    m      TEXT[];
    port   INTEGER;
    netloc TEXT;
    scheme TEXT;
    host   TEXT;
    path   TEXT;
    query  TEXT;
BEGIN
    IF raw_value IS NULL THEN
        RETURN NULL;
    END IF;
    IF identifier_type = 'domain' THEN
        v := regexp_replace(lower(raw_value), '\.$', '');
        IF v ~ '^www\.[^.]+\..+' THEN
            v := substr(v, 5);
        END IF;
        RETURN v;
    ELSIF identifier_type = 'website_url' THEN
        m := regexp_match(raw_value, '^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#:@\[\]]+)(?::([0-9]{1,5}))?([^?#]*)(?:\?([^#]*))?(?:#.*)?$');
        IF m IS NULL THEN
            RETURN NULL;
        END IF;
        scheme := lower(m[1]);
        host := lower(m[2]);
        IF scheme NOT IN ('http', 'https') THEN
            RETURN NULL;
        END IF;
        netloc := host;
        IF m[3] IS NOT NULL THEN
            port := m[3]::INTEGER;
            IF port > 65535 THEN
                RETURN NULL;
            END IF;
            IF NOT ((scheme = 'http' AND port = 80) OR (scheme = 'https' AND port = 443)) THEN
                netloc := host || ':' || port::TEXT;
            END IF;
        END IF;
        path := CASE WHEN m[4] = '' THEN '/' ELSE m[4] END;
        query := CASE WHEN m[5] IS NULL OR m[5] = '' THEN '' ELSE '?' || m[5] END;
        RETURN scheme || '://' || netloc || path || query;
    END IF;
    RETURN NULL;
END
$$
"""

CREATE_COMPANY_GUARD = r"""
CREATE FUNCTION v2.company_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.id := gen_random_uuid();              -- identity is generated here, never supplied
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

CREATE_COMPANY_PROVENANCE = r"""
CREATE FUNCTION v2.company_requires_provenance() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM v2.resolution_decision d
                    WHERE d.company_id = NEW.id AND d.decision_kind = 'create_company')
       OR NOT EXISTS (SELECT 1 FROM v2.company_name n
                       WHERE n.company_id = NEW.id AND n.name_role = 'canonical') THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company: a company needs a create_company decision and a canonical name',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NULL;
END
$$
"""

CREATE_DECISION_GUARD = r"""
CREATE FUNCTION v2.resolution_decision_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    matched UUID[];
BEGIN
    -- Serialise decisions per candidate, then look: nothing may follow a final decision.
    PERFORM 1 FROM v2.company_candidate WHERE id = NEW.candidate_id FOR NO KEY UPDATE;
    IF NOT FOUND THEN
        RETURN NEW;   -- the foreign key reports the missing candidate
    END IF;
    IF EXISTS (SELECT 1 FROM v2.resolution_decision d
                WHERE d.candidate_id = NEW.candidate_id
                  AND d.decision_kind IN ('create_company', 'attach_to_company', 'reject_candidate')) THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.resolution_decision: the candidate already has a final resolution',
            ERRCODE = 'unique_violation', CONSTRAINT = 'uq_resolution_decision_one_final';
    END IF;
    IF NEW.decided_by_kind = 'rule' THEN
        -- A rule attaches only on an exact identifier match with exactly ONE company.
        SELECT array_agg(DISTINCT x.company_id) INTO matched
          FROM v2.company_candidate_identifier ci
          JOIN v2.company_identifier x
            ON x.identifier_type = ci.identifier_type
           AND x.identifier_value = v2.normalize_company_identifier(ci.identifier_type, ci.identifier_value)
         WHERE ci.candidate_id = NEW.candidate_id;
        IF matched IS NULL OR array_length(matched, 1) <> 1 OR matched[1] IS DISTINCT FROM NEW.company_id THEN
            RAISE EXCEPTION USING MESSAGE = 'v2.resolution_decision: a rule may only attach on an exact match with exactly one company',
                ERRCODE = 'integrity_constraint_violation';
        END IF;
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

CREATE_NAME_GUARD = r"""
CREATE FUNCTION v2.company_name_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    d v2.resolution_decision%ROWTYPE;
    proposed TEXT;
BEGIN
    SELECT * INTO d FROM v2.resolution_decision WHERE id = NEW.resolution_decision_id;
    IF NOT FOUND THEN
        RETURN NEW;   -- the foreign key reports the missing decision
    END IF;
    SELECT proposed_name INTO proposed FROM v2.company_candidate WHERE id = NEW.candidate_id;
    IF d.decided_by_kind <> 'human'
       OR d.company_id IS DISTINCT FROM NEW.company_id
       OR d.candidate_id <> NEW.candidate_id
       OR NOT ((NEW.name_role = 'canonical' AND d.decision_kind = 'create_company')
            OR (NEW.name_role = 'alias' AND d.decision_kind = 'attach_to_company'))
       OR proposed IS DISTINCT FROM NEW.name THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company_name: a name is accepted only by a human decision on the candidate that proposed it',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

CREATE_IDENTIFIER_GUARD = r"""
CREATE FUNCTION v2.company_identifier_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    d  v2.resolution_decision%ROWTYPE;
    ci v2.company_candidate_identifier%ROWTYPE;
BEGIN
    SELECT * INTO d FROM v2.resolution_decision WHERE id = NEW.resolution_decision_id;
    IF NOT FOUND THEN
        RETURN NEW;
    END IF;
    SELECT * INTO ci FROM v2.company_candidate_identifier WHERE id = NEW.candidate_identifier_id;
    IF NOT FOUND THEN
        RETURN NEW;
    END IF;
    IF d.decided_by_kind <> 'human'
       OR d.decision_kind NOT IN ('create_company', 'attach_to_company')
       OR d.company_id IS DISTINCT FROM NEW.company_id
       OR d.candidate_id <> ci.candidate_id
       OR ci.identifier_type <> NEW.identifier_type
       OR v2.normalize_company_identifier(ci.identifier_type, ci.identifier_value) IS DISTINCT FROM NEW.identifier_value THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company_identifier: an identifier is accepted only by a human decision, from the candidate identifier that proposed it, in normalized form',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

CREATE_TRIGGERS = """
CREATE TRIGGER trg_company_guard
    BEFORE INSERT ON v2.company
    FOR EACH ROW EXECUTE FUNCTION v2.company_guard();
CREATE CONSTRAINT TRIGGER trg_company_requires_provenance
    AFTER INSERT ON v2.company
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION v2.company_requires_provenance();
CREATE TRIGGER trg_resolution_decision_guard
    BEFORE INSERT ON v2.resolution_decision
    FOR EACH ROW EXECUTE FUNCTION v2.resolution_decision_guard();
CREATE TRIGGER trg_company_name_guard
    BEFORE INSERT ON v2.company_name
    FOR EACH ROW EXECUTE FUNCTION v2.company_name_guard();
CREATE TRIGGER trg_company_identifier_guard
    BEFORE INSERT ON v2.company_identifier
    FOR EACH ROW EXECUTE FUNCTION v2.company_identifier_guard();
CREATE TRIGGER trg_company_append_only
    BEFORE UPDATE OR DELETE ON v2.company
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_company_no_truncate
    BEFORE TRUNCATE ON v2.company
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_resolution_decision_append_only
    BEFORE UPDATE OR DELETE ON v2.resolution_decision
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_resolution_decision_no_truncate
    BEFORE TRUNCATE ON v2.resolution_decision
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_company_name_append_only
    BEFORE UPDATE OR DELETE ON v2.company_name
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_company_name_no_truncate
    BEFORE TRUNCATE ON v2.company_name
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_company_identifier_append_only
    BEFORE UPDATE OR DELETE ON v2.company_identifier
    FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change();
CREATE TRIGGER trg_company_identifier_no_truncate
    BEFORE TRUNCATE ON v2.company_identifier
    FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change()
"""

COMMENTS = """
COMMENT ON TABLE v2.company IS
    'TRUSTED canonical company identity anchor: an opaque id and a creation time. Created only through a create_company ResolutionDecision.';
COMMENT ON TABLE v2.resolution_decision IS
    'Append-only decisions by a RULE or a HUMAN (never AI) that resolve an untrusted company candidate.';
COMMENT ON TABLE v2.company_name IS
    'Canonical/alias company names accepted by a human resolution decision, with candidate provenance.';
COMMENT ON TABLE v2.company_identifier IS
    'Canonical normalized company identifiers accepted by a human resolution decision, with candidate provenance.'
"""

REFUSE_IF_HISTORY_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.company) OR EXISTS (SELECT 1 FROM v2.resolution_decision)
       OR EXISTS (SELECT 1 FROM v2.company_name) OR EXISTS (SELECT 1 FROM v2.company_identifier) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0007: canonical company or resolution history exists',
            HINT = 'Canonical identity and resolution history are never discarded by a migration. Back it up and drop the tables by hand if you truly mean to.',
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
    op.execute(sa.text(CREATE_NORMALIZE))
    op.execute(sa.text(CREATE_COMPANY))
    op.execute(sa.text(CREATE_DECISION))
    op.execute(sa.text(CREATE_NAME))
    op.execute(sa.text(CREATE_IDENTIFIER))
    _execute_each(CREATE_INDEXES)
    for function in (CREATE_COMPANY_GUARD, CREATE_COMPANY_PROVENANCE, CREATE_DECISION_GUARD,
                     CREATE_NAME_GUARD, CREATE_IDENTIFIER_GUARD):
        op.execute(sa.text(function))
    _execute_each(CREATE_TRIGGERS)
    _execute_each(COMMENTS)


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_HISTORY_EXISTS))
    op.execute("DROP TABLE v2.company_identifier")
    op.execute("DROP TABLE v2.company_name")
    op.execute("DROP TABLE v2.resolution_decision")
    op.execute("DROP TABLE v2.company")
    for function in ("company_identifier_guard()", "company_name_guard()", "resolution_decision_guard()",
                     "company_requires_provenance()", "company_guard()",
                     "normalize_company_identifier(text, text)"):
        op.execute(f"DROP FUNCTION v2.{function}")
