"""
Alembic environment for VentureGPS V2 (schema `v2` only).

Loaded by the `alembic` CLI or alembic.command.* -- never imported by
application code and never run at app import or FastAPI startup.

Target database
    config.attributes["v2_database_url"] if set programmatically (tests do
    this, always), else app.v2.config.get_database_url(). The target
    host/database (never the password) is logged before anything runs.

Bootstrap (why the schema is created here, not only in revision 0001)
    Alembic creates its version table BEFORE running the first revision, and
    that table lives in `v2`, so the schema must already exist. On any
    command that upgrades to a revision, env.py runs an idempotent
    `CREATE SCHEMA IF NOT EXISTS v2`. Revision 0001 then records the
    namespace in the migration history. Read-only commands (current, heads,
    history) create nothing.

Teardown (symmetry)
    Alembic cannot remove the table that records its own progress from
    inside a revision. So when a downgrade reverts everything to base, env.py
    drops v2.alembic_version and then the `v2` schema -- in the SAME
    transaction as the downgrade. DROP SCHEMA has no CASCADE, so if anything
    else lives in `v2` the whole downgrade rolls back.

Concurrency
    A session-level advisory lock (app.v2.db.locks) is held for the whole run.

Scope
    include_name / include_object (app.v2.db.scope) restrict autogenerate to
    schema `v2`; legacy `public` tables are never reflected.
"""

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import text

from app.v2.config import get_database_url, get_migration_lock_timeout, redact_database_url
from app.v2.db.engine import make_engine
from app.v2.db.locks import migration_lock
from app.v2.db import tables  # noqa: F401 -- registers V2 tables on the metadata
from app.v2.db.metadata import V2_SCHEMA, metadata
from app.v2.db.scope import (
    VERSION_TABLE,
    VERSION_TABLE_SCHEMA,
    include_name,
    include_object,
)

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

log = logging.getLogger("alembic.env.v2")


def _context_kwargs() -> dict:
    return dict(
        target_metadata=metadata,
        version_table=VERSION_TABLE,
        version_table_schema=VERSION_TABLE_SCHEMA,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        compare_type=True,
    )


def _wants_bootstrap() -> bool:
    """True only for commands that upgrade/stamp TO a revision. Commands with no
    destination (current, check, heads, history) raise KeyError; downgrade to
    base yields None -- neither should create the schema."""
    try:
        return context.get_revision_argument() is not None
    except KeyError:
        return False


def _current_heads(connection) -> tuple[str, ...]:
    """Recorded revisions, without creating anything. Does not commit."""
    exists = connection.execute(
        text("SELECT to_regclass(:name)"), {"name": f"{V2_SCHEMA}.{VERSION_TABLE}"}
    ).scalar()
    if exists is None:
        return ()
    rows = connection.execute(text(f"SELECT version_num FROM {V2_SCHEMA}.{VERSION_TABLE}")).all()
    return tuple(row[0] for row in rows)


def _teardown_if_reverted_to_base(connection, heads_before: tuple[str, ...]) -> None:
    if not heads_before or _current_heads(connection):
        return
    connection.execute(text(f"DROP TABLE {V2_SCHEMA}.{VERSION_TABLE}"))
    connection.execute(text(f"DROP SCHEMA {V2_SCHEMA}"))  # no CASCADE: refuses if anything else lives here


def run_migrations_offline() -> None:
    """Emit SQL (`alembic upgrade head --sql`) without connecting."""
    context.configure(dialect_name="postgresql", literal_binds=True, **_context_kwargs())
    with context.begin_transaction():
        if _wants_bootstrap():
            context.execute(f"CREATE SCHEMA IF NOT EXISTS {V2_SCHEMA}")
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.attributes.get("v2_database_url") or get_database_url()
    timeout = config.attributes.get("v2_lock_timeout_seconds")
    if timeout is None:
        timeout = get_migration_lock_timeout()

    log.info("V2 migration target: %s", redact_database_url(url))
    engine = make_engine(url, pooled=False)
    try:
        with engine.connect() as connection:
            with migration_lock(connection, timeout_seconds=timeout):
                # Connection is not in a transaction here (migration_lock committed),
                # which Alembic requires in order to manage its own transaction.
                context.configure(connection=connection, **_context_kwargs())

                if _wants_bootstrap():
                    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {V2_SCHEMA}"))
                    connection.commit()

                heads_before = _current_heads(connection)
                connection.commit()

                with context.begin_transaction():
                    context.run_migrations()
                    _teardown_if_reverted_to_base(connection, heads_before)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
