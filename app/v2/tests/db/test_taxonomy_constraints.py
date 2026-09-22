"""Direct-SQL attacks on the classification boundary: the database is the last line, whatever the writer."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.v2.classification import service
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.repositories import markets
from app.v2.tests.db.evidence_helpers import refused
from app.v2.tests.db.financing_fakes import canonical_company
from app.v2.tests.db.taxonomy_fakes import ME, TV1, setup_taxonomy

pytestmark = pytest.mark.db

ANY = (IntegrityError, DBAPIError)


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    taxonomy = setup_taxonomy(db, ("robotics", "Robotics"), ("ai-infrastructure", "AI Infrastructure"))
    company = canonical_company(db)
    return db, company, taxonomy


def insert_sql(company, market, tv="'" + TV1 + "'", role="'primary'", by_kind="'human'", by_id="'admin:jerrod'"):
    return (f"INSERT INTO v2.company_market_classification (company_id, market_id, taxonomy_version, role, decided_by_kind, decided_by_id) "
            f"VALUES (:c, {market}, {tv}, {role}, {by_kind}, {by_id})")


def try_insert(db, company, market, **kw):
    with pytest.raises(ANY) as info:
        with db.begin() as conn:
            conn.execute(text(insert_sql(company, market, **kw)), {"c": company})
    return str(info.value.orig)


# ---------------- AI is impossible

@pytest.mark.parametrize("by_kind", ["ai", "AI", "llm", "model", "system", "agent", ""])
def test_a_direct_insert_with_any_other_authority_kind_fails(world, by_kind):
    db, company, taxonomy = world
    market = f"'{taxonomy['robotics'].id}'"
    message = try_insert(db, company, market, by_kind=f"'{by_kind}'")
    assert "ck_cmc_authority_allowed" in message or "violates check constraint" in message


@pytest.mark.parametrize("actor", ["ai:gpt4", "admin:claude", "admin:openai", "bot:x"])
def test_a_human_decision_cannot_name_an_ai_actor(world, actor):
    db, company, taxonomy = world
    market = f"'{taxonomy['robotics'].id}'"
    try_insert(db, company, market, by_id=f"'{actor}'")


def test_a_rule_decision_is_always_refused_even_a_shape_valid_one(world):
    db, company, taxonomy = world
    market = f"'{taxonomy['robotics'].id}'"
    message = try_insert(db, company, market, role="'primary'", by_kind="'rule'", by_id="'exact_identifier_match.v1'")
    assert "no classification rule is enabled" in message


def test_a_rule_actor_must_still_be_versioned_and_a_human_actor_must_be_shaped(world):
    db, company, taxonomy = world
    market = f"'{taxonomy['robotics'].id}'"
    for by_id in ("system", "jerrod", "admin:", "x" * 100 + ":y"):
        try_insert(db, company, market, by_kind="'human'", by_id=f"'{by_id}'")
    for by_id in ("system", "exact_identifier_match", "EXACT.v1"):
        try_insert(db, company, market, by_kind="'rule'", by_id=f"'{by_id}'")


def test_the_schema_has_no_ai_authority_value_or_enum(migrated_db):
    with migrated_db.connect() as conn:
        definition = conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_cmc_authority_allowed'")).scalar()
        enums = conn.execute(text("SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'v2' AND t.typtype = 'e'")).scalar()
    assert "'rule'" in definition and "'human'" in definition and "'ai'" not in definition.lower() and enums == 0


# ---------------- role vocabulary and uniqueness

def test_role_vocabulary_is_closed(world):
    db, company, taxonomy = world
    market = f"'{taxonomy['robotics'].id}'"
    for role in ("Primary", "tertiary", "", "PRIMARY"):
        try_insert(db, company, market, role=f"'{role}'")


def test_one_primary_per_company_per_taxonomy_version_at_the_database(world):
    db, company, taxonomy = world
    with db.begin() as conn:
        conn.execute(text(insert_sql(company, f"'{taxonomy['robotics'].id}'")), {"c": company})
    _, message = refused(db, insert_sql(company, f"'{taxonomy['ai-infrastructure'].id}'"), {"c": company}, exc=ANY)
    assert "uq_cmc_one_primary_per_company_version" in message or "unique" in message.lower()


def test_the_same_triple_cannot_be_classified_twice(world):
    db, company, taxonomy = world
    with db.begin() as conn:
        conn.execute(text(insert_sql(company, f"'{taxonomy['robotics'].id}'", role="'secondary'")), {"c": company})
    _, message = refused(db, insert_sql(company, f"'{taxonomy['robotics'].id}'", role="'secondary'"), {"c": company}, exc=ANY)
    assert "uq_cmc_company_market_version" in message or "unique" in message.lower()


# ---------------- foreign keys and created_at

def test_unknown_company_market_or_taxonomy_version_fail_by_foreign_key(world):
    db, company, taxonomy = world
    import uuid
    market = f"'{taxonomy['robotics'].id}'"
    assert "fk_cmc_company_id" in try_insert(db, str(uuid.uuid4()), market) or "foreign key" in try_insert(db, company, market, tv="'no_such.v1'")
    assert "foreign key" in try_insert(db, company, f"'{uuid.uuid4()}'")


def test_created_at_is_database_owned(world):
    db, company, taxonomy = world
    with db.begin() as conn:
        conn.execute(text("INSERT INTO v2.company_market_classification (company_id, market_id, taxonomy_version, role, decided_by_kind, decided_by_id, created_at) "
                          "VALUES (:c, :m, :t, 'primary', 'human', 'admin:jerrod', '2001-01-01T00:00:00Z')"),
                     {"c": company, "m": taxonomy["robotics"].id, "t": TV1})
        stamped = conn.execute(text("SELECT created_at FROM v2.company_market_classification WHERE company_id = :c"), {"c": company}).scalar()
    assert stamped.year >= 2026


# ---------------- market / taxonomy_version identity and shape

def test_market_id_is_database_generated(migrated_db):
    supplied = "11111111-1111-1111-1111-111111111111"
    with migrated_db.begin() as conn:
        row = conn.execute(text("INSERT INTO v2.market (id, slug, display_name) VALUES (:i, 'robotics', 'Robotics') RETURNING id"), {"i": supplied}).one()
    assert str(row.id) != supplied


def test_market_slug_and_display_name_shape_are_checked(migrated_db):
    for slug in ("Not A Slug", "-robotics", "robotics-", ""):
        refused(migrated_db, f"INSERT INTO v2.market (slug, display_name) VALUES ('{slug}', 'Robotics')", exc=ANY)
    for name in ("", " Robotics"):
        refused(migrated_db, f"INSERT INTO v2.market (slug, display_name) VALUES ('robotics', '{name}')", exc=ANY)


def test_taxonomy_version_shape_is_checked(migrated_db):
    for tv in ("v1", "latest", "1.0", ""):
        refused(migrated_db, f"INSERT INTO v2.taxonomy_version (taxonomy_version) VALUES ('{tv}')", exc=ANY)


# ---------------- append-only

@pytest.mark.parametrize("table", ["taxonomy_version", "market", "company_market_classification"])
def test_update_delete_and_truncate_are_blocked(world, table):
    db, company, taxonomy = world
    service.classify_company(db, company, taxonomy["robotics"].id, TV1, ClassificationRole.PRIMARY, ME)
    set_clause = {"taxonomy_version": "created_at = now()", "market": "display_name = 'Renamed'", "company_market_classification": "role = 'secondary'"}[table]
    for sql in (f"UPDATE v2.{table} SET {set_clause}", f"DELETE FROM v2.{table}", f"TRUNCATE v2.{table} CASCADE"):
        _, message = refused(db, sql, exc=ANY)
        assert "append-only" in message, sql


def test_taxonomy_market_and_classification_rows_cannot_orphan_their_provenance(world):
    db, company, taxonomy = world
    service.classify_company(db, company, taxonomy["robotics"].id, TV1, ClassificationRole.PRIMARY, ME)
    for sql in ("DELETE FROM v2.company", "DELETE FROM v2.market", "DELETE FROM v2.taxonomy_version"):
        refused(db, sql, exc=ANY)
