"""
Fixtures for tests that need the disposable PostgreSQL test database.

Only V2_TEST_DATABASE_URL is ever read (see guard.py for the exact safety
rule). An UNSET URL skips DB tests (fails if V2_REQUIRE_DB_TESTS=1); an UNSAFE
URL fails loudly -- it is never skipped and never "fixed up".
"""

import os

import pytest

from app.v2.db.engine import make_engine
from app.v2.tests.db import guard, harness


@pytest.fixture(scope="session")
def db_target(production_urls):
    raw = os.environ.get(guard.TEST_DATABASE_URL_ENV)
    allowed = os.environ.get(guard.ALLOWED_HOSTS_ENV, "").split(",")
    try:
        return guard.validate_test_database_url(raw, production_urls=production_urls, allowed_hosts=allowed)
    except guard.DatabaseNotConfigured as exc:
        message = f"{exc}; database tests need a disposable test DB (see docs/v2/DATABASE_MIGRATIONS.md)"
        if os.environ.get(guard.REQUIRE_DB_TESTS_ENV) == "1":
            pytest.fail(f"{message} [{guard.REQUIRE_DB_TESTS_ENV}=1]", pytrace=False)
        pytest.skip(message)
    except guard.UnsafeTestDatabaseError as exc:
        pytest.fail(f"REFUSING to run V2 database tests: {exc}", pytrace=False)


@pytest.fixture(scope="session")
def db_engine(db_target):
    engine = make_engine(db_target.url, pooled=False)
    try:
        with engine.connect() as conn:
            guard.verify_server_attests_disposable(conn, db_target)
    except guard.UnsafeTestDatabaseError as exc:
        engine.dispose()
        pytest.fail(f"REFUSING to run V2 database tests: {exc}", pytrace=False)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_db(db_engine):
    harness.reset_database(db_engine)
    yield db_engine
    harness.reset_database(db_engine)


@pytest.fixture
def alembic_cfg(db_target):
    def make(lock_timeout: float | None = None):
        return harness.make_alembic_config(db_target.url, lock_timeout=lock_timeout)
    return make


@pytest.fixture
def legacy_probe(clean_db):
    harness.create_legacy_probe_objects(clean_db)
    return clean_db
