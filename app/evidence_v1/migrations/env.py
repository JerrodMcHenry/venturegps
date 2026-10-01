"""
Alembic environment for Evidence Engine v1 product persistence ONLY.

Deliberately minimal and fully independent of app/v2/migrations/env.py --
see alembic_evidence_v1.ini's own header for why a second environment
exists at all, and docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md
for the full architectural decision record.

Loaded by the `alembic -c alembic_evidence_v1.ini` CLI only -- never
imported by application code, never run at app import or FastAPI startup
(same "run manually" convention V2 established).

Target database: DATABASE_URL directly (the same database the legacy app
uses) -- no V2_DATABASE_URL fallback logic, since this environment has no
relationship to V2 at all. No new Postgres schema is created; the one
table this environment owns (evidence_v1_analyses) and its own version
table (evidence_v1_alembic_version) both live in the default/public
schema. No autogenerate -- target_metadata is None and every revision is
a small, explicit, hand-written migration (this environment manages
exactly one table; autogenerate's reflection/diffing machinery is not
needed and would otherwise require its own schema-scoping safeguards,
which V2's own env.py needed precisely because it does use autogenerate).
"""

import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

load_dotenv()

VERSION_TABLE = "evidence_v1_alembic_version"


def _database_url() -> str:
    """DATABASE_URL, normalized the same minimal way app/v2/config.py's
    own normalize_database_url() does (Render-style postgres:// ->
    postgresql://) -- duplicated here, deliberately, rather than
    imported from app.v2.config, so this environment has zero import
    dependency on the V2 subsystem (not even a config helper)."""
    raw = os.environ.get("DATABASE_URL")
    if not raw or not raw.strip():
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    value = raw.strip()
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    try:
        make_url(value)
    except ArgumentError:
        raise RuntimeError("DATABASE_URL could not be parsed.") from None
    return value


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(), target_metadata=None, version_table=VERSION_TABLE,
        version_table_schema=None, literal_binds=True, dialect_name="postgresql",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=None,
                version_table=VERSION_TABLE, version_table_schema=None,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
