"""Alembic configuration is scoped to schema v2 and stays out of legacy code paths."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.script import ScriptDirectory

from app.v2.db.metadata import V2_SCHEMA, metadata
from app.v2.db.scope import VERSION_TABLE, VERSION_TABLE_SCHEMA, include_name, include_object
from app.v2.tests.db.harness import REPO_ROOT, make_alembic_config


def test_version_table_lives_in_v2_not_public():
    assert (VERSION_TABLE, VERSION_TABLE_SCHEMA) == ("alembic_version", "v2")
    assert V2_SCHEMA == "v2" and metadata.schema == "v2"


@pytest.mark.parametrize(
    "name, type_, parent, expected",
    [
        ("v2", "schema", {}, True),
        ("public", "schema", {}, False),
        (None, "schema", {}, False),          # the default schema: where legacy tables live
        ("pg_catalog", "schema", {}, False),
        ("anything", "table", {"schema_name": "v2"}, True),
        ("startups", "table", {"schema_name": None}, False),
        ("startups", "table", {"schema_name": "public"}, False),
        ("alembic_version", "table", {"schema_name": "public"}, False),
        ("x", "column", {}, False),
    ],
)
def test_include_name_only_admits_schema_v2(name, type_, parent, expected):
    assert include_name(name, type_, parent) is expected


def test_include_object_is_fail_closed():
    table = lambda schema: SimpleNamespace(schema=schema)
    assert include_object(table("v2"), "t", "table", False, None) is True
    assert include_object(table("public"), "startups", "table", True, None) is False
    assert include_object(table(None), "startups", "table", True, None) is False
    child = lambda schema: SimpleNamespace(table=table(schema))
    assert include_object(child("v2"), "ix", "index", False, None) is True
    assert include_object(child("public"), "ix", "index", True, None) is False
    assert include_object(SimpleNamespace(), "mystery", "column", False, None) is False


def test_alembic_ini_has_no_database_url_and_points_at_the_v2_migrations():
    cfg = make_alembic_config()
    assert cfg.get_main_option("sqlalchemy.url") is None
    assert Path(cfg.get_main_option("script_location")) == REPO_ROOT / "app" / "v2" / "migrations"


def test_migration_history_is_linear_and_starts_with_the_namespace_revision():
    script = ScriptDirectory.from_config(make_alembic_config())
    assert script.get_heads() == ["0007"]
    assert script.get_revision("0001").down_revision is None
    assert script.get_revision("0002").down_revision == "0001"
    assert script.get_revision("0003").down_revision == "0002"
    assert script.get_revision("0004").down_revision == "0003"
    assert script.get_revision("0005").down_revision == "0004"
    assert script.get_revision("0006").down_revision == "0005"


def test_revision_0001_creates_no_tables():
    source = (REPO_ROOT / "app/v2/migrations/versions/0001_establish_v2_namespace.py").read_text().lower()
    assert "create table" not in source and "create_table" not in source


def test_revision_0002_creates_only_v2_source():
    source = (REPO_ROOT / "app/v2/migrations/versions/0002_create_source.py").read_text()
    assert source.count("CREATE TABLE") == 1 and "CREATE TABLE v2.source" in source
    assert "public." not in source and "op.create_table" not in source


def test_only_numbered_revision_files_exist():
    names = [p.name for p in (REPO_ROOT / "app/v2/migrations/versions").glob("*.py")]
    assert names and all(re.match(r"^\d{4}_[a-z0-9_]+\.py$", n) for n in names)


def test_legacy_runtime_files_do_not_run_v2_migrations():
    for rel in ("app/api.py", "app/database/db.py", "render.yaml"):
        text = (REPO_ROOT / rel).read_text().lower()
        assert "alembic" not in text and "app.v2" not in text, rel
    assert "predeploy" not in (REPO_ROOT / "render.yaml").read_text().lower()


def test_v2_never_runs_migrations_from_application_code():
    offenders = []
    for path in (REPO_ROOT / "app/v2").rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith(("app/v2/tests/", "app/v2/migrations/")):
            continue
        if re.search(r"alembic\.command|command\.upgrade|command\.downgrade", path.read_text()):
            offenders.append(rel)
    assert offenders == []
