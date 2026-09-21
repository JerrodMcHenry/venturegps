"""Revision 0005 (v2.processing_attempt): stepwise migration, exact schema, legacy untouched."""

import io

import pytest
from alembic import command
from sqlalchemy import text

from app.v2.repositories import processing_attempts as attempts
from app.v2.tests.db.evidence_helpers import ingest_one
from app.v2.tests.db.harness import (
    HEAD_REVISION,
    HEAD_V2_OBJECTS,
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


def test_head_is_0005():
    assert HEAD_REVISION == "0005"


def test_upgrade_0004_to_0005_creates_only_the_processing_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0004")
    assert v2_objects(clean_db) == REVISION_0004_V2_OBJECTS
    command.upgrade(alembic_cfg(), "0005")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0005"
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS
    assert functions(clean_db) == ["forbid_evidence_change", "observation_stamp", "processing_attempt_guard", "source_guard"]


def test_downgrade_0005_to_0004_removes_only_increment_7_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "0004")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0004"
    assert v2_objects(clean_db) == REVISION_0004_V2_OBJECTS
    assert functions(clean_db) == ["forbid_evidence_change", "observation_stamp", "source_guard"]


def test_upgrade_again_after_downgrade(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "0004")
    command.upgrade(alembic_cfg(), "head")
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS


def test_downgrade_refuses_to_discard_processing_history_and_rolls_back_completely(migrated_db, alembic_cfg):
    observation = ingest_one(migrated_db).observation
    attempts.start_processing(migrated_db, observation.id, "fin_extractor", "fin_extractor.v1")
    with pytest.raises(Exception, match="contains processing history"):
        command.downgrade(alembic_cfg(), "0004")
    assert scalar(migrated_db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION
    assert scalar(migrated_db, "SELECT count(*) FROM v2.processing_attempt") == 1
    assert v2_objects(migrated_db) == HEAD_V2_OBJECTS


def test_downgrade_works_with_evidence_but_no_processing_history(migrated_db, alembic_cfg):
    ingest_one(migrated_db)
    command.downgrade(alembic_cfg(), "0004")
    assert scalar(migrated_db, "SELECT count(*) FROM v2.observation_sighting") == 1


def test_legacy_public_objects_are_unchanged_through_0004_0005_0004_0005(legacy_probe, alembic_cfg):
    baseline = snapshot_non_v2(legacy_probe)
    for target, direction in (("0004", command.upgrade), ("0005", command.upgrade),
                              ("0004", command.downgrade), ("0005", command.upgrade)):
        direction(alembic_cfg(), target)
        assert snapshot_non_v2(legacy_probe) == baseline, f"changed at {direction.__name__} {target}"


def test_alembic_scope_stays_v2_only_and_metadata_matches_the_database(legacy_probe, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.check(alembic_cfg())


def test_offline_sql_for_0005_is_valid_and_v2_only(alembic_cfg):
    up, down = io.StringIO(), io.StringIO()
    cfg = alembic_cfg(); cfg.output_buffer = up
    command.upgrade(cfg, "0004:0005", sql=True)
    sql = up.getvalue()
    assert "CREATE TABLE v2.processing_attempt" in sql and "processing_attempt_guard" in sql
    assert "uq_processing_attempt_one_active" in sql and "public" not in sql
    cfg = alembic_cfg(); cfg.output_buffer = down
    command.downgrade(cfg, "0005:0004", sql=True)
    assert "DROP TABLE v2.processing_attempt" in down.getvalue() and "DROP FUNCTION v2.processing_attempt_guard()" in down.getvalue()
    assert "forbid_evidence_change" not in down.getvalue().replace("DROP FUNCTION v2.forbid_evidence_change", "")  # 0003's function stays


def test_exact_processing_attempt_schema(migrated_db):
    assert rows(migrated_db, """SELECT column_name, data_type, is_nullable, is_identity FROM information_schema.columns
        WHERE table_schema='v2' AND table_name='processing_attempt' ORDER BY ordinal_position""") == [
        ("id", "bigint", "NO", "YES"), ("observation_id", "bigint", "NO", "NO"), ("processor_id", "text", "NO", "NO"),
        ("processor_version", "text", "NO", "NO"), ("attempt_number", "integer", "NO", "NO"), ("status", "text", "NO", "NO"),
        ("started_at", "timestamp with time zone", "NO", "NO"), ("finished_at", "timestamp with time zone", "YES", "NO"),
        ("lease_expires_at", "timestamp with time zone", "YES", "NO"), ("reason_code", "text", "YES", "NO"), ("detail_code", "text", "YES", "NO"),
    ]
    assert [r[0] for r in rows(migrated_db, "SELECT conname FROM pg_constraint WHERE conrelid='v2.processing_attempt'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")] == [
        "ck_processing_attempt_attempt_number_positive", "ck_processing_attempt_detail_code_shape",
        "ck_processing_attempt_finished_not_before_started", "ck_processing_attempt_processor_id_shape",
        "ck_processing_attempt_processor_version_shape", "ck_processing_attempt_reason_code_shape",
        "ck_processing_attempt_state_shape", "ck_processing_attempt_status_allowed",
        "fk_processing_attempt_observation_id_observation", "pk_processing_attempt", "uq_processing_attempt_number",
    ]
    assert "ON DELETE RESTRICT" in scalar(migrated_db, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'fk_processing_attempt_observation_id_observation'")
    assert scalar(migrated_db, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'uq_processing_attempt_number'") == "UNIQUE (observation_id, processor_id, attempt_number)"
    index = scalar(migrated_db, "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_processing_attempt_one_active'")
    assert "UNIQUE" in index and "(observation_id, processor_id)" in index and "status = 'processing'" in index
    assert [r[0] for r in rows(migrated_db, "SELECT tgname FROM pg_trigger WHERE tgrelid='v2.processing_attempt'::regclass AND NOT tgisinternal ORDER BY 1")] == [
        "trg_processing_attempt_guard", "trg_processing_attempt_no_delete", "trg_processing_attempt_no_truncate"]


def test_processing_attempt_carries_no_evidence_ai_or_candidate_columns(migrated_db):
    columns = {r[0] for r in rows(migrated_db, "SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='processing_attempt'")}
    for word in ("payload", "bytes", "hash", "excerpt", "message", "exception", "trace", "prompt", "model", "ai_", "response",
                 "confidence", "candidate", "company", "score", "observed", "recorded", "source"):
        assert not any(word in c for c in columns), word
    # and the evidence tables gained no processing column
    obs_columns = {r[0] for r in rows(migrated_db, "SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='observation'")}
    assert not any(w in c for c in obs_columns for w in ("status", "attempt", "processing", "lease"))
