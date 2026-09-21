"""Revision 0003 (v2.raw_payload, v2.observation): stepwise migration, exact schema, legacy untouched."""

import io

import pytest
from alembic import command
from sqlalchemy import text

from app.v2.domain.payload import MAX_INLINE_PAYLOAD_BYTES
from app.v2.repositories import observations as obs_repo
from app.v2.tests.db.evidence_helpers import make_observation, register_source, store_payload
from app.v2.tests.db.harness import (
    HEAD_REVISION,
    HEAD_V2_OBJECTS,
    REVISION_0002_V2_OBJECTS,
    REVISION_0003_V2_OBJECTS,
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


def test_upgrade_0002_to_0003_creates_only_the_evidence_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0002")
    assert v2_objects(clean_db) == REVISION_0002_V2_OBJECTS

    command.upgrade(alembic_cfg(), "0003")

    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0003"
    assert v2_objects(clean_db) == REVISION_0003_V2_OBJECTS  # no sighting, processing, candidate, company... tables
    assert functions(clean_db) == ["forbid_evidence_change", "observation_stamp", "source_guard"]


def test_downgrade_0003_to_0002_removes_only_increment_5_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "0002")

    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0002"
    assert v2_objects(clean_db) == REVISION_0002_V2_OBJECTS
    assert functions(clean_db) == ["source_guard"]
    assert scalar(clean_db, "SELECT to_regclass('v2.source')") is not None  # 0002 intact


def test_upgrade_again_after_downgrade(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "0002")
    command.upgrade(alembic_cfg(), "head")
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS


def test_legacy_public_objects_are_unchanged_through_0002_0003_0002_0003(legacy_probe, alembic_cfg):
    baseline = snapshot_non_v2(legacy_probe)
    for target, direction in (("0002", command.upgrade), ("0003", command.upgrade),
                              ("0002", command.downgrade), ("0003", command.upgrade)):
        direction(alembic_cfg(), target)
        assert snapshot_non_v2(legacy_probe) == baseline, f"changed at {direction.__name__} {target}"


