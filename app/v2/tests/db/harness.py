"""
Helpers for V2 database tests. Only ever handed an engine that already passed
guard.validate_test_database_url() AND guard.verify_server_attests_disposable().
"""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[4]

LEGACY_PROBE_TABLES = ("legacy_probe_analyses", "legacy_probe_startups")
LEGACY_PROBE_VIEW = "legacy_probe_latest"
DECOY_TABLE = "alembic_version"  # a table in public with V2's version-table name

_SYSTEM = "('pg_catalog','information_schema')"


def make_alembic_config(url: str | None = None, *, lock_timeout: float | None = None) -> Config:
    """alembic.ini + programmatic settings. `url` is ALWAYS passed explicitly by DB
    tests; env.py would otherwise fall back to production environment variables."""
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    if url is not None:
        cfg.attributes["v2_database_url"] = url
    if lock_timeout is not None:
        cfg.attributes["v2_lock_timeout_seconds"] = lock_timeout
    return cfg


def reset_database(engine) -> None:
    """Remove ONLY what tests create: schema v2 and the legacy probe objects."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS v2 CASCADE"))
        conn.execute(text(f"DROP VIEW IF EXISTS public.{LEGACY_PROBE_VIEW}"))
        for table in LEGACY_PROBE_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS public.{table}"))
        conn.execute(text(f"DROP TABLE IF EXISTS public.{DECOY_TABLE}"))


def create_legacy_probe_objects(engine) -> None:
    """Representative legacy-style objects, including a public.alembic_version decoy."""
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
        if exists is not None:
            raise AssertionError("public.alembic_version already exists: this test database is not disposable")
        conn.execute(text("""
            CREATE TABLE public.legacy_probe_startups (
                id SERIAL PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""))
        conn.execute(text("""
            CREATE TABLE public.legacy_probe_analyses (
                id SERIAL PRIMARY KEY,
                startup_id INTEGER REFERENCES public.legacy_probe_startups(id),
                methodology JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""))
        conn.execute(text("CREATE INDEX legacy_probe_analyses_startup ON public.legacy_probe_analyses (startup_id)"))
        conn.execute(text(
            "CREATE VIEW public.legacy_probe_latest AS "
            "SELECT s.canonical_name, a.methodology FROM public.legacy_probe_analyses a "
            "JOIN public.legacy_probe_startups s ON s.id = a.startup_id"))
        conn.execute(text("INSERT INTO public.legacy_probe_startups (canonical_name, normalized_name) VALUES ('Acme','acme'),('Globex','globex')"))
        conn.execute(text("""INSERT INTO public.legacy_probe_analyses (startup_id, methodology)
                             VALUES (1, '{"startup_intelligence_score": 71.5}'), (2, '{"startup_intelligence_score": 40.0}')"""))
        conn.execute(text("CREATE TABLE public.alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        conn.execute(text("INSERT INTO public.alembic_version VALUES ('legacy-decoy-not-v2')"))


def snapshot_non_v2(engine) -> dict:
    """Everything observable outside schema v2: objects, columns, indexes,
    constraints, sequences, schemas, and a content hash + row count of every table."""
    excl = f"n.nspname NOT IN {_SYSTEM} AND n.nspname <> 'v2' AND n.nspname NOT LIKE 'pg\\_toast%' AND n.nspname NOT LIKE 'pg\\_temp%'"
    with engine.connect() as conn:
        objects = [tuple(r) for r in conn.execute(text(
            f"SELECT n.nspname, c.relname, c.relkind::text FROM pg_class c "
            f"JOIN pg_namespace n ON n.oid = c.relnamespace WHERE {excl} ORDER BY 1,2,3"))]
        schemas = [r[0] for r in conn.execute(text(
            f"SELECT n.nspname FROM pg_namespace n WHERE {excl} ORDER BY 1"))]
        columns = [tuple(r) for r in conn.execute(text(
            "SELECT table_schema, table_name, column_name, data_type, is_nullable, column_default "
            f"FROM information_schema.columns WHERE table_schema NOT IN {_SYSTEM} AND table_schema <> 'v2' "
            "ORDER BY 1,2,ordinal_position"))]
        indexes = [tuple(r) for r in conn.execute(text(
            f"SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes "
            f"WHERE schemaname NOT IN {_SYSTEM} AND schemaname <> 'v2' ORDER BY 1,2,3"))]
        constraints = [tuple(r) for r in conn.execute(text(
            "SELECT n.nspname, c.conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
            f"JOIN pg_namespace n ON n.oid = c.connamespace WHERE {excl} ORDER BY 1,2"))]
        sequences = [tuple(r) for r in conn.execute(text(
            f"SELECT schemaname, sequencename, last_value FROM pg_sequences "
            f"WHERE schemaname NOT IN {_SYSTEM} AND schemaname <> 'v2' ORDER BY 1,2"))]
        data = {}
        for schema, name, kind in objects:
            if kind == "r":
                qualified = f'"{schema}"."{name}"'
                data[f"{schema}.{name}"] = tuple(conn.execute(text(
                    f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM {qualified} t")).one())
    return {"objects": objects, "schemas": schemas, "columns": columns, "indexes": indexes,
            "constraints": constraints, "sequences": sequences, "data": data}


def v2_objects(engine) -> list[tuple[str, str]]:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(
            "SELECT c.relname, c.relkind::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'v2' AND c.relkind NOT IN ('i') ORDER BY 1"))]


def scalar(engine, sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()
