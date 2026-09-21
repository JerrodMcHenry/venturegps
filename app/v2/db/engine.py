"""
V2 engine factory. Nothing here connects at import time or when an engine
is created (SQLAlchemy engines are lazy; the first connect happens on first use).

- make_engine(url): pure factory, used by tests and Alembic. Takes an
  explicit URL and reads no environment, so a test can never be redirected
  to a production URL by ambient configuration.
- get_engine(): the process-wide engine for runtime code (later increments),
  built from app.v2.config.get_database_url() on first call.

The pool is deliberately small: V2 shares one managed Postgres with the
legacy app's default pool, and managed plans cap connections.
"""

import threading

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from app.v2.config import get_database_url, normalize_database_url

POOL_SIZE = 2
MAX_OVERFLOW = 2
POOL_RECYCLE_SECONDS = 1800
APPLICATION_NAME = "venturegps-v2"

_engine: Engine | None = None
_engine_lock = threading.Lock()


def make_engine(url: str, *, pooled: bool = True) -> Engine:
    """Build (not connect) an engine. pooled=False uses NullPool, for
    short-lived processes such as migrations and tests."""
    kwargs: dict = {
        "pool_pre_ping": True,
        "connect_args": {"application_name": APPLICATION_NAME},
    }
    if pooled:
        kwargs.update(
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_recycle=POOL_RECYCLE_SECONDS,
        )
    else:
        kwargs["poolclass"] = NullPool
    return create_engine(normalize_database_url(url), **kwargs)


def get_engine() -> Engine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = make_engine(get_database_url())
        return _engine


def dispose_engine() -> None:
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None
