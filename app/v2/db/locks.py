"""
Migration mutual exclusion: one PostgreSQL session-level advisory lock, so
two `alembic upgrade` processes cannot race. Deliberately not a general
locking framework.

try-lock + poll (not a blocking pg_advisory_lock) so a hung migrator makes
the next one fail with a clear error after a timeout instead of waiting forever.
"""

import time
from contextlib import contextmanager

from sqlalchemy import text

# Arbitrary fixed 64-bit key identifying "VentureGPS V2 migrations".
MIGRATION_LOCK_KEY = 7206540001002

POLL_INTERVAL_SECONDS = 0.1


class MigrationLockError(RuntimeError):
    """Another migration process holds the V2 migration lock."""


@contextmanager
def migration_lock(connection, *, timeout_seconds: float, poll_interval: float = POLL_INTERVAL_SECONDS):
    deadline = time.monotonic() + timeout_seconds
    while True:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
        ).scalar()
        # End the implicit transaction: the lock is session-level and survives
        # the commit, and Alembic must start from a connection NOT already in
        # a transaction or it will not commit its own work.
        connection.commit()
        if acquired:
            break
        if time.monotonic() >= deadline:
            raise MigrationLockError(
                f"could not acquire the V2 migration lock within {timeout_seconds:g}s; "
                "another migration process appears to be running"
            )
        time.sleep(poll_interval)
    try:
        yield
    finally:
        connection.rollback()  # clear any failed transaction before unlocking
        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY})
        connection.commit()
