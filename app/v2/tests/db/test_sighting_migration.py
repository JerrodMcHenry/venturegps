"""Revision 0004 (v2.observation_sighting): stepwise migration, exact schema, legacy untouched."""

import io

import pytest
from alembic import command
from sqlalchemy import text

from app.v2.ingestion.service import ingest_evidence
from app.v2.tests.db.evidence_helpers import make_command, register_source
from app.v2.tests.db.harness import (
    HEAD_REVISION,
    HEAD_V2_OBJECTS,
    REVISION_0003_V2_OBJECTS,
    REVISION_0004_V2_OBJECTS,
    scalar,
    snapshot_non_v2,
    v2_objects,
)

pytestmark = pytest.mark.db


def rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def functions(engine):
    return [r[0] for r in rows(engine, "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'v2' ORDER BY 1")]


def test_head_moved_past_0004():
    assert HEAD_REVISION >= "0004"


def test_upgrade_0003_to_0004_creates_only_the_sighting_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0003")
    assert v2_objects(clean_db) == REVISION_0003_V2_OBJECTS
    functions_before = functions(clean_db)

    command.upgrade(alembic_cfg(), "0004")

    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0004"
    assert v2_objects(clean_db) == REVISION_0004_V2_OBJECTS
    assert functions(clean_db) == functions_before == ["forbid_evidence_change", "observation_stamp", "source_guard"]  # reused, none added


def test_downgrade_0004_to_0003_removes_only_increment_6_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "0003")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0003"
    assert v2_objects(clean_db) == REVISION_0003_V2_OBJECTS
    assert functions(clean_db) == ["forbid_evidence_change", "observation_stamp", "source_guard"]  # 0003's functions still needed


def test_upgrade_again_after_downgrade(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "0003")
    command.upgrade(alembic_cfg(), "head")
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS


def test_downgrade_refuses_to_discard_sightings_and_rolls_back_completely(migrated_db, alembic_cfg):
    register_source(migrated_db)
    ingest_evidence(migrated_db, make_command())
    with pytest.raises(Exception, match="observation_sighting contains evidence"):
        command.downgrade(alembic_cfg(), "0003")
    assert scalar(migrated_db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION
    assert scalar(migrated_db, "SELECT count(*) FROM v2.observation_sighting") == 1
    assert v2_objects(migrated_db) == HEAD_V2_OBJECTS


def test_downgrade_still_works_when_there_are_observations_but_no_sightings(migrated_db, alembic_cfg):
    from app.v2.repositories.observations import store_observation
    from app.v2.tests.db.evidence_helpers import make_observation, store_payload
    register_source(migrated_db)
    store_observation(migrated_db, make_observation(store_payload(migrated_db, b"x")))  # Increment 5 primitive: no sighting
    command.downgrade(alembic_cfg(), "0003")
    assert scalar(migrated_db, "SELECT count(*) FROM v2.observation") == 1


def test_legacy_public_objects_are_unchanged_through_0003_0004_0003_0004(legacy_probe, alembic_cfg):
    baseline = snapshot_non_v2(legacy_probe)
    for target, direction in (("0003", command.upgrade), ("0004", command.upgrade),
                              ("0003", command.downgrade), ("0004", command.upgrade)):
        direction(alembic_cfg(), target)
        assert snapshot_non_v2(legacy_probe) == baseline, f"changed at {direction.__name__} {target}"


def test_alembic_scope_stays_v2_only_and_metadata_matches_the_database(legacy_probe, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.check(alembic_cfg())


def test_offline_sql_for_0004_is_valid_and_v2_only(alembic_cfg):
    buffer = io.StringIO()
    cfg = alembic_cfg()
    cfg.output_buffer = buffer
    command.upgrade(cfg, "0003:0004", sql=True)
    sql = buffer.getvalue()
    assert "CREATE TABLE v2.observation_sighting" in sql and "trg_observation_sighting_append_only" in sql
    assert "CREATE FUNCTION" not in sql and "public" not in sql
    down = io.StringIO()
    cfg = alembic_cfg()
    cfg.output_buffer = down
    command.downgrade(cfg, "0004:0003", sql=True)
    assert "DROP TABLE v2.observation_sighting" in down.getvalue() and "DROP FUNCTION" not in down.getvalue()


def test_exact_sighting_schema(migrated_db):
    assert rows(migrated_db, """SELECT column_name, data_type, is_nullable, is_identity FROM information_schema.columns
        WHERE table_schema='v2' AND table_name='observation_sighting' ORDER BY ordinal_position""") == [
        ("id", "bigint", "NO", "YES"), ("observation_id", "bigint", "NO", "NO"),
        ("observed_time", "timestamp with time zone", "NO", "NO"), ("recorded_time", "timestamp with time zone", "NO", "NO"),
        ("collector_id", "text", "NO", "NO"), ("collection_version", "text", "NO", "NO"), ("acquisition_key", "text", "NO", "NO"),
    ]
    assert [r[0] for r in rows(migrated_db, "SELECT conname FROM pg_constraint WHERE conrelid='v2.observation_sighting'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")] == [
        "ck_observation_sighting_acquisition_key_shape", "ck_observation_sighting_collection_version_shape",
        "ck_observation_sighting_collector_id_shape", "fk_observation_sighting_observation_id_observation",
        "pk_observation_sighting", "uq_observation_sighting_acquisition",
    ]
    fk = scalar(migrated_db, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'fk_observation_sighting_observation_id_observation'")
    assert "ON DELETE RESTRICT" in fk
    assert scalar(migrated_db, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'uq_observation_sighting_acquisition'") == "UNIQUE (observation_id, acquisition_key)"
    assert [r[0] for r in rows(migrated_db, "SELECT tgname FROM pg_trigger WHERE tgrelid='v2.observation_sighting'::regclass AND NOT tgisinternal ORDER BY 1")] == [
        "trg_observation_sighting_append_only", "trg_observation_sighting_no_truncate", "trg_observation_sighting_stamp"]


def test_sighting_has_no_payload_source_status_ai_or_interpretation_columns(migrated_db):
    columns = {r[0] for r in rows(migrated_db, "SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='observation_sighting'")}
    for word in ("payload", "bytes", "hash", "source", "status", "state", "attempt", "ai_", "model", "confidence", "score", "company", "updated", "summary"):
        assert not any(word in c for c in columns), word
