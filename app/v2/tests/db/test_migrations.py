"""V2 migrations against the disposable test database (guarded: see guard.py)."""

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.v2.tests.db.harness import (
    HEAD_REVISION,
    HEAD_V2_OBJECTS,
    REVISION_0001_V2_OBJECTS,
    REVISION_0002_V2_OBJECTS,
    REVISION_0003_V2_OBJECTS,
    REVISION_0004_V2_OBJECTS,
    REVISION_0005_V2_OBJECTS,
    REVISION_0006_V2_OBJECTS,
    REVISION_0007_V2_OBJECTS,
    REVISION_0008_V2_OBJECTS,
    REVISION_0009_V2_OBJECTS,
    make_alembic_config,
    scalar,
    v2_objects,
)

pytestmark = pytest.mark.db

HEAD = HEAD_REVISION


def schema_exists(engine) -> bool:
    return scalar(engine, "SELECT count(*) FROM pg_namespace WHERE nspname = 'v2'") == 1


def test_upgrade_base_to_head_creates_schema_and_v2_version_table(clean_db, alembic_cfg):
    assert not schema_exists(clean_db)

    command.upgrade(alembic_cfg(), "head")

    assert schema_exists(clean_db)
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == HEAD
    assert HEAD == ScriptDirectory.from_config(make_alembic_config()).get_current_head()
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS  # exactly what the revisions so far created
    assert "VentureGPS V2" in scalar(clean_db, "SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname = 'v2'")


def test_version_table_is_in_v2_and_not_in_public(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    assert scalar(clean_db, "SELECT to_regclass('v2.alembic_version')") is not None
    assert scalar(clean_db, "SELECT to_regclass('public.alembic_version')") is None


def test_upgrade_is_idempotent(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.upgrade(alembic_cfg(), "head")
    assert scalar(clean_db, "SELECT count(*) FROM v2.alembic_version") == 1


def test_downgrade_head_to_base_leaves_no_v2_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "base")
    assert not schema_exists(clean_db)
    assert scalar(clean_db, "SELECT to_regclass('v2.alembic_version')") is None


def test_upgrade_again_after_downgrade(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "base")
    command.upgrade(alembic_cfg(), "head")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == HEAD
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS


def test_downgrading_one_revision_at_a_time_ends_at_base(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "-1")                       # 0010 -> 0009: market/taxonomy/classification go
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0009"
    assert v2_objects(clean_db) == REVISION_0009_V2_OBJECTS
    command.downgrade(alembic_cfg(), "-1")                       # 0009 -> 0008: canonical financing events go
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0008"
    assert v2_objects(clean_db) == REVISION_0008_V2_OBJECTS
    command.downgrade(alembic_cfg(), "-1")                       # 0008 -> 0007: financing candidates go
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0007"
    assert v2_objects(clean_db) == REVISION_0007_V2_OBJECTS
    command.downgrade(alembic_cfg(), "-1")                       # 0007 -> 0006: resolution + canonical identity go
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0006"
    assert v2_objects(clean_db) == REVISION_0006_V2_OBJECTS
    command.downgrade(alembic_cfg(), "-1")                       # 0006 -> 0005: candidates go
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0005"
    assert v2_objects(clean_db) == REVISION_0005_V2_OBJECTS
    command.downgrade(alembic_cfg(), "-1")                       # 0005 -> 0004: processing history goes
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0004"
    assert v2_objects(clean_db) == REVISION_0004_V2_OBJECTS
    command.downgrade(alembic_cfg(), "-1")                       # 0004 -> 0003: sightings go
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0003"
    assert v2_objects(clean_db) == REVISION_0003_V2_OBJECTS
    command.downgrade(alembic_cfg(), "-1")                       # 0003 -> 0002: evidence tables go
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0002"
    assert v2_objects(clean_db) == REVISION_0002_V2_OBJECTS
    command.downgrade(alembic_cfg(), "-1")                       # 0002 -> 0001: namespace stays, source goes
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0001"
    assert v2_objects(clean_db) == REVISION_0001_V2_OBJECTS
    command.downgrade(alembic_cfg(), "-1")                       # 0001 -> base: schema removed
    assert not schema_exists(clean_db)


def test_upgrade_works_when_the_schema_already_exists(clean_db, alembic_cfg):
    with clean_db.begin() as conn:
        conn.execute(text("CREATE SCHEMA v2"))
    command.upgrade(alembic_cfg(), "head")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == HEAD


def test_read_only_commands_do_not_create_anything(clean_db, alembic_cfg):
    cfg = alembic_cfg()
    command.current(cfg)
    command.heads(cfg)
    command.history(cfg)
    assert not schema_exists(clean_db)


def test_downgrade_to_base_refuses_to_drop_a_schema_holding_foreign_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    with clean_db.begin() as conn:
        conn.execute(text("CREATE TABLE v2.stray_table (id int)"))

    with pytest.raises(Exception, match="stray_table|depend"):
        command.downgrade(alembic_cfg(), "base")

    # The whole downgrade rolled back: still at head, schema, comment and stray table intact.
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == HEAD
    assert scalar(clean_db, "SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname = 'v2'") is not None
    assert scalar(clean_db, "SELECT to_regclass('v2.stray_table')") is not None
