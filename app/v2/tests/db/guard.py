"""
Fail-closed guard for V2 database tests.

THE RULE. A database may be used by V2 DB tests only if ALL of these hold:

  1. V2_TEST_DATABASE_URL is set. There is NO fallback to DATABASE_URL,
     V2_DATABASE_URL or anything else. Unset => tests skip (or fail when
     V2_REQUIRE_DB_TESTS=1).
  2. It is a PostgreSQL URL (postgresql / postgresql+psycopg2).
  3. The database NAME matches ^venturegps_v2_test(_[a-z0-9]+)?$ .
  4. The host is loopback (localhost, 127.0.0.1, ::1), a unix-socket path, or
     listed EXACTLY in V2_TEST_DATABASE_ALLOWED_HOSTS. Loopback alone is not
     sufficient (rules 3 and 5 still apply); a remote host needs an explicit
     opt-in.
  5. The database name differs from the name in DATABASE_URL / V2_DATABASE_URL
     (whatever host they use).
  6. Before any destructive step, the SERVER itself attests that the database
     is disposable: current_database() equals the URL's database and the
     database comment is exactly VENTUREGPS_V2_DISPOSABLE_TEST_DB
     (COMMENT ON DATABASE ... IS '...'). A production database will not carry it.

Any doubt refuses. Error messages never include a URL (passwords).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

TEST_DATABASE_URL_ENV = "V2_TEST_DATABASE_URL"
ALLOWED_HOSTS_ENV = "V2_TEST_DATABASE_ALLOWED_HOSTS"
REQUIRE_DB_TESTS_ENV = "V2_REQUIRE_DB_TESTS"

DISPOSABLE_MARKER = "VENTUREGPS_V2_DISPOSABLE_TEST_DB"
DATABASE_NAME_PATTERN = re.compile(r"^venturegps_v2_test(_[a-z0-9]+)?$")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_SUPPORTED_DRIVERS = ("postgresql", "postgresql+psycopg2")


class UnsafeTestDatabaseError(RuntimeError):
    """The configured test database is not provably disposable."""


class DatabaseNotConfigured(RuntimeError):
    """V2_TEST_DATABASE_URL is not set."""


@dataclass(frozen=True)
class DisposableDatabase:
    url: str
    host: str
    port: int | None
    database: str


def _host_of(url) -> str:
    host = url.host or url.query.get("host") or ""
    if isinstance(host, (tuple, list)):
        host = host[0] if host else ""
    return str(host).strip().lower()


def validate_test_database_url(
    raw: str | None,
    *,
    production_urls: Mapping[str, str] | None = None,
    allowed_hosts: Iterable[str] = (),
) -> DisposableDatabase:
    if raw is None or not raw.strip():
        raise DatabaseNotConfigured(f"{TEST_DATABASE_URL_ENV} is not set")

    try:
        url = make_url(raw.strip())
    except ArgumentError:
        raise UnsafeTestDatabaseError(f"{TEST_DATABASE_URL_ENV} could not be parsed") from None

    if url.drivername not in _SUPPORTED_DRIVERS:
        raise UnsafeTestDatabaseError(f"unsupported driver {url.drivername!r}; PostgreSQL only")

    database = url.database or ""
    if not DATABASE_NAME_PATTERN.match(database):
        raise UnsafeTestDatabaseError(
            f"database name {database!r} does not match {DATABASE_NAME_PATTERN.pattern}"
        )

    host = _host_of(url)
    allowed = {h.strip().lower() for h in allowed_hosts if h and h.strip()}
    if not host:
        raise UnsafeTestDatabaseError("test database host must be explicit")
    if not (host in LOOPBACK_HOSTS or host.startswith("/") or host in allowed):
        raise UnsafeTestDatabaseError(
            f"host {host!r} is not loopback/socket and is not listed in {ALLOWED_HOSTS_ENV}"
        )

    for env_name, prod_raw in (production_urls or {}).items():
        try:
            prod = make_url((prod_raw or "").strip().replace("postgres://", "postgresql://", 1))
        except ArgumentError:
            continue
        if prod.database and prod.database == database:
            raise UnsafeTestDatabaseError(
                f"database name {database!r} is the same as the one in {env_name}"
            )

    return DisposableDatabase(url=raw.strip(), host=host, port=url.port, database=database)


def verify_server_attests_disposable(connection, target: DisposableDatabase) -> None:
    """Server-side check; call before any destructive statement."""
    current = connection.execute(text("SELECT current_database()")).scalar()
    marker = connection.execute(
        text(
            "SELECT shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        )
    ).scalar()
    if current != target.database:
        raise UnsafeTestDatabaseError(
            f"connected to {current!r} but the configured test database is {target.database!r}"
        )
    if marker != DISPOSABLE_MARKER:
        raise UnsafeTestDatabaseError(
            f"database {current!r} is not marked disposable "
            f"(expected database comment {DISPOSABLE_MARKER!r}); refusing to run destructive tests"
        )
