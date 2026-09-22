"""Create v2.taxonomy_version, v2.market and v2.company_market_classification

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-22

The minimum market/taxonomy structure needed to attribute canonical FinancingEvents to a canonical Market and
calculate deterministic Capital metrics.

    Canonical Company -> versioned Company/Market classification -> canonical FinancingEvent -> Capital metrics

- **`v2.taxonomy_version`**: a registered version id (e.g. `venturegps_taxonomy.v1`). Classification always names
  the version it was made under; a methodology change is a NEW version with new rows, never a silent rewrite of an
  old classification.
- **`v2.market`**: a bare taxonomy-node identity -- `id UUID` (database-generated), a unique routing `slug`, and a
  `display_name` (NOT identity; duplicates across different Markets are allowed). No description/icon/score/summary
  fields. Registered directly (like `v2.source`); it is reference/taxonomy data, not evidence-derived truth, so it
  is not behind a candidate/resolution boundary.
- **`v2.company_market_classification`**: the explicit, append-only, authoritative fact "under this taxonomy
  version, this Company was classified into this Market with this role, by this authority." `decided_by_kind` is
  CHECKed to `rule | human`; every `rule` decision is refused by the insert trigger, unconditionally -- no
  classification rule is safe/enabled yet (same company/name/sector guess is not sufficient identity). At most one
  `primary` classification per (Company, taxonomy version) (partial unique index: PRIMARY owns Capital
  attribution, so a Company can never have two); a Company may hold any number of `secondary` classifications, but
  never the same (Company, Market, taxonomy version) twice.

All three tables are append-only (UPDATE/DELETE/TRUNCATE rejected), `created_at` is the database's clock, and FKs
are `ON DELETE RESTRICT`.

Downgrade removes only these objects and REFUSES to run while any taxonomy version, market or classification exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TABLES = ("taxonomy_version", "market", "company_market_classification")

CREATE_TAXONOMY_VERSION = r"""
CREATE TABLE v2.taxonomy_version (
    taxonomy_version TEXT        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_taxonomy_version PRIMARY KEY (taxonomy_version),
    CONSTRAINT ck_taxonomy_version_shape CHECK (taxonomy_version ~ '^[a-z][a-z0-9_]{0,63}\.v[1-9][0-9]{0,5}$')
)
"""

CREATE_MARKET = r"""
CREATE TABLE v2.market (
    id           UUID        NOT NULL DEFAULT gen_random_uuid(),
    slug         TEXT        NOT NULL,
    display_name TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_market PRIMARY KEY (id),
    CONSTRAINT uq_market_slug UNIQUE (slug),
    CONSTRAINT ck_market_slug_shape CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) <= 80),
    CONSTRAINT ck_market_display_name_valid
        CHECK (display_name = btrim(display_name) AND char_length(display_name) BETWEEN 1 AND 200
               AND display_name !~ '[\x01-\x1f\x7f]')
)
"""

CREATE_CLASSIFICATION = r"""
CREATE TABLE v2.company_market_classification (
    id               BIGINT GENERATED ALWAYS AS IDENTITY,
    company_id       UUID        NOT NULL,
    market_id        UUID        NOT NULL,
    taxonomy_version TEXT        NOT NULL,
    role             TEXT        NOT NULL,
    decided_by_kind  TEXT        NOT NULL,
    decided_by_id    TEXT        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_company_market_classification PRIMARY KEY (id),
    CONSTRAINT fk_cmc_company_id FOREIGN KEY (company_id) REFERENCES v2.company (id) ON DELETE RESTRICT,
    CONSTRAINT fk_cmc_market_id FOREIGN KEY (market_id) REFERENCES v2.market (id) ON DELETE RESTRICT,
    CONSTRAINT fk_cmc_taxonomy_version FOREIGN KEY (taxonomy_version) REFERENCES v2.taxonomy_version (taxonomy_version) ON DELETE RESTRICT,
    CONSTRAINT uq_cmc_company_market_version UNIQUE (company_id, market_id, taxonomy_version),
    CONSTRAINT ck_cmc_role_allowed CHECK (role IN ('primary', 'secondary')),
    CONSTRAINT ck_cmc_authority_allowed CHECK (decided_by_kind IN ('rule', 'human')),
    CONSTRAINT ck_cmc_actor_human
        CHECK (decided_by_kind <> 'human'
               OR decided_by_id ~ '^[a-z][a-z0-9_]{0,31}:[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'),
    CONSTRAINT ck_cmc_actor_rule
        CHECK (decided_by_kind <> 'rule'
               OR decided_by_id ~ '^[a-z][a-z0-9_]{0,62}\.v[0-9]{1,4}$'),
    CONSTRAINT ck_cmc_actor_is_not_ai
        CHECK (decided_by_id !~* '(^|[^a-z])(ai|llm|gpt|chatgpt|openai|anthropic|claude|gemini|copilot|model|bot|agent)([^a-z]|$)')
)
"""

CREATE_INDEXES = """
CREATE UNIQUE INDEX uq_cmc_one_primary_per_company_version ON v2.company_market_classification (company_id, taxonomy_version)
    WHERE role = 'primary'
