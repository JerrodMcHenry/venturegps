"""Revision 0006 (v2.company_candidate, v2.company_candidate_identifier)."""

import io

import pytest
from alembic import command
from sqlalchemy import text

from app.v2.repositories import processing_attempts as attempts
from app.v2.repositories.company_candidates import store_company_candidates
from app.v2.tests.db.candidate_fakes import PAGE, PROC, V1, make_proposal
from app.v2.tests.db.evidence_helpers import ingest_one
from app.v2.tests.db.harness import (
    HEAD_REVISION,
    HEAD_V2_OBJECTS,
    REVISION_0005_V2_OBJECTS,
    REVISION_0006_V2_OBJECTS,
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


def test_head_is_at_least_0006():
    assert HEAD_REVISION >= "0006"


def test_upgrade_0005_to_0006_creates_only_the_candidate_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0005")
    assert v2_objects(clean_db) == REVISION_0005_V2_OBJECTS
    command.upgrade(alembic_cfg(), "0006")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0006"
    assert v2_objects(clean_db) == REVISION_0006_V2_OBJECTS
    assert functions(clean_db) == ["company_candidate_guard", "company_candidate_identifier_guard", "forbid_evidence_change",
                                   "observation_stamp", "processing_attempt_guard", "source_guard"]


def test_downgrade_0006_to_0005_removes_only_increment_8_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0006")
    command.downgrade(alembic_cfg(), "0005")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0005"
    assert v2_objects(clean_db) == REVISION_0005_V2_OBJECTS
    assert functions(clean_db) == ["forbid_evidence_change", "observation_stamp", "processing_attempt_guard", "source_guard"]


def test_upgrade_again_after_downgrade(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.downgrade(alembic_cfg(), "0005")
    command.upgrade(alembic_cfg(), "head")
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS


def test_downgrade_refuses_to_discard_candidate_history_and_rolls_back_completely(migrated_db, alembic_cfg):
    observation = ingest_one(migrated_db, payload=PAGE).observation
    attempt = attempts.start_processing(migrated_db, observation.id, PROC, V1)
    store_company_candidates(migrated_db, attempt.id, [make_proposal(PAGE, "Acme Robotics", domain="acmerobotics.com")])
    with pytest.raises(Exception, match="contains candidate history"):
        command.downgrade(alembic_cfg(), "0005")
    assert scalar(migrated_db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION
    assert scalar(migrated_db, "SELECT count(*) FROM v2.company_candidate") == 1
    assert scalar(migrated_db, "SELECT count(*) FROM v2.company_candidate_identifier") == 1
    assert v2_objects(migrated_db) == HEAD_V2_OBJECTS


def test_downgrade_works_with_processing_history_but_no_candidates(migrated_db, alembic_cfg):
    observation = ingest_one(migrated_db, payload=PAGE).observation
    attempts.start_processing(migrated_db, observation.id, PROC, V1)
    command.downgrade(alembic_cfg(), "0005")
    assert scalar(migrated_db, "SELECT count(*) FROM v2.processing_attempt") == 1


def test_legacy_public_objects_are_unchanged_through_0005_0006_0005_0006(legacy_probe, alembic_cfg):
    baseline = snapshot_non_v2(legacy_probe)
    for target, direction in (("0005", command.upgrade), ("0006", command.upgrade),
                              ("0005", command.downgrade), ("0006", command.upgrade)):
        direction(alembic_cfg(), target)
        assert snapshot_non_v2(legacy_probe) == baseline, f"changed at {direction.__name__} {target}"


def test_alembic_scope_stays_v2_only_and_metadata_matches_the_database(legacy_probe, alembic_cfg):
    command.upgrade(alembic_cfg(), "head")
    command.check(alembic_cfg())


def test_offline_sql_for_0006_is_valid_and_v2_only(alembic_cfg):
    up, down = io.StringIO(), io.StringIO()
    cfg = alembic_cfg(); cfg.output_buffer = up
    command.upgrade(cfg, "0005:0006", sql=True)
    sql = up.getvalue()
    assert "CREATE TABLE v2.company_candidate " in sql and "CREATE TABLE v2.company_candidate_identifier" in sql
    assert "trg_company_candidate_guard" in sql and "public" not in sql
    cfg = alembic_cfg(); cfg.output_buffer = down
    command.downgrade(cfg, "0006:0005", sql=True)
    assert "DROP TABLE v2.company_candidate" in down.getvalue() and "DROP FUNCTION v2.company_candidate_guard()" in down.getvalue()


def test_exact_candidate_schema(migrated_db):
    assert rows(migrated_db, """SELECT column_name, data_type, is_nullable, is_identity FROM information_schema.columns
        WHERE table_schema='v2' AND table_name='company_candidate' ORDER BY ordinal_position""") == [
        ("id", "bigint", "NO", "YES"), ("processing_attempt_id", "bigint", "NO", "NO"), ("candidate_ordinal", "integer", "NO", "NO"),
        ("proposed_name", "text", "NO", "NO"), ("name_evidence_start", "integer", "NO", "NO"), ("name_evidence_end", "integer", "NO", "NO"),
        ("name_evidence_hash", "text", "NO", "NO"), ("created_at", "timestamp with time zone", "NO", "NO"),
    ]
    assert rows(migrated_db, """SELECT column_name, data_type, is_nullable FROM information_schema.columns
        WHERE table_schema='v2' AND table_name='company_candidate_identifier' ORDER BY ordinal_position""") == [
        ("id", "bigint", "NO"), ("candidate_id", "bigint", "NO"), ("identifier_ordinal", "integer", "NO"), ("identifier_type", "text", "NO"),
        ("identifier_value", "text", "NO"), ("evidence_start", "integer", "NO"), ("evidence_end", "integer", "NO"), ("evidence_hash", "text", "NO"),
    ]
    assert [r[0] for r in rows(migrated_db, "SELECT conname FROM pg_constraint WHERE conrelid='v2.company_candidate'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")] == [
        "ck_company_candidate_name_evidence_hash_shape", "ck_company_candidate_name_evidence_span", "ck_company_candidate_ordinal_range",
        "ck_company_candidate_proposed_name_valid", "fk_company_candidate_processing_attempt_id_processing_attempt",
        "pk_company_candidate", "uq_company_candidate_ordinal",
    ]
    assert [r[0] for r in rows(migrated_db, "SELECT conname FROM pg_constraint WHERE conrelid='v2.company_candidate_identifier'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")] == [
        "ck_company_candidate_identifier_evidence_hash_shape", "ck_company_candidate_identifier_evidence_span",
        "ck_company_candidate_identifier_ordinal_range", "ck_company_candidate_identifier_type_allowed",
        "ck_company_candidate_identifier_value_valid", "fk_company_candidate_identifier_candidate_id_company_candidate",
        "pk_company_candidate_identifier", "uq_company_candidate_identifier_ordinal", "uq_company_candidate_identifier_value",
    ]
    for fk in ("fk_company_candidate_processing_attempt_id_processing_attempt", "fk_company_candidate_identifier_candidate_id_company_candidate"):
        assert "ON DELETE RESTRICT" in scalar(migrated_db, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n", n=fk)
    assert [r[0] for r in rows(migrated_db, "SELECT tgname FROM pg_trigger WHERE tgrelid IN ('v2.company_candidate'::regclass, 'v2.company_candidate_identifier'::regclass) AND NOT tgisinternal ORDER BY 1")] == [
        "trg_company_candidate_append_only", "trg_company_candidate_guard", "trg_company_candidate_identifier_append_only",
        "trg_company_candidate_identifier_guard", "trg_company_candidate_identifier_no_truncate", "trg_company_candidate_no_truncate"]


def test_candidate_tables_are_labelled_untrusted_and_no_canonical_tables_exist(migrated_db):
    for table in ("company_candidate", "company_candidate_identifier"):
        assert "UNTRUSTED" in scalar(migrated_db, "SELECT obj_description(to_regclass(:t)::oid, 'pg_class')", t=f"v2.{table}")
    names = {r[0] for r in rows(migrated_db, "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'v2' AND c.relkind = 'r'")}
    # Increment 9 legitimately added the resolution boundary and canonical identity; nothing beyond it exists.
    assert names == {"alembic_version", "source", "raw_payload", "observation", "observation_sighting", "processing_attempt",
                     "company_candidate", "company_candidate_identifier",
                     "company", "company_name", "company_identifier", "resolution_decision",
                     "financing_event_candidate", "financing_event_candidate_amount", "financing_event_candidate_date",
                     "financing_event", "financing_resolution_decision", "financing_event_stage", "financing_event_type",
                     "financing_event_verified_round_amount", "financing_event_date",
                     "company_market_classification", "market", "taxonomy_version",
                     "collection_run"}
    # Increment 12 legitimately added market/taxonomy_version/company_market_classification.
    # Increment 18.5 legitimately added collection_run -- operational job history, not evidence, a candidate,
    # or a canonical fact; it carries no confidence/score/model/canonical/company_id/etc. column either (see
    # the next test), so it does not weaken what this test actually guards against.
    for forbidden in ("claim", "evidence_link", "identifier_claim", "merge"):
        assert not any(forbidden == n or n.startswith(forbidden + "_") or n.endswith("_" + forbidden) for n in names), forbidden


def test_the_candidate_tables_carry_no_ai_or_canonical_columns(migrated_db):
    columns = {r[0] for r in rows(migrated_db, "SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name IN ('company_candidate','company_candidate_identifier')")}
    for word in ("confidence", "score", "model", "provider", "prompt", "reasoning", "response", "canonical", "company_id", "resolved",
                 "accepted", "verified", "trusted", "claim", "updated", "status", "quote", "excerpt", "raw", "payload", "observation", "processor", "version", "attempt_number"):
        assert not any(word in c for c in columns), word
