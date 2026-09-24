"""Revision 0010: taxonomy_version, market, company_market_classification."""

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.v2.classification import service
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.repositories import markets
from app.v2.tests.db.financing_fakes import canonical_company
from app.v2.tests.db.harness import (
    HEAD_REVISION,
    HEAD_V2_OBJECTS,
    REVISION_0009_V2_OBJECTS,
    REVISION_0010_V2_OBJECTS,
    create_legacy_probe_objects,
    make_alembic_config,
    scalar,
    snapshot_non_v2,
    v2_objects,
)
from app.v2.tests.db.taxonomy_fakes import ME, TV1, setup_taxonomy

pytestmark = pytest.mark.db

NEW_TABLES = ("taxonomy_version", "market", "company_market_classification")


def rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def functions(engine):
    return [r[0] for r in rows(engine, "SELECT proname FROM pg_proc WHERE pronamespace = 'v2'::regnamespace ORDER BY 1")]


def test_0010_is_no_longer_head_but_still_exists_in_history():
    # Revision 0011 (Increment 18.5) is now head; this file's own scope is still exactly revision 0010's
    # objects, tested at that specific revision (REVISION_0010_V2_OBJECTS), not at whatever is currently head.
    assert HEAD_REVISION != "0010"
    script = ScriptDirectory.from_config(make_alembic_config())
    assert script.get_revision("0010") is not None


def test_upgrade_0009_to_0010_creates_only_the_taxonomy_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0009")
    assert v2_objects(clean_db) == REVISION_0009_V2_OBJECTS
    command.upgrade(alembic_cfg(), "0010")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0010"
    assert v2_objects(clean_db) == REVISION_0010_V2_OBJECTS
    added = {"taxonomy_version_stamp", "market_guard", "company_market_classification_guard"}
    assert added <= set(functions(clean_db))


def test_downgrade_0010_to_0009_removes_only_increment_12_objects_and_upgrade_again_works(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0010")
    command.downgrade(alembic_cfg(), "0009")
    assert v2_objects(clean_db) == REVISION_0009_V2_OBJECTS
    assert not {"taxonomy_version_stamp", "market_guard", "company_market_classification_guard"} & set(functions(clean_db))
    command.upgrade(alembic_cfg(), "0010")
    assert v2_objects(clean_db) == REVISION_0010_V2_OBJECTS


@pytest.mark.parametrize("what", ["taxonomy_version_only", "market_only", "classification"])
def test_downgrade_refuses_while_taxonomy_market_or_classification_history_exists(migrated_db, alembic_cfg, what):
    db = migrated_db
    if what == "taxonomy_version_only":
        markets.register_taxonomy_version(db, TV1)
    elif what == "market_only":
        markets.register_market(db, "robotics", "Robotics")
    else:
        taxonomy = setup_taxonomy(db, ("robotics", "Robotics"))
        company = canonical_company(db)
        service.classify_company(db, company, taxonomy["robotics"].id, TV1, ClassificationRole.PRIMARY, ME)
    before = {t: scalar(db, f"SELECT count(*) FROM v2.{t}") for t in NEW_TABLES}
    with pytest.raises(DBAPIError) as info:
        command.downgrade(alembic_cfg(), "0009")
    assert "refusing to downgrade 0010" in str(info.value.orig)
    assert scalar(db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION and v2_objects(db) == HEAD_V2_OBJECTS
    assert {t: scalar(db, f"SELECT count(*) FROM v2.{t}") for t in NEW_TABLES} == before
    with pytest.raises(DBAPIError):
        command.downgrade(alembic_cfg(), "base")


def test_tables_are_labelled(migrated_db):
    for table, word in (("taxonomy_version", "Classification always names one"), ("market", "not a profile"),
                        ("company_market_classification", "never AI")):
        assert word in scalar(migrated_db, "SELECT obj_description(to_regclass(:t)::oid, 'pg_class')", t=f"v2.{table}")


def test_constraint_and_trigger_inventory(migrated_db):
    def constraints(table):
        return [r[0] for r in rows(migrated_db, f"SELECT conname FROM pg_constraint WHERE conrelid='v2.{table}'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")]
    assert constraints("taxonomy_version") == ["ck_taxonomy_version_shape", "pk_taxonomy_version"]
    assert constraints("market") == ["ck_market_display_name_valid", "ck_market_slug_shape", "pk_market", "uq_market_slug"]
    assert constraints("company_market_classification") == [
        "ck_cmc_actor_human", "ck_cmc_actor_is_not_ai", "ck_cmc_actor_rule", "ck_cmc_authority_allowed", "ck_cmc_role_allowed",
        "fk_cmc_company_id", "fk_cmc_market_id", "fk_cmc_taxonomy_version", "pk_company_market_classification",
        "uq_cmc_company_market_version"]
    expected = sorted([f"trg_{t}_{k}" for t in NEW_TABLES for k in ("append_only", "no_truncate")]
                      + ["trg_company_market_classification_guard", "trg_market_guard", "trg_taxonomy_version_stamp"])
    assert [r[0] for r in rows(migrated_db, "SELECT tgname FROM pg_trigger WHERE tgrelid::regclass::text IN "
                                            "('v2.taxonomy_version', 'v2.market', 'v2.company_market_classification') "
                                            "AND NOT tgisinternal ORDER BY 1")] == expected


def test_metadata_matches_the_migration_alembic_check_is_clean(migrated_db, alembic_cfg):
    command.check(alembic_cfg())


def test_legacy_objects_are_untouched_in_both_directions(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0009")
    create_legacy_probe_objects(clean_db)
    baseline = snapshot_non_v2(clean_db)
    command.upgrade(alembic_cfg(), "head")
    assert snapshot_non_v2(clean_db) == baseline
    command.downgrade(alembic_cfg(), "0009")
    assert snapshot_non_v2(clean_db) == baseline


def test_history_is_linear_and_earlier_revisions_are_intact():
    script = ScriptDirectory.from_config(make_alembic_config())
    assert [r.revision for r in script.walk_revisions()] == ["0011", "0010", "0009", "0008", "0007", "0006", "0005", "0004", "0003", "0002", "0001"]
    assert script.get_revision("0010").down_revision == "0009"
