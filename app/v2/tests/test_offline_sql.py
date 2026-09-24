"""`alembic ... --sql` renders the migrations without any database connection."""

import io

from alembic import command

from app.v2.tests.db.harness import make_alembic_config


def render(direction: str, revision: str) -> str:
    cfg = make_alembic_config()  # no URL: offline mode must not need one
    cfg.output_buffer = io.StringIO()
    getattr(command, direction)(cfg, revision, sql=True)
    return cfg.output_buffer.getvalue()


def test_upgrade_sql_is_confined_to_schema_v2():
    sql = render("upgrade", "head")
    assert "CREATE SCHEMA IF NOT EXISTS v2" in sql
    assert "CREATE TABLE v2.alembic_version" in sql
    assert "INSERT INTO v2.alembic_version" in sql
    assert "COMMENT ON SCHEMA v2 IS" in sql
    assert "public" not in sql.replace("Legacy tables live in public and are never managed here", "")
    assert sql.count("CREATE TABLE") == 25  # version table + the 24 V2 tables through revision 0011: nothing else
    assert "CREATE TABLE v2.company_candidate" in sql
    assert "CREATE TABLE v2.processing_attempt" in sql
    assert "CREATE TABLE v2.observation_sighting" in sql
    assert "CREATE TABLE v2.raw_payload" in sql and "CREATE TABLE v2.observation" in sql
    assert "CREATE TABLE v2.source" in sql and "CREATE FUNCTION v2.source_guard" in sql
    assert "CREATE TRIGGER trg_source_guard" in sql


def test_downgrade_sql_reverts_only_the_comment_and_version_row():
    sql = render("downgrade", "0001:base")
    assert "COMMENT ON SCHEMA v2 IS NULL" in sql
    assert "DELETE FROM v2.alembic_version" in sql
    assert "DROP TABLE" not in sql.replace("DROP TABLE v2.alembic_version", "")


def test_revision_0002_offline_upgrade_and_downgrade_render_only_source_objects():
    up = render("upgrade", "0001:0002")
    assert "CREATE TABLE v2.source" in up and "UPDATE v2.alembic_version SET version_num='0002'" in up
    assert "public" not in up
    down = render("downgrade", "0002:0001")
    assert "DROP TABLE v2.source" in down and "DROP FUNCTION v2.source_guard()" in down
    assert "DROP SCHEMA" not in down and "public" not in down


def test_revision_0002_offline_upgrade_and_downgrade_render_only_source_objects():
    up = render("upgrade", "0001:0002")
    assert "CREATE TABLE v2.source" in up and "UPDATE v2.alembic_version SET version_num='0002'" in up
    assert "public" not in up
    down = render("downgrade", "0002:0001")
    assert "DROP TABLE v2.source" in down and "DROP FUNCTION v2.source_guard()" in down
    assert "DROP SCHEMA" not in down and "public" not in down