"""

CREATE_CLASSIFICATION_GUARD = """
CREATE FUNCTION v2.company_market_classification_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.decided_by_kind = 'rule' THEN
        RAISE EXCEPTION USING MESSAGE = 'v2.company_market_classification: no classification rule is enabled; only a human may classify',
            ERRCODE = 'integrity_constraint_violation';
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

CREATE_MARKET_GUARD = """
CREATE FUNCTION v2.market_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.id := gen_random_uuid();               -- identity is generated here, never supplied
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""

CREATE_TAXONOMY_VERSION_STAMP = """
CREATE FUNCTION v2.taxonomy_version_stamp() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END
$$
"""


def _triggers() -> list[str]:
    statements = [
        "CREATE TRIGGER trg_taxonomy_version_stamp BEFORE INSERT ON v2.taxonomy_version FOR EACH ROW EXECUTE FUNCTION v2.taxonomy_version_stamp()",
        "CREATE TRIGGER trg_market_guard BEFORE INSERT ON v2.market FOR EACH ROW EXECUTE FUNCTION v2.market_guard()",
        "CREATE TRIGGER trg_company_market_classification_guard BEFORE INSERT ON v2.company_market_classification "
        "FOR EACH ROW EXECUTE FUNCTION v2.company_market_classification_guard()",
    ]
    for table in TABLES:
        statements += [
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON v2.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION v2.forbid_evidence_change()",
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON v2.{table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION v2.forbid_evidence_change()",
        ]
    return statements


COMMENTS = [
    "COMMENT ON TABLE v2.taxonomy_version IS 'Registered VentureGPS taxonomy versions. Classification always names one; a methodology change is a new version, never a silent rewrite.'",
    "COMMENT ON TABLE v2.market IS 'A bare canonical taxonomy-node identity (not a profile): an opaque id, a routing slug, and a display name.'",
    "COMMENT ON TABLE v2.company_market_classification IS 'Append-only, authoritative Company -> Market classification by a HUMAN (never AI), scoped to a taxonomy version. PRIMARY owns Capital attribution; SECONDARY never does.'",
]

REFUSE_IF_HISTORY_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM v2.taxonomy_version) OR EXISTS (SELECT 1 FROM v2.market)
       OR EXISTS (SELECT 1 FROM v2.company_market_classification) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'refusing to downgrade 0010: taxonomy version, market or classification history exists',
            HINT = 'Taxonomy/market/classification history is never discarded by a migration. Back it up and drop the tables by hand if you truly mean to.',
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
    for ddl in (CREATE_TAXONOMY_VERSION, CREATE_MARKET, CREATE_CLASSIFICATION):
        op.execute(sa.text(ddl))
    _execute_each(CREATE_INDEXES)
    for function in (CREATE_TAXONOMY_VERSION_STAMP, CREATE_MARKET_GUARD, CREATE_CLASSIFICATION_GUARD):
        op.execute(sa.text(function))
    for statement in _triggers() + COMMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text(REFUSE_IF_HISTORY_EXISTS))
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE v2.{table}")
    for function in ("company_market_classification_guard()", "market_guard()", "taxonomy_version_stamp()"):
        op.execute(f"DROP FUNCTION v2.{function}")
