"""Direct-SQL attacks on the lifecycle resolution boundary: the database is the last line, whatever the writer.
Mirrors test_financing_resolution_constraints.py's own structure and rigor."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.v2.domain.lifecycle import OperatingStatus, SuccessorRelationshipKind
from app.v2.domain.lifecycle_resolution import LifecycleFactSelection
from app.v2.domain.resolution import human_authority
from app.v2.lifecycle import promotion
from app.v2.repositories import lifecycle_candidates as candidates
from app.v2.tests.db.evidence_helpers import refused
from app.v2.tests.db.lifecycle_fakes import RENAME_ANNOUNCEMENT, canonical_company, make_lifecycle, rename, start_attempt
from app.v2.tests.db.resolution_helpers import untouched_snapshot

pytestmark = pytest.mark.db

ANY = (IntegrityError, DBAPIError)
HUMAN = "admin:jerrod"
ME = human_authority(HUMAN)

ALL_LIFECYCLE_TABLES = (
    "lifecycle_event_candidate", "lifecycle_event_candidate_name_change", "lifecycle_event_candidate_operating_status",
    "lifecycle_event_candidate_acquisition", "lifecycle_event_candidate_successor", "lifecycle_resolution_decision",
    "company_name_history", "company_operating_status", "company_acquisition", "company_successor_relationship",
)


def lc_counts(db):
    with db.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in ALL_LIFECYCLE_TABLES}


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, RENAME_ANNOUNCEMENT)
    candidate = candidates.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)]).candidates[0]
    return db, company, candidate


def decision_sql(kind="accept_lifecycle_event", by_kind="human", by_id="admin:jerrod", reason="NULL", candidate=":c"):
    return (f"INSERT INTO v2.lifecycle_resolution_decision (candidate_id, decision_kind, decided_by_kind, decided_by_id, reason_code) "
            f"VALUES ({candidate}, '{kind}', '{by_kind}', '{by_id}', {reason})")


# ---------------- AI is impossible; only human/rule; no rule is ever enabled

@pytest.mark.parametrize("by_kind", ["ai", "AI", "llm", "model", "system", "agent", ""])
def test_a_direct_insert_with_any_other_authority_kind_fails(world, by_kind):
    db, _, candidate = world
    before = lc_counts(db)
    _, message = refused(db, decision_sql("reject_candidate", by_kind, "admin:jerrod", reason="'nope'"), {"c": candidate.id}, exc=ANY)
    assert "ck_lrd_authority_allowed" in message or "violates check constraint" in message
    assert lc_counts(db) == before


@pytest.mark.parametrize("actor", ["ai:gpt4", "admin:claude", "admin:openai", "bot:x"])
def test_a_human_decision_cannot_name_an_ai_actor(world, actor):
    db, _, candidate = world
    refused(db, decision_sql("reject_candidate", "human", actor, reason="'nope'"), {"c": candidate.id}, exc=ANY)


def test_a_rule_decision_is_always_refused_even_a_shape_valid_one(world):
    """No lifecycle rule is enabled: EVERY 'rule' decision is refused, not just malformed ones."""
    db, _, candidate = world
    _, message = refused(db, decision_sql("accept_lifecycle_event", "rule", "exact_lifecycle_match.v1"), {"c": candidate.id}, exc=ANY)
    assert "no lifecycle rule is enabled" in message


def test_the_schema_has_no_ai_authority_value_or_enum(migrated_db):
    with migrated_db.connect() as conn:
        definition = conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_lrd_authority_allowed'")).scalar()
    assert "'rule'" in definition and "'human'" in definition and "'ai'" not in definition.lower()


# ---------------- decision shape

def test_decision_kind_and_reason_shapes_are_enforced(world):
    db, _, candidate = world
    bad = [decision_sql("reject_candidate"), decision_sql("defer_candidate"),
           decision_sql("accept_lifecycle_event", reason="'x1'"),
           decision_sql("merge_companies"), decision_sql("reject_candidate", reason="'Not A Code'")]
    for sql in bad:
        refused(db, sql, {"c": candidate.id}, exc=ANY)


def test_created_at_is_database_owned(world):
    db, _, candidate = world
    with db.begin() as conn:
        conn.execute(text("INSERT INTO v2.lifecycle_resolution_decision (candidate_id, decision_kind, decided_by_kind, decided_by_id, reason_code, created_at) "
                          "VALUES (:c, 'defer_candidate', 'human', 'admin:jerrod', 'later', '2001-01-01T00:00:00Z')"), {"c": candidate.id})
        stamped = conn.execute(text("SELECT created_at FROM v2.lifecycle_resolution_decision WHERE candidate_id = :c"), {"c": candidate.id}).scalar()
    assert stamped.year >= 2026


# ---------------- no contradictory resolutions

def test_one_final_decision_per_candidate_and_nothing_final_may_follow(world):
    db, _, candidate = world
    promotion.accept_lifecycle_event(db, candidate.id, ME)
    refused(db, decision_sql("reject_candidate", reason="'again'"), {"c": candidate.id}, exc=ANY)
    refused(db, decision_sql("defer_candidate", reason="'again'"), {"c": candidate.id}, exc=ANY)
    refused(db, decision_sql("accept_lifecycle_event"), {"c": candidate.id}, exc=ANY)


def test_a_second_final_decision_on_the_same_candidate_is_refused(world):
    db, _, candidate = world
    promotion.accept_lifecycle_event(db, candidate.id, ME)
    _, message = refused(db, decision_sql("accept_lifecycle_event"), {"c": candidate.id}, exc=ANY)
    assert "final resolution" in message or "unique" in message


# ---------------- accepted-fact acceptance rules: value must match, company must match, decision must be a real accept

def test_a_name_change_fact_must_come_from_a_human_accept_decision_on_the_resolved_candidate_with_the_true_value(world):
    db, company, candidate = world
    d = promotion.accept_lifecycle_event(db, candidate.id, ME).decision.id
    sql = "INSERT INTO v2.company_name_history (company_id, new_name, resolution_decision_id, candidate_id) VALUES (:co, :n, :d, :c)"
    for name in ("Wrong Name Inc.", "lifeward ltd."):   # wrong value, and even a near-miss (case) is refused
        refused(db, sql, {"co": company, "n": name, "d": d, "c": candidate.id}, exc=ANY)
    with db.begin() as conn:   # the true value: accepted
        conn.execute(text(sql), {"co": company, "n": "Lifeward Ltd.", "d": d, "c": candidate.id})


def test_a_fact_cannot_be_backed_by_a_reject_or_defer_decision(world):
    db, company, candidate = world
    d = promotion.reject_candidate(db, candidate.id, ME, "not_valid").decision.id
    refused(db, "INSERT INTO v2.company_name_history (company_id, new_name, resolution_decision_id, candidate_id) VALUES (:co, :n, :d, :c)",
           {"co": company, "n": "Lifeward Ltd.", "d": d, "c": candidate.id}, exc=ANY)


def test_a_fact_cannot_be_backed_by_a_decision_for_a_different_candidate(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, first = start_attempt(db, RENAME_ANNOUNCEMENT)
    candidate_a = candidates.persist_lifecycle_event_candidates(db, first.id, [rename(company)]).candidates[0]
    from app.v2.tests.db.lifecycle_fakes import STATUS_ACTIVE_NEWS, status_active
    _, second = start_attempt(db, STATUS_ACTIVE_NEWS, record_id="other-candidate")
    candidate_b = candidates.persist_lifecycle_event_candidates(db, second.id, [status_active(company)]).candidates[0]
    d = promotion.accept_lifecycle_event(db, candidate_b.id, ME, LifecycleFactSelection(operating_status=True)).decision.id
    refused(db, "INSERT INTO v2.company_name_history (company_id, new_name, resolution_decision_id, candidate_id) VALUES (:co, :n, :d, :c)",
           {"co": company, "n": "Lifeward Ltd.", "d": d, "c": candidate_a.id}, exc=ANY)   # decision d never accepted candidate_a's fact


def test_a_fact_cannot_be_attributed_to_the_wrong_company(migrated_db):
    db = migrated_db
    company = canonical_company(db, "Acme Robotics, Inc.", "acmerobotics.com")
    other = canonical_company(db, "Globex Corporation", "globex.example")
    _, attempt = start_attempt(db, RENAME_ANNOUNCEMENT)
    candidate = candidates.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)]).candidates[0]
    d = promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(name_change=True)).decision.id
    refused(db, "INSERT INTO v2.company_name_history (company_id, new_name, resolution_decision_id, candidate_id) VALUES (:co, :n, :d, :c)",
           {"co": other, "n": "Lifeward Ltd.", "d": d, "c": candidate.id}, exc=ANY)


def test_only_a_human_accept_decision_may_back_a_canonical_operating_status(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    from app.v2.tests.db.lifecycle_fakes import STATUS_ACTIVE_NEWS, status_active
    _, attempt = start_attempt(db, STATUS_ACTIVE_NEWS)
    candidate = candidates.persist_lifecycle_event_candidates(db, attempt.id, [status_active(company)]).candidates[0]
    d = promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(operating_status=True)).decision.id
    with db.connect() as conn:
        assert conn.execute(text("SELECT status FROM v2.company_operating_status WHERE candidate_id = :c"), {"c": candidate.id}).scalar() == "active"
    refused(db, "INSERT INTO v2.company_operating_status (company_id, status, resolution_decision_id, candidate_id) VALUES (:co, 'acquired', :d, :c)",
           {"co": company, "d": d, "c": candidate.id}, exc=ANY)   # wrong value for the real row


def test_an_acquisition_fact_never_writes_an_operating_status_row_by_itself(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    from app.v2.tests.db.lifecycle_fakes import ACQUISITION_NEWS, acquisition
    _, attempt = start_attempt(db, ACQUISITION_NEWS)
    candidate = candidates.persist_lifecycle_event_candidates(db, attempt.id, [acquisition(company)]).candidates[0]
    promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(acquisition=True))
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.company_operating_status WHERE company_id = :c"), {"c": company}).scalar() == 0


# ---------------- append-only, restrict FKs

COMBINED_PAYLOAD = (
    b"ReWalk Robotics Ltd. announced today that its Board of Directors approved changing the company's "
    b"registered name to Lifeward Ltd., effective September 12, 2024. The company remains an active, "
    b"independently operating business. Siemens Healthineers AG completed its acquisition of a related "
    b"subsidiary. Some observers have called NewCo Robotics a possible successor to the original entity."
)


def _fully_populated_candidate(db, company):
    """One candidate with a row in every one of the four typed fact tables, accepted in full -- so every one of
    the 10 lifecycle tables has at least one row before the append-only sweep below."""
    _, attempt = start_attempt(db, COMBINED_PAYLOAD, record_id="combined-1")
    proposal = make_lifecycle(
        COMBINED_PAYLOAD, company, event=b"Board of Directors approved",
        name_change=("Lifeward Ltd.", b"Lifeward Ltd."),
        operating_status=(OperatingStatus.ACTIVE, b"active, independently operating"),
        acquisition=("Siemens Healthineers AG", b"Siemens Healthineers AG"),
        successor=("NewCo Robotics", SuccessorRelationshipKind.POSSIBLE_SUCCESSOR, b"NewCo Robotics"),
    )
    candidate = candidates.persist_lifecycle_event_candidates(db, attempt.id, [proposal]).candidates[0]
    promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(
        name_change=True, operating_status=True, acquisition=True, successor=True))
    return candidate


def test_update_delete_and_truncate_are_blocked_on_every_lifecycle_table(world):
    db, company, _ = world
    _fully_populated_candidate(db, company)
    before = (lc_counts(db), untouched_snapshot(db))
    for table in ALL_LIFECYCLE_TABLES:
        for sql in (f"UPDATE v2.{table} SET created_at = now()", f"DELETE FROM v2.{table}",
                    f"TRUNCATE v2.{table} CASCADE", f"TRUNCATE v2.{table} RESTART IDENTITY CASCADE"):
            _, message = refused(db, sql, exc=ANY)
            assert "append-only" in message, (table, sql)
    assert (lc_counts(db), untouched_snapshot(db)) == before


def test_canonical_lifecycle_rows_cannot_orphan_their_provenance(world):
    db, _, candidate = world
    promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(name_change=True))
    for sql in ("DELETE FROM v2.lifecycle_event_candidate", "DELETE FROM v2.company", "DELETE FROM v2.processing_attempt",
               "DELETE FROM v2.lifecycle_resolution_decision"):
        refused(db, sql, exc=ANY)
    with db.connect() as conn:
        defs = conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE contype = 'f' AND connamespace = 'v2'::regnamespace "
                                 "AND conrelid::regclass::text LIKE 'v2.company_%' AND conrelid::regclass::text NOT LIKE '%_candidate%' "
                                 "AND conrelid::regclass::text IN ('v2.company_name_history', 'v2.company_operating_status', "
                                 "'v2.company_acquisition', 'v2.company_successor_relationship')")).all()
    assert defs and all("ON DELETE RESTRICT" in d[0] for d in defs)


def test_lifecycle_resolution_never_modifies_the_candidate_layer_or_earlier_evidence(world):
    db, _, candidate = world
    before = untouched_snapshot(db)
    promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(name_change=True))
    assert untouched_snapshot(db) == before


# ---------------- no per-company uniqueness: many accepted facts of the same kind coexist, by design

def test_no_per_company_uniqueness_on_any_canonical_lifecycle_table(migrated_db):
    with migrated_db.connect() as conn:
        for table in ("company_name_history", "company_operating_status", "company_acquisition", "company_successor_relationship"):
            constraints = [r[0] for r in conn.execute(text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = to_regclass(:t) AND contype = 'u'"), {"t": f"v2.{table}"})]
            assert not any("company_id" in c and "resolution_decision_id" not in c and "candidate_id" not in c for c in constraints), table
