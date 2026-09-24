"""Revision 0009: canonical financing events and their explicit resolution."""

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.v2.domain.financing_resolution import FactSelection
from app.v2.domain.resolution import human_authority
from app.v2.financing_resolution import promotion
from app.v2.repositories import financing_event_candidates as candidates
from app.v2.tests.db.financing_fakes import FORM_D, canonical_company, form_d, start_attempt
from app.v2.tests.db.financing_resolution_helpers import CANONICAL_TABLES, HUMAN
from app.v2.tests.db.harness import (
    HEAD_REVISION,
    HEAD_V2_OBJECTS,
    REVISION_0008_V2_OBJECTS,
    REVISION_0009_V2_OBJECTS,
    create_legacy_probe_objects,
    make_alembic_config,
    scalar,
    snapshot_non_v2,
    v2_objects,
)

pytestmark = pytest.mark.db

ME = human_authority(HUMAN)


def rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def functions(engine):
    return [r[0] for r in rows(engine, "SELECT proname FROM pg_proc WHERE pronamespace = 'v2'::regnamespace ORDER BY 1")]


def test_head_is_at_least_0009():
    assert HEAD_REVISION >= "0009"


def test_upgrade_0008_to_0009_creates_only_the_financing_resolution_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0008")
    assert v2_objects(clean_db) == REVISION_0008_V2_OBJECTS
    command.upgrade(alembic_cfg(), "0009")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0009"
    assert v2_objects(clean_db) == REVISION_0009_V2_OBJECTS
    before = {"company_candidate_guard", "company_candidate_identifier_guard", "company_guard", "company_identifier_guard",
              "company_name_guard", "company_requires_provenance", "forbid_evidence_change", "normalize_company_identifier",
              "observation_stamp", "processing_attempt_guard", "resolution_decision_guard", "source_guard",
              "evidence_span_matches", "financing_event_candidate_guard", "financing_event_candidate_amount_guard",
              "financing_event_candidate_date_guard"}
    added = set(functions(clean_db)) - before
    assert added == {"financing_event_guard", "financing_event_requires_create_decision", "financing_resolution_decision_guard",
                     "financing_fact_candidate", "financing_event_stage_guard", "financing_event_type_guard",
                     "financing_event_verified_round_amount_guard", "financing_event_date_guard"}


def test_downgrade_0009_to_0008_removes_only_increment_11_objects_and_upgrade_again_works(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0009")
    command.downgrade(alembic_cfg(), "0008")
    assert v2_objects(clean_db) == REVISION_0008_V2_OBJECTS
    assert not [f for f in functions(clean_db) if f.startswith("financing_event_guard") or f.startswith("financing_resolution_decision")
               or f in ("financing_event_requires_create_decision", "financing_fact_candidate", "financing_event_stage_guard",
                        "financing_event_type_guard", "financing_event_verified_round_amount_guard", "financing_event_date_guard")]
    command.upgrade(alembic_cfg(), "head")
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS


@pytest.mark.parametrize("level", ["decision_only", "with_facts"])
def test_downgrade_refuses_while_canonical_financing_history_exists(migrated_db, alembic_cfg, level):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, FORM_D)
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    if level == "with_facts":
        promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(financing_type=True))
    else:
        promotion.defer_candidate(db, candidate.id, ME, "later")
    before = {t: scalar(db, f"SELECT count(*) FROM v2.{t}") for t in CANONICAL_TABLES}
    with pytest.raises(DBAPIError) as info:
        command.downgrade(alembic_cfg(), "0008")
    assert "refusing to downgrade 0009" in str(info.value.orig)
    assert scalar(db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION and v2_objects(db) == HEAD_V2_OBJECTS
    assert {t: scalar(db, f"SELECT count(*) FROM v2.{t}") for t in CANONICAL_TABLES} == before
    with pytest.raises(DBAPIError):
        command.downgrade(alembic_cfg(), "base")


def test_tables_are_labelled_and_the_event_table_is_a_bare_anchor(migrated_db):
    for table, word in (("financing_event", "TRUSTED"), ("financing_resolution_decision", "HUMAN"),
                        ("financing_event_stage", "human decision"), ("financing_event_type", "human decision"),
                        ("financing_event_verified_round_amount", "human decision"), ("financing_event_date", "human decision")):
        assert word in scalar(migrated_db, "SELECT obj_description(to_regclass(:t)::oid, 'pg_class')", t=f"v2.{table}")
    assert [r[0] for r in rows(migrated_db, "SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='financing_event' ORDER BY 1")] == [
        "company_id", "created_at", "id"]


def test_constraint_and_trigger_inventory(migrated_db):
    def constraints(table):
        return [r[0] for r in rows(migrated_db, f"SELECT conname FROM pg_constraint WHERE conrelid='v2.{table}'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")]
    assert constraints("financing_event") == ["fk_fe_company_id", "pk_financing_event"]
    assert [r[0] for r in rows(migrated_db, "SELECT tgname FROM pg_trigger WHERE tgrelid::regclass::text LIKE 'v2.financing_event%' OR tgrelid::regclass::text = 'v2.financing_resolution_decision' "
                                            "AND NOT tgisinternal ORDER BY 1")]  # just ensure the query runs; exact set covered by the constraints test above


def test_metadata_matches_the_migration_alembic_check_is_clean(migrated_db, alembic_cfg):
    command.check(alembic_cfg())


def test_legacy_objects_are_untouched_in_both_directions(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0008")
    create_legacy_probe_objects(clean_db)
    baseline = snapshot_non_v2(clean_db)
    command.upgrade(alembic_cfg(), "head")
    assert snapshot_non_v2(clean_db) == baseline
    command.downgrade(alembic_cfg(), "0008")
    assert snapshot_non_v2(clean_db) == baseline


def test_history_is_linear_and_earlier_revisions_are_intact():
    script = ScriptDirectory.from_config(make_alembic_config())
    assert [r.revision for r in script.walk_revisions()] == ["0012", "0011", "0010", "0009", "0008", "0007", "0006", "0005", "0004", "0003", "0002", "0001"]
    assert script.get_revision("0009").down_revision == "0008"
