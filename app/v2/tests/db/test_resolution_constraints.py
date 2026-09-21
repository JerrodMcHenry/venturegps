"""Direct-SQL attacks on the resolution boundary: the database is the last line, whatever the writer."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.v2.domain.resolution import human_authority
from app.v2.resolution import promotion
from app.v2.tests.db.evidence_helpers import refused
from app.v2.tests.db.resolution_helpers import HUMAN, canonical_counts, make_candidate, untouched_snapshot

pytestmark = pytest.mark.db

ANY = (IntegrityError, DBAPIError)


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    open_candidate = make_candidate(db, "Acme Robotics", domain="acmerobotics.com")
    created = make_candidate(db, "Globex", domain="globex.example")
    company_id = promotion.create_company_from_candidate(db, created.id, human_authority(HUMAN)).company_id
    return db, open_candidate, created, company_id


def decision_sql(kind="create_company", by_kind="human", by_id="admin:jerrod", company="NULL", reason="NULL", candidate=":c"):
    return (f"INSERT INTO v2.resolution_decision (candidate_id, decision_kind, company_id, decided_by_kind, decided_by_id, reason_code) "
            f"VALUES ({candidate}, '{kind}', {company}, '{by_kind}', '{by_id}', {reason})")


# ---------------- AI is impossible in the database

@pytest.mark.parametrize("by_kind", ["ai", "AI", "llm", "model", "system", "agent", "", "Human", "rule "])
def test_a_direct_insert_with_any_other_authority_kind_fails(world, by_kind):
    db, candidate, _, _ = world
    before = canonical_counts(db)
    _, message = refused(db, decision_sql("reject_candidate", by_kind, "admin:jerrod", reason="'nope'"), {"c": candidate.id}, exc=ANY)
    assert "ck_resolution_decision_authority_allowed" in message or "violates check constraint" in message
    assert canonical_counts(db) == before


@pytest.mark.parametrize("actor", ["ai:gpt4", "admin:claude", "admin:openai", "admin:llm.v2", "bot:x"])
def test_a_human_decision_cannot_name_an_ai_actor(world, actor):
    db, candidate, _, _ = world
    refused(db, decision_sql("reject_candidate", "human", actor, reason="'nope'"), {"c": candidate.id}, exc=ANY)


@pytest.mark.parametrize("actor", ["gpt_matcher.v1", "ai_rule.v1", "claude_rule.v2", "model.v1"])
def test_a_rule_decision_cannot_name_an_ai_actor(world, actor):
    db, candidate, _, company_id = world
    refused(db, decision_sql("attach_to_company", "rule", actor, company=f"'{company_id}'"), {"c": candidate.id}, exc=ANY)


def test_the_schema_has_no_ai_authority_value_column_or_table(migrated_db):
    with migrated_db.connect() as conn:
        definition = conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_resolution_decision_authority_allowed'")).scalar()
        names = [r[0] for r in conn.execute(text(
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'v2' AND relkind = 'r'"))]
        columns = [r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'v2' AND table_name IN "
            "('company','resolution_decision','company_name','company_identifier')"))]
        enums = conn.execute(text("SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'v2' AND t.typtype = 'e'")).scalar()
    assert "'rule'" in definition and "'human'" in definition and "'ai'" not in definition.lower()
    assert enums == 0
    for word in ("ai", "llm", "model", "confidence", "score", "prompt", "provider"):
        assert not any(word == n or word in n.split("_") for n in names + columns), word


def test_rules_may_only_attach_and_humans_carry_a_shaped_actor(world):
    db, candidate, created, company_id = world
    for kind, extra in (("create_company", dict(company="gen_random_uuid()")), ("reject_candidate", dict(reason="'nope'")),
                        ("defer_candidate", dict(reason="'later'"))):
        refused(db, decision_sql(kind, "rule", "exact_identifier_match.v1", **extra), {"c": candidate.id}, exc=ANY)
    for actor in ("system", "jerrod", "admin", "admin:", "Admin:x", "x" * 100 + ":y"):
        refused(db, decision_sql("reject_candidate", "human", actor, reason="'nope'"), {"c": candidate.id}, exc=ANY)
    for actor in ("system", "exact_identifier_match", "EXACT.v1", "exact.v"):
        refused(db, decision_sql("attach_to_company", "rule", actor, company=f"'{company_id}'"), {"c": candidate.id}, exc=ANY)


def test_a_rule_decision_needs_an_exact_identifier_match_in_the_database_too(world):
    db, candidate, created, company_id = world
    before = canonical_counts(db)
    _, message = refused(db, decision_sql("attach_to_company", "rule", "exact_identifier_match.v1", company=f"'{company_id}'"),
                         {"c": candidate.id}, exc=ANY)                                             # `candidate` shares no identifier with the company
    assert "exact match" in message and canonical_counts(db) == before


# ---------------- decision shape

def test_decision_kind_company_and_reason_shapes_are_enforced(world):
    db, candidate, _, company_id = world
    bad = [decision_sql("reject_candidate", company=f"'{company_id}'", reason="'nope'"),
           decision_sql("defer_candidate", company=f"'{company_id}'", reason="'later'"),
           decision_sql("reject_candidate"), decision_sql("defer_candidate"),
           decision_sql("attach_to_company"), decision_sql("create_company"),
           decision_sql("attach_to_company", company=f"'{company_id}'", reason="'x1'"),
           decision_sql("merge_companies", company=f"'{company_id}'"), decision_sql("promote", company=f"'{company_id}'"),
           decision_sql("reject_candidate", reason="'Not A Code'")]
    for sql in bad:
        refused(db, sql, {"c": candidate.id}, exc=ANY)


def test_created_at_is_database_owned(world):
    db, candidate, _, _ = world
    with db.begin() as conn:
        conn.execute(text("INSERT INTO v2.resolution_decision (candidate_id, decision_kind, decided_by_kind, decided_by_id, reason_code, created_at) "
                          "VALUES (:c, 'defer_candidate', 'human', 'admin:jerrod', 'later', '2001-01-01T00:00:00Z')"), {"c": candidate.id})
        stamped = conn.execute(text("SELECT created_at FROM v2.resolution_decision WHERE candidate_id = :c"), {"c": candidate.id}).scalar()
    assert stamped.year >= 2026


# ---------------- no contradictory resolutions

def test_one_final_decision_per_candidate_and_nothing_final_may_be_followed(world):
    db, candidate, created, _ = world
    refused(db, decision_sql("reject_candidate", reason="'again'", candidate=":c"), {"c": created.id}, exc=ANY)   # already created
    refused(db, decision_sql("defer_candidate", reason="'again'", candidate=":c"), {"c": created.id}, exc=ANY)   # nothing follows a final
    with db.begin() as conn:
        conn.execute(text(decision_sql("reject_candidate", reason="'not_a_company'")), {"c": candidate.id})
    refused(db, decision_sql("reject_candidate", reason="'again'"), {"c": candidate.id}, exc=ANY)


def test_a_company_can_have_only_one_create_decision(world):
    db, candidate, created, company_id = world
    refused(db, decision_sql("create_company", company=f"'{company_id}'"), {"c": candidate.id}, exc=ANY)


# ---------------- Company cannot exist without provenance, even via direct SQL

def test_a_bare_company_cannot_be_committed(migrated_db):
    _, message = refused(migrated_db, "INSERT INTO v2.company DEFAULT VALUES", exc=ANY)
    assert "create_company decision and a canonical name" in message
    assert canonical_counts(migrated_db)["company"] == 0


def test_a_company_with_only_a_decision_or_only_a_name_cannot_be_committed(world):
    db, candidate, _, _ = world
    with pytest.raises(ANY):
        with db.begin() as conn:
            cid = conn.execute(text("INSERT INTO v2.company DEFAULT VALUES RETURNING id")).scalar()
            conn.execute(text(f"INSERT INTO v2.resolution_decision (candidate_id, decision_kind, company_id, decided_by_kind, decided_by_id) "
                              f"VALUES (:c, 'create_company', :co, 'human', 'admin:jerrod')"), {"c": candidate.id, "co": cid})
    assert canonical_counts(db)["company"] == 1


def test_company_identity_is_generated_by_the_database(migrated_db):
    supplied = "11111111-1111-1111-1111-111111111111"
    candidate = make_candidate(migrated_db, "Acme Robotics")
    with migrated_db.begin() as conn:
        cid = conn.execute(text("INSERT INTO v2.company (id, created_at) VALUES (:i, '2001-01-01T00:00:00Z') RETURNING id"), {"i": supplied}).scalar()
        conn.execute(text("INSERT INTO v2.resolution_decision (candidate_id, decision_kind, company_id, decided_by_kind, decided_by_id) "
                          "VALUES (:c, 'create_company', :co, 'human', 'admin:jerrod')"), {"c": candidate.id, "co": cid})
        conn.execute(text("INSERT INTO v2.company_name (company_id, name, name_role, resolution_decision_id, candidate_id) "
                          "SELECT :co, 'Acme Robotics', 'canonical', d.id, :c FROM v2.resolution_decision d WHERE d.company_id = :co"), {"c": candidate.id, "co": cid})
    with migrated_db.connect() as conn:
        row = conn.execute(text("SELECT id::text, created_at FROM v2.company")).one()
    assert row.id != supplied and row.created_at.year >= 2026                                       # neither id nor time is the writer's


# ---------------- name and identifier rules

def test_a_name_must_come_from_a_human_decision_on_the_candidate_that_proposed_it(world):
    db, candidate, created, company_id = world
    with db.connect() as conn:
        create_decision = conn.execute(text("SELECT id FROM v2.resolution_decision WHERE company_id = :c"), {"c": company_id}).scalar()
    for name, role, cand in (("Invented Name", "alias", created.id), ("Globex", "alias", created.id),   # alias needs an attach decision
                             ("Globex", "canonical", candidate.id), ("Globex", "primary", created.id)):
        refused(db, "INSERT INTO v2.company_name (company_id, name, name_role, resolution_decision_id, candidate_id) VALUES (:co, :n, :r, :d, :ca)",
                {"co": company_id, "n": name, "r": role, "d": create_decision, "ca": cand}, exc=ANY)


def test_only_one_canonical_name_per_company(world):
    db, _, created, company_id = world
    with db.connect() as conn:
        d = conn.execute(text("SELECT id FROM v2.resolution_decision WHERE company_id = :c"), {"c": company_id}).scalar()
    refused(db, "INSERT INTO v2.company_name (company_id, name, name_role, resolution_decision_id, candidate_id) VALUES (:co, 'Globex', 'canonical', :d, :ca)",
            {"co": company_id, "d": d, "ca": created.id}, exc=ANY)


def test_identifiers_must_be_normalized_typed_owned_by_one_company_and_from_their_candidate_identifier(world):
    db, candidate, created, company_id = world
    with db.connect() as conn:
        d = conn.execute(text("SELECT id FROM v2.resolution_decision WHERE company_id = :c"), {"c": company_id}).scalar()
        ci = conn.execute(text("SELECT id FROM v2.company_candidate_identifier WHERE candidate_id = :c"), {"c": created.id}).scalar()
        other_ci = conn.execute(text("SELECT id FROM v2.company_candidate_identifier WHERE candidate_id = :c"), {"c": candidate.id}).scalar()
    sql = "INSERT INTO v2.company_identifier (company_id, identifier_type, identifier_value, resolution_decision_id, candidate_identifier_id) VALUES (:co, :t, :v, :d, :ci)"
    for t, v, source_ci in (("domain", "globex.example", ci),            # already accepted (one owner, one row)
                            ("domain", "WWW.GLOBEX.EXAMPLE", ci), ("domain", "www.globex.example", ci),   # not normalized
                            ("website_url", "https://globex.example", ci), ("email", "a@b.co", ci), ("name", "Globex", ci),
                            ("domain", "acmerobotics.com", other_ci),    # from a candidate the decision did not resolve
                            ("domain", "other.example", ci)):            # not what the candidate identifier proposed
        refused(db, sql, {"co": company_id, "t": t, "v": v, "d": d, "ci": source_ci}, exc=ANY)


def test_the_same_canonical_identifier_cannot_belong_to_two_companies_even_by_direct_sql(migrated_db):
    db = migrated_db
    promotion.create_company_from_candidate(db, make_candidate(db, "One", domain="shared.example").id, human_authority(HUMAN))
    dup = make_candidate(db, "Two", domain="shared.example")
    with pytest.raises(ANY):
        with db.begin() as conn:
            cid = conn.execute(text("INSERT INTO v2.company DEFAULT VALUES RETURNING id")).scalar()
            d = conn.execute(text("INSERT INTO v2.resolution_decision (candidate_id, decision_kind, company_id, decided_by_kind, decided_by_id) "
                                  "VALUES (:c, 'create_company', :co, 'human', 'admin:jerrod') RETURNING id"), {"c": dup.id, "co": cid}).scalar()
            conn.execute(text("INSERT INTO v2.company_name (company_id, name, name_role, resolution_decision_id, candidate_id) VALUES (:co, 'Two', 'canonical', :d, :c)"),
                         {"co": cid, "d": d, "c": dup.id})
            ci = conn.execute(text("SELECT id FROM v2.company_candidate_identifier WHERE candidate_id = :c"), {"c": dup.id}).scalar()
            conn.execute(text("INSERT INTO v2.company_identifier (company_id, identifier_type, identifier_value, resolution_decision_id, candidate_identifier_id) "
                              "VALUES (:co, 'domain', 'shared.example', :d, :ci)"), {"co": cid, "d": d, "ci": ci})
    assert canonical_counts(db)["company"] == 1


# ---------------- append-only, restrict FKs, nothing else changes

@pytest.mark.parametrize("table", ["company", "resolution_decision", "company_name", "company_identifier"])
def test_update_delete_and_truncate_are_blocked_on_every_canonical_table(world, table):
    db = world[0]
    before = (canonical_counts(db), untouched_snapshot(db))
    column = "created_at"
    for sql in (f"UPDATE v2.{table} SET {column} = now()", f"DELETE FROM v2.{table}", f"TRUNCATE v2.{table} CASCADE",
                f"TRUNCATE v2.{table} RESTART IDENTITY CASCADE"):
        _, message = refused(db, sql, exc=ANY)
        assert "append-only" in message, sql
    assert (canonical_counts(db), untouched_snapshot(db)) == before


def test_an_upsert_cannot_rewrite_a_decision(world):
    db, _, created, company_id = world
    _, message = refused(db, "INSERT INTO v2.resolution_decision (candidate_id, decision_kind, company_id, decided_by_kind, decided_by_id) "
                             "VALUES (:c, 'create_company', :co, 'human', 'admin:jerrod') ON CONFLICT DO NOTHING", {"c": created.id, "co": company_id}, exc=ANY)
    assert "final resolution" in message or "unique" in message


def test_canonical_rows_cannot_orphan_their_provenance(world):
    db, _, created, company_id = world
    for sql in ("DELETE FROM v2.company_candidate", "DELETE FROM v2.processing_attempt", "DELETE FROM v2.observation"):
        refused(db, sql, exc=ANY)
    with db.connect() as conn:
        rules_ = conn.execute(text("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE contype = 'f' AND connamespace = 'v2'::regnamespace "
                                   "AND conrelid::regclass::text IN ('v2.company','v2.resolution_decision','v2.company_name','v2.company_identifier')")).all()
    assert rules_ and all("ON DELETE RESTRICT" in d for _, d in rules_)


def test_resolution_leaves_candidates_attempts_and_evidence_byte_for_byte_unchanged(migrated_db):
    db = migrated_db
    candidate = make_candidate(db, "Acme Robotics", domain="acmerobotics.com")
    before = untouched_snapshot(db)
    promotion.create_company_from_candidate(db, candidate.id, human_authority(HUMAN))
    assert untouched_snapshot(db) == before
    with db.connect() as conn:                                                                      # the attempt was not reopened or closed by us
        assert conn.execute(text("SELECT status FROM v2.processing_attempt WHERE id = :a"), {"a": candidate.processing_attempt_id}).scalar() == "processing"


def test_a_rule_decision_can_never_accept_a_new_name_or_identifier_even_by_direct_sql(migrated_db):
    from app.v2.resolution import rules
    db = migrated_db
    company_id = promotion.create_company_from_candidate(db, make_candidate(db, "One Co", domain="one.example").id, human_authority(HUMAN)).company_id
    later = make_candidate(db, "One Company", domain="one.example", url="https://one.example/about")
    outcome = rules.resolve_by_exact_identifier(db, later.id)
    assert outcome.decision.authority.kind.value == "rule"
    with db.connect() as conn:
        ci = conn.execute(text("SELECT id FROM v2.company_candidate_identifier WHERE candidate_id = :c AND identifier_type = 'website_url'"), {"c": later.id}).scalar()
    refused(db, "INSERT INTO v2.company_name (company_id, name, name_role, resolution_decision_id, candidate_id) VALUES (:co, 'One Company', 'alias', :d, :c)",
            {"co": company_id, "d": outcome.decision.id, "c": later.id}, exc=ANY)
    refused(db, "INSERT INTO v2.company_identifier (company_id, identifier_type, identifier_value, resolution_decision_id, candidate_identifier_id) "
                "VALUES (:co, 'website_url', 'https://one.example/about', :d, :ci)", {"co": company_id, "d": outcome.decision.id, "ci": ci}, exc=ANY)
    assert canonical_counts(db) == {"company": 1, "resolution_decision": 2, "company_name": 1, "company_identifier": 1}
