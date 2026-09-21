"""Create v2.source

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-21

The persisted form of the pure Source model (app/v2/domain/source.py).

Design notes (see docs/v2/DATABASE_MIGRATIONS.md):

- Enumerated vocabularies are TEXT + named CHECK constraints, not PostgreSQL
  ENUM types: extending a vocabulary is one constraint swap in an ordinary
  transactional migration, and values can be retired without the ENUM
  limitations (ADD VALUE restrictions, no value removal).
- Identity = generated id + the unique source_key. Name and URL are data.
- IMMUTABLE after insert: id, source_key, source_type, collection_method,
  created_at. MUTABLE: source_name, source_url, is_active. A trigger enforces
  this for every writer, including direct SQL.
- The trigger also owns the timestamps: created_at is always the database's
  clock, and updated_at moves only when a mutable field actually changes.
- CHECKs guard integrity invariants and are deliberately a subset of the
  domain rules (the domain validators stay authoritative).
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SOURCE_TYPES = (
    "government_regulatory", "first_party_company", "investor", "job_platform",
    "research", "patent", "open_source", "media_news", "other",
)
COLLECTION_METHODS = ("manual_upload", "http_fetch", "api", "feed", "bulk_file")


def _in_list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


CREATE_TABLE = f"""
CREATE TABLE v2.source (
    id                BIGINT GENERATED ALWAYS AS IDENTITY,
    source_key        TEXT        NOT NULL,
    source_name       TEXT        NOT NULL,
    source_type       TEXT        NOT NULL,
    collection_method TEXT        NOT NULL,
    source_url        TEXT,
    is_active         BOOLEAN     NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_source PRIMARY KEY (id),
    CONSTRAINT uq_source_source_key UNIQUE (source_key),
    CONSTRAINT ck_source_source_key_shape
        CHECK (source_key ~ '^[a-z][a-z0-9_]{{1,63}}$'),
    CONSTRAINT ck_source_source_name_valid
        CHECK (source_name = btrim(source_name)
               AND char_length(source_name) BETWEEN 1 AND 200
               AND source_name !~ '[\\x01-\\x1f\\x7f]'),
    CONSTRAINT ck_source_source_type_allowed
        CHECK (source_type IN ({_in_list(SOURCE_TYPES)})),
    CONSTRAINT ck_source_collection_method_allowed
        CHECK (collection_method IN ({_in_list(COLLECTION_METHODS)})),
    CONSTRAINT ck_source_source_url_valid
        CHECK (source_url IS NULL
               OR (char_length(source_url) <= 2048
                   AND source_url ~ '^[\\x21-\\x5b\\x5d-\\x7e]+$'
                   AND source_url ~* '^https?://[^/?#]'
                   AND source_url !~* '^https?://[^/?#]*@')),
    CONSTRAINT ck_source_updated_not_before_created
        CHECK (updated_at >= created_at)
)
"""

CREATE_FUNCTION = """
CREATE FUNCTION v2.source_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- Timestamps are the database's, whatever the writer supplied.
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
        NEW.updated_at := OLD.updated_at;  -- a no-op update is not a modification
    END IF;
    RETURN NEW;
END
$$
"""

CREATE_TRIGGER = """
CREATE TRIGGER trg_source_guard
    BEFORE INSERT OR UPDATE ON v2.source
    FOR EACH ROW EXECUTE FUNCTION v2.source_guard()
"""


def upgrade() -> None:
    op.execute(sa.text(CREATE_TABLE))
    op.execute(sa.text(CREATE_FUNCTION))
    op.execute(sa.text(CREATE_TRIGGER))


def downgrade() -> None:
    op.execute("DROP TABLE v2.source")  # drops its trigger and identity sequence too
    op.execute("DROP FUNCTION v2.source_guard()")
