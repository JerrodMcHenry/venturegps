"""Two migration processes must not race (PostgreSQL advisory lock)."""

import os
import subprocess
import sys

import pytest
from alembic import command
from sqlalchemy import text

from app.v2.db.locks import MIGRATION_LOCK_KEY, MigrationLockError
from app.v2.tests.db.harness import HEAD_REVISION, REPO_ROOT, scalar

pytestmark = pytest.mark.db


def test_lock_key_fits_a_bigint():
    assert 0 < MIGRATION_LOCK_KEY < 2**63


def test_migration_fails_fast_when_another_process_holds_the_lock(clean_db, alembic_cfg):
    holder = clean_db.connect()
    try:
        assert holder.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY}).scalar() is True
        holder.commit()

        with pytest.raises(MigrationLockError, match="another migration process"):
            command.upgrade(alembic_cfg(lock_timeout=0.5), "head")

        # ...and it changed nothing while waiting.
        assert scalar(clean_db, "SELECT count(*) FROM pg_namespace WHERE nspname = 'v2'") == 0
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY})
        holder.commit()
        holder.close()

    command.upgrade(alembic_cfg(lock_timeout=5), "head")  # lock free again
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION


def _cli_env(db_target) -> dict[str, str]:
    """A child environment for the real `alembic` CLI: only the GUARDED test URL, no production URL."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("DATABASE_URL", "V2_DATABASE_URL", "V2_TEST_DATABASE_URL")}
    env.update(V2_DATABASE_URL=db_target.url, V2_MIGRATION_LOCK_TIMEOUT_SECONDS="30", PYTHONDONTWRITEBYTECODE="1")
    return env


def test_concurrent_cli_upgrades_serialize_and_all_succeed(clean_db, db_target):
    """Separate PROCESSES (the real deployment shape; alembic's `context` proxy is not thread-safe)."""
    procs = [
        subprocess.Popen([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=REPO_ROOT,
                         env=_cli_env(db_target), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(4)
    ]
    results = [(p.wait(timeout=90), p.stdout.read(), p.stderr.read()) for p in procs]

    assert [code for code, _, _ in results] == [0, 0, 0, 0], results
    assert scalar(clean_db, "SELECT count(*) FROM v2.alembic_version") == 1
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION
    # exactly one process actually ran the revisions; the rest found them already applied
    assert sum("Running upgrade  -> 0001" in err for _, _, err in results) == 1, results
    assert sum("Running upgrade 0001 -> 0002" in err for _, _, err in results) == 1, results


def test_cli_reports_the_redacted_target_and_uses_v2_database_url(clean_db, db_target):
    done = subprocess.run([sys.executable, "-m", "alembic", "current"], cwd=REPO_ROOT,
                          env=_cli_env(db_target), capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert f"V2 migration target: {db_target.host}:{db_target.port}/{db_target.database}" in done.stderr


def test_lock_is_released_after_a_failed_migration(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    with clean_db.begin() as conn:
        conn.execute(text("CREATE TABLE v2.stray_table (id int)"))
    with pytest.raises(Exception):
        command.downgrade(alembic_cfg(), "base")  # fails: schema not empty

    other = clean_db.connect()
    try:
        assert other.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY}).scalar() is True
        other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY})
        other.commit()
    finally:
        other.close()