def test_alembic_scope_stays_v2_only_and_metadata_matches_the_database(legacy_probe, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.check(alembic_cfg())


def test_offline_sql_for_0003_is_valid_and_v2_only(alembic_cfg):
    up = io.StringIO()
    cfg = alembic_cfg()
    cfg.output_buffer = up
    command.upgrade(cfg, "0002:0003", sql=True)
    sql = up.getvalue()
    assert "CREATE TABLE v2.raw_payload" in sql and "CREATE TABLE v2.observation" in sql
    assert "trg_observation_append_only" in sql and "BEFORE TRUNCATE ON v2.observation" in sql
    assert "public" not in sql and "sighting" not in sql.lower()


def test_exact_raw_payload_schema(migrated_db):
    assert rows(migrated_db, """SELECT column_name, data_type, is_nullable FROM information_schema.columns
        WHERE table_schema='v2' AND table_name='raw_payload' ORDER BY ordinal_position""") == [
        ("content_hash", "text", "NO"), ("storage_kind", "text", "NO"), ("size_bytes", "bigint", "NO"), ("payload_bytes", "bytea", "YES"),
    ]
    assert [r[0] for r in rows(migrated_db, "SELECT conname FROM pg_constraint WHERE conrelid='v2.raw_payload'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")] == [
        "ck_raw_payload_content_hash_shape", "ck_raw_payload_hash_matches_bytes", "ck_raw_payload_inline_bytes_present",
        "ck_raw_payload_size_matches_bytes", "ck_raw_payload_size_within_limit", "ck_raw_payload_storage_kind_allowed", "pk_raw_payload",
    ]
    assert [r[0] for r in rows(migrated_db, "SELECT tgname FROM pg_trigger WHERE tgrelid='v2.raw_payload'::regclass AND NOT tgisinternal ORDER BY 1")] == [
        "trg_raw_payload_append_only", "trg_raw_payload_no_truncate"]


def test_exact_observation_schema(migrated_db):
    assert rows(migrated_db, """SELECT column_name, data_type, is_nullable, is_identity FROM information_schema.columns
        WHERE table_schema='v2' AND table_name='observation' ORDER BY ordinal_position""") == [
        ("id", "bigint", "NO", "YES"), ("source_id", "bigint", "NO", "NO"), ("source_record_identifier", "text", "YES", "NO"),
        ("observation_type", "text", "NO", "NO"), ("event_time", "timestamp with time zone", "YES", "NO"),
        ("event_time_precision", "text", "YES", "NO"), ("observed_time", "timestamp with time zone", "NO", "NO"),
        ("recorded_time", "timestamp with time zone", "NO", "NO"), ("collection_version", "text", "NO", "NO"),
        ("collector_id", "text", "NO", "NO"), ("content_hash", "text", "NO", "NO"),
        ("declared_media_type", "text", "YES", "NO"), ("sniffed_media_type", "text", "NO", "NO"),
    ]
    assert [r[0] for r in rows(migrated_db, "SELECT conname FROM pg_constraint WHERE conrelid='v2.observation'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")] == [
        "ck_observation_collection_version_shape", "ck_observation_collector_id_shape", "ck_observation_declared_media_type_shape",
        "ck_observation_event_time_paired", "ck_observation_event_time_precision_allowed",
        "ck_observation_event_time_start_matches_precision", "ck_observation_observation_type_shape",
        "ck_observation_sniffed_media_type_allowed", "ck_observation_source_record_identifier_valid",
        "fk_observation_content_hash_raw_payload", "fk_observation_source_id_source", "pk_observation",
    ]
    fks = dict(rows(migrated_db, "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='v2.observation'::regclass AND contype='f'"))
    assert all("ON DELETE RESTRICT" in d for d in fks.values())
    assert [r[0] for r in rows(migrated_db, "SELECT tgname FROM pg_trigger WHERE tgrelid='v2.observation'::regclass AND NOT tgisinternal ORDER BY 1")] == [
        "trg_observation_append_only", "trg_observation_no_truncate", "trg_observation_stamp"]
    assert [r[0] for r in rows(migrated_db, "SELECT indexname FROM pg_indexes WHERE schemaname='v2' AND tablename='observation' ORDER BY 1")] == [
        "pk_observation", "uq_observation_dedup_with_record_id", "uq_observation_dedup_without_record_id"]


def test_observation_has_no_status_ai_company_or_interpretation_columns(migrated_db):
    columns = {r[0] for r in rows(migrated_db, "SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='observation'")}
    for word in ("status", "state", "attempt", "ai_", "model", "prompt", "confidence", "score", "company", "summary", "interpret", "agreement", "mismatch", "updated"):
        assert not any(word in c for c in columns), word


def test_the_size_limit_in_the_database_is_the_domain_constant(migrated_db):
    definition = scalar(migrated_db, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_raw_payload_size_within_limit'")
    assert str(MAX_INLINE_PAYLOAD_BYTES) in definition


def test_downgrade_refuses_to_discard_evidence_and_rolls_back_completely(migrated_db, alembic_cfg):
    register_source(migrated_db)
    digest = store_payload(migrated_db, b"evidence")
    with pytest.raises(Exception, match="contain evidence"):
        command.downgrade(alembic_cfg(), "0002")
    assert scalar(migrated_db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION
    assert scalar(migrated_db, "SELECT count(*) FROM v2.raw_payload WHERE content_hash = :h", h=digest) == 1  # a payload alone is evidence too

    obs_repo.store_observation(migrated_db, make_observation(digest))
    with pytest.raises(Exception, match="contain evidence"):
        command.downgrade(alembic_cfg(), "base")
    assert scalar(migrated_db, "SELECT count(*) FROM v2.observation") == 1
    assert v2_objects(migrated_db) == HEAD_V2_OBJECTS


def test_downgrade_works_when_no_evidence_exists_even_with_sources(migrated_db, alembic_cfg):
    register_source(migrated_db)
    command.downgrade(alembic_cfg(), "0002")
    assert scalar(migrated_db, "SELECT count(*) FROM v2.source") == 1
