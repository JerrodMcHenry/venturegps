"""
Task 31 -- migration safety tests for the independent Evidence Engine v1
Alembic environment (alembic_evidence_v1.ini). Runs against the real,
configured DATABASE_URL (same convention as
app/tests/test_backend_authentication.py's own "lazy users-table
synchronization" group and app/tests/test_startup_write_path.py -- there
is no separate test database in this project). Every check cleans up
after itself; the suite leaves the database in the same upgraded state
it found it in (or creates it, if this is the first run).

No paid external call anywhere in this file -- pure DDL/DML against
Postgres.

Run with:
    python -m app.evidence_v1.tests.test_migrations
"""

from __future__ import annotations

from alembic.config import Config
from alembic import command
from sqlalchemy import text

from app.database.db import engine


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _evidence_v1_alembic_config() -> Config:
    return Config("alembic_evidence_v1.ini")


def _table_exists(connection, name: str, schema: str = "public") -> bool:
    return connection.execute(
        text("SELECT to_regclass(:qualified)"), {"qualified": f"{schema}.{name}"}
    ).scalar() is not None


def _schema_exists(connection, name: str) -> bool:
    return connection.execute(
        text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :name"), {"name": name}
    ).scalar() is not None


def test_upgrade_creates_the_expected_evidence_v1_structure() -> None:
    cfg = _evidence_v1_alembic_config()
    command.upgrade(cfg, "head")
    with engine.begin() as connection:
        expect(_table_exists(connection, "evidence_v1_analyses"), "evidence_v1_analyses must exist after upgrade")
        expect(_table_exists(connection, "evidence_v1_alembic_version"), "the independent version table must exist")
        cols = connection.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='evidence_v1_analyses'
        """)).scalars().all()
        for required in ("id", "owner_user_id", "company_name", "canonical_website", "engine",
                          "methodology_version", "result", "telemetry", "created_at"):
            expect(required in cols, f"evidence_v1_analyses must have column {required!r}, got {cols}")
        version = connection.execute(text("SELECT version_num FROM evidence_v1_alembic_version")).scalar()
        expect(version == "0001", f"expected version 0001, got {version!r}")


def test_evidence_migrations_do_not_touch_v2_schema_or_tables() -> None:
    with engine.begin() as connection:
        v2_existed_before = _schema_exists(connection, "v2")
    cfg = _evidence_v1_alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with engine.begin() as connection:
        v2_exists_after = _schema_exists(connection, "v2")
    expect(
        v2_existed_before == v2_exists_after,
        "evidence_v1 migrations must never create or drop the v2 schema",
    )


def test_evidence_migrations_do_not_modify_legacy_analyses_table() -> None:
    with engine.begin() as connection:
        before_count = connection.execute(text("SELECT count(*) FROM analyses")).scalar()
        before_cols = set(connection.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='analyses'
        """)).scalars().all())

    cfg = _evidence_v1_alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    with engine.begin() as connection:
        after_count = connection.execute(text("SELECT count(*) FROM analyses")).scalar()
        after_cols = set(connection.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='analyses'
        """)).scalars().all())

    expect(before_count == after_count, f"legacy analyses row count must be unchanged: {before_count} -> {after_count}")
    expect(before_cols == after_cols, "legacy analyses columns must be unchanged by evidence_v1 migrations")


def test_downgrade_removes_only_evidence_v1_owned_objects() -> None:
    cfg = _evidence_v1_alembic_config()
    command.upgrade(cfg, "head")

    with engine.begin() as connection:
        legacy_count_before = connection.execute(text("SELECT count(*) FROM analyses")).scalar()

    command.downgrade(cfg, "base")

    with engine.begin() as connection:
        expect(not _table_exists(connection, "evidence_v1_analyses"), "evidence_v1_analyses must be gone after downgrade to base")
        # Unlike V2's own env.py (which adds custom teardown logic to drop
        # its whole schema, including its version table, specifically
        # because it owns a schema), this minimal environment leaves its
        # own version-tracking table in place, empty -- standard Alembic
        # behavior, deliberately not replicated here (keeping this
        # environment "as small as possible" per its own design brief).
        # An empty, evidence_v1-owned tracking table is still correctly
        # "only evidence_v1-owned objects remain" -- it is not a stray
        # unrelated artifact.
        expect(_table_exists(connection, "evidence_v1_alembic_version"), "the version table itself is expected to remain (empty) after downgrade -- standard Alembic behavior")
        version_rows = connection.execute(text("SELECT count(*) FROM evidence_v1_alembic_version")).scalar()
        expect(version_rows == 0, f"the version table must be empty after downgrade to base, got {version_rows} row(s)")
        expect(_table_exists(connection, "analyses"), "legacy analyses table must survive an evidence_v1 downgrade")
        legacy_count_after = connection.execute(text("SELECT count(*) FROM analyses")).scalar()
        expect(legacy_count_before == legacy_count_after, "legacy analyses rows must survive an evidence_v1 downgrade")

    # Restore to head so the rest of the suite (and the running dev
    # server, if any) finds the table present again.
    command.upgrade(cfg, "head")


def test_no_version_table_collision_with_v2_or_legacy() -> None:
    """The three possible 'alembic_version'-shaped tables in this
    database must never collide: evidence_v1's own is named
    'evidence_v1_alembic_version', distinct from v2.alembic_version
    (different name AND different schema) and from the legacy app,
    which has no Alembic version table of its own at all (ad-hoc
    add_*_column migrations, per the Legacy DDL freeze)."""
    cfg = _evidence_v1_alembic_config()
    command.upgrade(cfg, "head")
    with engine.begin() as connection:
        public_version_tables = connection.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name LIKE '%alembic_version%'
        """)).scalars().all()
    expect(
        public_version_tables == ["evidence_v1_alembic_version"],
        f"exactly one version table should exist in public schema, got {public_version_tables}",
    )


def test_evidence_v1_analyses_table_has_expected_constraints() -> None:
    with engine.begin() as connection:
        constraint_names = connection.execute(text("""
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'evidence_v1_analyses'::regclass
        """)).scalars().all()
    for expected in ("pk_evidence_v1_analyses", "ck_evidence_v1_analyses_engine", "ck_evidence_v1_analyses_run_status"):
        expect(expected in constraint_names, f"missing constraint {expected!r}: {constraint_names}")


TESTS = [
    test_upgrade_creates_the_expected_evidence_v1_structure,
    test_evidence_migrations_do_not_touch_v2_schema_or_tables,
    test_evidence_migrations_do_not_modify_legacy_analyses_table,
    test_downgrade_removes_only_evidence_v1_owned_objects,
    test_no_version_table_collision_with_v2_or_legacy,
    test_evidence_v1_analyses_table_has_expected_constraints,
]


def main() -> None:
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {test.__name__}: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {test.__name__}: {exc!r}")
            failed += 1
    print("-" * 74)
    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
