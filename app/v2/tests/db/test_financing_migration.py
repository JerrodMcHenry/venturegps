"""Revision 0008: financing-event candidates (untrusted proposals; no canonical financing table)."""

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.v2.repositories import financing_event_candidates as repo
from app.v2.tests.db.evidence_helpers import count
from app.v2.tests.db.financing_fakes import FORM_D, canonical_company, form_d, start_attempt
from app.v2.tests.db.harness import (
    HEAD_REVISION,
    HEAD_V2_OBJECTS,
    REVISION_0007_V2_OBJECTS,
    REVISION_0008_V2_OBJECTS,
    create_legacy_probe_objects,
    make_alembic_config,
    scalar,
    snapshot_non_v2,
    v2_objects,
)

pytestmark = pytest.mark.db


def rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def functions(engine):
    return [r[0] for r in rows(engine, "SELECT proname FROM pg_proc WHERE pronamespace = 'v2'::regnamespace ORDER BY 1")]


def test_head_is_at_least_0008():
    assert HEAD_REVISION >= "0008"


def test_upgrade_0007_to_0008_creates_only_the_financing_candidate_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0007")
    assert v2_objects(clean_db) == REVISION_0007_V2_OBJECTS
    command.upgrade(alembic_cfg(), "0008")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0008"
    assert v2_objects(clean_db) == REVISION_0008_V2_OBJECTS
    added = set(functions(clean_db)) - {"company_candidate_guard", "company_candidate_identifier_guard", "company_guard", "company_identifier_guard",
                                        "company_name_guard", "company_requires_provenance", "forbid_evidence_change", "normalize_company_identifier",
                                        "observation_stamp", "processing_attempt_guard", "resolution_decision_guard", "source_guard"}
    assert added == {"evidence_span_matches", "financing_event_candidate_guard", "financing_event_candidate_amount_guard", "financing_event_candidate_date_guard"}


def test_downgrade_0008_to_0007_removes_only_increment_10_objects_and_upgrade_again_works(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0008")
    command.downgrade(alembic_cfg(), "0007")
    assert v2_objects(clean_db) == REVISION_0007_V2_OBJECTS
    assert not [f for f in functions(clean_db) if "financing" in f or f == "evidence_span_matches"]
    command.upgrade(alembic_cfg(), "head")
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS


@pytest.mark.parametrize("level", ["candidate_only", "with_facts"])
def test_downgrade_refuses_while_financing_candidate_history_exists(migrated_db, alembic_cfg, level):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, FORM_D)
    proposal = form_d(company)
    if level == "candidate_only":
        proposal = proposal.model_copy(update={"amounts": (), "dates": (), "financing_type": None})
    repo.persist_financing_event_candidates(db, attempt.id, [proposal])
    before = {t: count(db, t) for t in ("financing_event_candidate", "financing_event_candidate_amount", "financing_event_candidate_date", "company")}
    with pytest.raises(DBAPIError) as info:
        command.downgrade(alembic_cfg(), "0007")
    assert "refusing to downgrade 0008" in str(info.value.orig)
    assert scalar(db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION and v2_objects(db) == HEAD_V2_OBJECTS
    assert before == {t: count(db, t) for t in before}
    with pytest.raises(DBAPIError):
        command.downgrade(alembic_cfg(), "base")


def test_tables_are_labelled_untrusted_and_no_canonical_financing_object_exists(migrated_db):
    for table in ("financing_event_candidate", "financing_event_candidate_amount", "financing_event_candidate_date"):
        assert "UNTRUSTED" in scalar(migrated_db, "SELECT obj_description(to_regclass(:t)::oid, 'pg_class')", t=f"v2.{table}")
    names = {r[0] for r in rows(migrated_db, "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'v2' AND relkind IN ('r','v','m')")}
    # Increment 11 added canonical financing_event tables; Increment 12 legitimately added market/taxonomy_version/
    # company_market_classification. Nothing about Capital signals/metrics tables (there are none -- metrics are computed,
    # never persisted) or Market Pulse exists.
    assert not {n for n in names if "capital" in n or "signal" in n or "pulse" in n or "metric" in n}
    assert not [f for f in functions(migrated_db) if "promote" in f or "resolve_financing" in f]


def test_constraint_and_trigger_inventory(migrated_db):
    def constraints(table):
        return [r[0] for r in rows(migrated_db, f"SELECT conname FROM pg_constraint WHERE conrelid='v2.{table}'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")]
    assert constraints("financing_event_candidate") == [
        "ck_financing_event_candidate_event_evidence_hash_shape", "ck_financing_event_candidate_event_evidence_span",
        "ck_financing_event_candidate_optional_evidence_shape", "ck_financing_event_candidate_ordinal_range",
        "ck_financing_event_candidate_stage_allowed", "ck_financing_event_candidate_stage_evidence_matches_stage",
        "ck_financing_event_candidate_type_allowed", "ck_financing_event_candidate_type_evidence_matches_type",
        "fk_fec_company_id", "fk_fec_processing_attempt_id", "pk_financing_event_candidate", "uq_financing_event_candidate_ordinal"]
    assert [r[0] for r in rows(migrated_db, "SELECT tgname FROM pg_trigger WHERE tgrelid IN ('v2.financing_event_candidate'::regclass, "
                                            "'v2.financing_event_candidate_amount'::regclass, 'v2.financing_event_candidate_date'::regclass) AND NOT tgisinternal ORDER BY 1")] == sorted(
        f"trg_{t}_{k}" for t in ("financing_event_candidate", "financing_event_candidate_amount", "financing_event_candidate_date")
        for k in ("guard", "append_only", "no_truncate"))


def test_metadata_matches_the_migration_alembic_check_is_clean(migrated_db, alembic_cfg):
    command.check(alembic_cfg())


def test_legacy_objects_are_untouched_in_both_directions(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0007")
    create_legacy_probe_objects(clean_db)
    baseline = snapshot_non_v2(clean_db)
    command.upgrade(alembic_cfg(), "head")
    assert snapshot_non_v2(clean_db) == baseline
    command.downgrade(alembic_cfg(), "0007")
    assert snapshot_non_v2(clean_db) == baseline


def test_history_is_linear_and_earlier_revisions_are_intact():
    script = ScriptDirectory.from_config(make_alembic_config())
    assert [r.revision for r in script.walk_revisions()] == ["0010", "0009", "0008", "0007", "0006", "0005", "0004", "0003", "0002", "0001"]
    assert script.get_revision("0008").down_revision == "0007"
