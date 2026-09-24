"""Revision 0007: resolution decisions and canonical Company identity."""

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.v2.domain.candidate import IdentifierType
from app.v2.domain.company import normalize_domain, normalize_website_url
from app.v2.domain.resolution import human_authority
from app.v2.resolution import promotion
from app.v2.tests.db.evidence_helpers import refused
from app.v2.tests.db.harness import (
    HEAD_REVISION,
    HEAD_V2_OBJECTS,
    REVISION_0006_V2_OBJECTS,
    REVISION_0007_V2_OBJECTS,
    create_legacy_probe_objects,
    scalar,
    snapshot_non_v2,
    v2_objects,
)
from app.v2.tests.db.resolution_helpers import HUMAN, canonical_counts, make_candidate

pytestmark = pytest.mark.db

NEW_TABLES = ("company", "resolution_decision", "company_name", "company_identifier")


def rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql))]


def test_head_is_at_least_0007():
    assert HEAD_REVISION >= "0007"


def test_upgrade_0006_to_0007_creates_only_the_resolution_and_company_objects(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0006")
    assert v2_objects(clean_db) == REVISION_0006_V2_OBJECTS
    command.upgrade(alembic_cfg(), "0007")
    assert scalar(clean_db, "SELECT version_num FROM v2.alembic_version") == "0007"
    assert v2_objects(clean_db) == REVISION_0007_V2_OBJECTS
    assert [r[0] for r in rows(clean_db, "SELECT p.proname FROM pg_proc p WHERE p.pronamespace = 'v2'::regnamespace ORDER BY 1")] == [
        "company_candidate_guard", "company_candidate_identifier_guard", "company_guard", "company_identifier_guard",
        "company_name_guard", "company_requires_provenance", "forbid_evidence_change", "normalize_company_identifier",
        "observation_stamp", "processing_attempt_guard", "resolution_decision_guard", "source_guard"]


def test_downgrade_0007_to_0006_removes_only_increment_9_objects_and_upgrade_again_works(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0007")
    command.downgrade(alembic_cfg(), "0006")
    assert v2_objects(clean_db) == REVISION_0006_V2_OBJECTS
    assert [r[0] for r in rows(clean_db, "SELECT p.proname FROM pg_proc p WHERE p.pronamespace = 'v2'::regnamespace ORDER BY 1")] == [
        "company_candidate_guard", "company_candidate_identifier_guard", "forbid_evidence_change", "observation_stamp",
        "processing_attempt_guard", "source_guard"]
    command.upgrade(alembic_cfg(), "head")
    assert v2_objects(clean_db) == HEAD_V2_OBJECTS


@pytest.mark.parametrize("state", ["decision_only", "company"])
def test_downgrade_refuses_while_resolution_or_company_history_exists(migrated_db, alembic_cfg, state):
    db = migrated_db
    candidate = make_candidate(db, "Acme Robotics", domain="acmerobotics.com")
    if state == "company":
        promotion.create_company_from_candidate(db, candidate.id, human_authority(HUMAN))
    else:
        promotion.defer_candidate(db, candidate.id, human_authority(HUMAN), "later")
    before = canonical_counts(db)
    with pytest.raises(DBAPIError) as info:
        command.downgrade(alembic_cfg(), "0006")
    assert "refusing to downgrade 0007" in str(info.value.orig)
    assert scalar(db, "SELECT version_num FROM v2.alembic_version") == HEAD_REVISION      # the whole downgrade rolled back
    assert canonical_counts(db) == before and v2_objects(db) == HEAD_V2_OBJECTS


def test_a_downgrade_to_base_is_also_refused_while_history_exists(migrated_db, alembic_cfg):
    db = migrated_db
    promotion.create_company_from_candidate(db, make_candidate(db, "Acme").id, human_authority(HUMAN))
    with pytest.raises(DBAPIError):
        command.downgrade(alembic_cfg(), "base")
    assert scalar(db, "SELECT count(*) FROM v2.company") == 1


def test_tables_are_labelled_and_the_company_table_is_a_bare_anchor(migrated_db):
    for table, word in (("company", "TRUSTED"), ("resolution_decision", "RULE or a HUMAN"),
                        ("company_name", "human resolution decision"), ("company_identifier", "human resolution decision")):
        assert word in scalar(migrated_db, "SELECT obj_description(to_regclass(:t)::oid, 'pg_class')", t=f"v2.{table}")
    assert [r[0] for r in rows(migrated_db, "SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='company' ORDER BY 1")] == ["created_at", "id"]
    assert scalar(migrated_db, "SELECT data_type FROM information_schema.columns WHERE table_schema='v2' AND table_name='company' AND column_name='id'") == "uuid"


def test_constraint_and_trigger_inventory(migrated_db):
    def constraints(table):
        return [r[0] for r in rows(migrated_db, f"SELECT conname FROM pg_constraint WHERE conrelid='v2.{table}'::regclass AND contype IN ('p','u','c','f') ORDER BY 1")]
    assert constraints("company") == ["pk_company"]
    assert constraints("resolution_decision") == [
        "ck_resolution_decision_actor_human", "ck_resolution_decision_actor_is_not_ai", "ck_resolution_decision_actor_rule",
        "ck_resolution_decision_authority_allowed", "ck_resolution_decision_company_matches_kind", "ck_resolution_decision_kind_allowed",
        "ck_resolution_decision_reason_matches_kind", "ck_resolution_decision_reason_shape",
        "fk_resolution_decision_candidate_id_company_candidate", "fk_resolution_decision_company_id_company", "pk_resolution_decision"]
    assert [r[0] for r in rows(migrated_db, "SELECT tgname FROM pg_trigger WHERE tgrelid IN ('v2.company'::regclass, 'v2.resolution_decision'::regclass, "
                                            "'v2.company_name'::regclass, 'v2.company_identifier'::regclass) AND NOT tgisinternal ORDER BY 1")] == [
        "trg_company_append_only", "trg_company_guard", "trg_company_identifier_append_only", "trg_company_identifier_guard",
        "trg_company_identifier_no_truncate", "trg_company_name_append_only", "trg_company_name_guard", "trg_company_name_no_truncate",
        "trg_company_no_truncate", "trg_company_requires_provenance", "trg_resolution_decision_append_only",
        "trg_resolution_decision_guard", "trg_resolution_decision_no_truncate"]
    assert scalar(migrated_db, "SELECT tgdeferrable AND tginitdeferred FROM pg_trigger WHERE tgname = 'trg_company_requires_provenance'")


def test_metadata_matches_the_migration_alembic_check_is_clean(migrated_db, alembic_cfg):
    command.check(alembic_cfg())


def test_legacy_objects_are_untouched_by_the_migration_in_both_directions(clean_db, alembic_cfg):
    command.upgrade(alembic_cfg(), "0006")
    create_legacy_probe_objects(clean_db)
    baseline = snapshot_non_v2(clean_db)
    command.upgrade(alembic_cfg(), "head")
    assert snapshot_non_v2(clean_db) == baseline
    command.downgrade(alembic_cfg(), "0006")
    assert snapshot_non_v2(clean_db) == baseline


def test_earlier_revisions_are_unchanged_in_history():
    from alembic.script import ScriptDirectory
    from app.v2.tests.db.harness import make_alembic_config
    script = ScriptDirectory.from_config(make_alembic_config())
    assert [r.revision for r in script.walk_revisions()] == ["0012", "0011", "0010", "0009", "0008", "0007", "0006", "0005", "0004", "0003", "0002", "0001"]
    assert script.get_revision("0007").down_revision == "0006"


# ---------------- the SQL normalizer is the twin of the Python policy

DOMAIN_CORPUS = ["Example.com", "example.com", "www.example.com", "WWW.Example.COM.", "app.example.com", "www.app.example.com",
                 "www.com", "wwwexample.com", "www.www.example.com", "example.co.uk", "a-b.example", "xn--bcher-kva.example"]
URL_CORPUS = ["https://example.com", "HTTPS://Example.COM/Path", "https://www.example.com/", "http://example.com/", "https://example.com:443/a",
              "http://example.com:80", "https://example.com:8443/a", "http://example.com:443/", "https://example.com/a#frag",
              "https://example.com/a/", "https://example.com/A?Q=1&b=2", "https://example.com?x=1", "https://example.com/?",
              "http://example.com:0080/x", "https://example.com:00443", "HTTP://EXAMPLE.com:8080?a#b"]


@pytest.mark.parametrize("raw", DOMAIN_CORPUS)
def test_sql_and_python_agree_on_domain_normalization(migrated_db, raw):
    assert scalar(migrated_db, "SELECT v2.normalize_company_identifier('domain', :v)", v=raw) == normalize_domain(raw)


@pytest.mark.parametrize("raw", URL_CORPUS)
def test_sql_and_python_agree_on_website_url_normalization(migrated_db, raw):
    assert scalar(migrated_db, "SELECT v2.normalize_company_identifier('website_url', :v)", v=raw) == normalize_website_url(raw)


def test_sql_normalization_refuses_what_it_does_not_support(migrated_db):
    for kind, value in (("website_url", "ftp://example.com"), ("website_url", "https://[::1]/"), ("website_url", "example.com"),
                        ("website_url", "https://example.com:99999/"), ("email", "x@y.z"), ("domain", None)):
        assert scalar(migrated_db, "SELECT v2.normalize_company_identifier(:t, :v)", t=kind, v=value) is None
    assert IdentifierType.DOMAIN.value == "domain"
