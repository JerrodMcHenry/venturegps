"""Revision 0002 (v2.source): stepwise migration, exact schema, legacy untouched."""

import pytest
from alembic import command

from app.v2.tests.db.harness import (
    HEAD_V2_OBJECTS,
    REVISION_0001_V2_OBJECTS,
    REVISION_0002_V2_OBJECTS,
    scalar,
    snapshot_non_v2,
    v2_objects,
)
from sqlalchemy import text

pytestmark = pytest.mark.db


def rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def test_upgrade_0001_to_0002_creates_only_the_source_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0001")
    assert v2_objects(clean_db) == REVISION_0001_V2_OBJECTS
    assert scalar(clean_db, "SELECT to_regclass('v2.source')") is None

    command.upgrade(alembic_cfg(), "0002")

    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0002"
    assert v2_objects(clean_db) == REVISION_0002_V2_OBJECTS
    assert rows(clean_db, "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'v2'") == [("source_guard",)]


def test_downgrade_0002_to_0001_removes_only_increment_4_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "0001")

    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0001"
    assert v2_objects(clean_db) == REVISION_0001_V2_OBJECTS
    assert scalar(clean_db, "SELECT to_regclass('v2.source')") is None
    assert rows(clean_db, "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'v2'") == []
    assert scalar(clean_db, "SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname = 'v2'") is not None  # 0001 intact


def test_upgrade_again_after_downgrade(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "0001")
    command.upgrade(alembic_cfg(), "head")
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS


def test_a_populated_source_table_survives_nothing_but_downgrade_is_still_clean(migrated_db, alembic_cfg):
    with migrated_db.begin() as conn:
        conn.execute(text("INSERT INTO v2.source (source_key, source_name, source_type, collection_method, is_active) "
                          "VALUES ('sec_edgar', 'SEC', 'government_regulatory', 'api', true)"))
    command.downgrade(alembic_cfg(), "0001")  # dev/test-only policy: destructive downgrades are for disposable databases
    assert scalar(migrated_db, "SELECT to_regclass('v2.source')") is None


def test_legacy_public_objects_are_unchanged_through_0001_0002_0001_0002(legacy_probe, alembic_cfg):
    baseline = snapshot_non_v2(legacy_probe)
    for target, direction in (("0001", command.upgrade), ("0002", command.upgrade),
                              ("0001", command.downgrade), ("0002", command.upgrade)):
        direction(alembic_cfg(), target)
        assert snapshot_non_v2(legacy_probe) == baseline, f"changed at {direction.__name__} {target}"


def test_alembic_scope_stays_v2_only_with_the_new_table(legacy_probe, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.check(alembic_cfg())  # the real env.py autogenerate path: no drift, no legacy tables in the diff


def test_exact_v2_source_schema(migrated_db):
    assert rows(migrated_db, """
        SELECT column_name, data_type, is_nullable, is_identity, coalesce(identity_generation, '')
        FROM information_schema.columns WHERE table_schema = 'v2' AND table_name = 'source' ORDER BY ordinal_position
    """) == [
        ("id", "bigint", "NO", "YES", "ALWAYS"),
        ("source_key", "text", "NO", "NO", ""),
        ("source_name", "text", "NO", "NO", ""),
        ("source_type", "text", "NO", "NO", ""),
        ("collection_method", "text", "NO", "NO", ""),
        ("source_url", "text", "YES", "NO", ""),
        ("is_active", "boolean", "NO", "NO", ""),
        ("created_at", "timestamp with time zone", "NO", "NO", ""),
        ("updated_at", "timestamp with time zone", "NO", "NO", ""),
        ("is_test", "boolean", "NO", "NO", ""),  # Revision 0011: synthetic/test evidence marker, default false
    ]
    assert rows(migrated_db, """
        SELECT conname, contype::text FROM pg_constraint
        WHERE conrelid = 'v2.source'::regclass AND contype IN ('p','u','c','f') ORDER BY conname
    """) == [
        ("ck_source_collection_method_allowed", "c"),
        ("ck_source_source_key_shape", "c"),
        ("ck_source_source_name_valid", "c"),
        ("ck_source_source_type_allowed", "c"),
        ("ck_source_source_url_valid", "c"),
        ("ck_source_updated_not_before_created", "c"),
        ("pk_source", "p"),
        ("uq_source_source_key", "u"),
    ]
    triggers = rows(migrated_db, "SELECT tgname, pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid = 'v2.source'::regclass AND NOT tgisinternal")
    assert len(triggers) == 1 and triggers[0][0] == "trg_source_guard"
    assert "BEFORE INSERT OR UPDATE" in triggers[0][1] and "FOR EACH ROW" in triggers[0][1]


def test_source_type_and_collection_method_are_text_with_checks_not_enum_types(migrated_db):
    assert rows(migrated_db, "SELECT typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'v2' AND t.typtype = 'e'") == []
    defs = dict(rows(migrated_db, "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'v2.source'::regclass AND contype = 'c'"))
    from app.v2.domain.source import CollectionMethod, SourceType
    for value in (t.value for t in SourceType):
        assert f"'{value}'" in defs["ck_source_source_type_allowed"]
    for value in (m.value for m in CollectionMethod):
        assert f"'{value}'" in defs["ck_source_collection_method_allowed"]
