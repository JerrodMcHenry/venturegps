"""
V2 configuration. Reads the PROCESS environment lazily, inside functions --
importing this module never reads a variable, opens a connection, or loads
a .env file (unlike legacy app/database/db.py). Deterministic V2 modules
therefore import fine with no DATABASE_URL and no AI credentials.

Database URL resolution (runtime and the `alembic` CLI):

    V2_DATABASE_URL   preferred, explicit V2 target
    DATABASE_URL      fallback: the existing single Postgres deployment

V2_TEST_DATABASE_URL is deliberately NOT read here. It belongs to the test
harness (app/v2/tests/db/), and nothing in this module may ever fall back
to or from it.

Error messages never include a URL (URLs carry passwords).
"""

import os
from collections.abc import Mapping

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DATABASE_URL_ENV = "V2_DATABASE_URL"
FALLBACK_DATABASE_URL_ENV = "DATABASE_URL"
MIGRATION_LOCK_TIMEOUT_ENV = "V2_MIGRATION_LOCK_TIMEOUT_SECONDS"
DEFAULT_MIGRATION_LOCK_TIMEOUT_SECONDS = 30.0

_SUPPORTED_DRIVERS = ("postgresql", "postgresql+psycopg2")


class ConfigurationError(RuntimeError):
    """Invalid or missing V2 configuration. The message never contains a URL."""


def normalize_database_url(raw: str) -> str:
    """Strip whitespace, map Render-style `postgres://` to `postgresql://`,
    and require a PostgreSQL (psycopg2) URL."""
    value = (raw or "").strip()
    if not value:
        raise ConfigurationError("database URL is empty")
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    try:
        url = make_url(value)
    except ArgumentError:
        raise ConfigurationError("database URL could not be parsed") from None
    if url.drivername not in _SUPPORTED_DRIVERS:
        raise ConfigurationError(
            f"unsupported database driver {url.drivername!r}; V2 requires PostgreSQL"
        )
    return value


def get_database_url(environ: Mapping[str, str] | None = None) -> str:
    """The V2 database URL: V2_DATABASE_URL, else DATABASE_URL, else an error."""
    env = os.environ if environ is None else environ
    for name in (DATABASE_URL_ENV, FALLBACK_DATABASE_URL_ENV):
        value = env.get(name)
        if value and value.strip():
            return normalize_database_url(value)
    raise ConfigurationError(
        f"no database configured: set {DATABASE_URL_ENV} (or {FALLBACK_DATABASE_URL_ENV})"
    )


def get_migration_lock_timeout(environ: Mapping[str, str] | None = None) -> float:
    env = os.environ if environ is None else environ
    raw = env.get(MIGRATION_LOCK_TIMEOUT_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_MIGRATION_LOCK_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        raise ConfigurationError(f"{MIGRATION_LOCK_TIMEOUT_ENV} must be a number") from None
    if value < 0:
        raise ConfigurationError(f"{MIGRATION_LOCK_TIMEOUT_ENV} must be >= 0")
    return value


def redact_database_url(url: str) -> str:
    """host:port/database only -- safe to log."""
    parsed = make_url(url)
    host = parsed.host or parsed.query.get("host") or "?"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{host}{port}/{parsed.database}"
