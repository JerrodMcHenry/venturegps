"""Direct-SQL attacks on the financing resolution boundary: the database is the last line, whatever the writer."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.v2.domain.resolution import human_authority
from app.v2.financing_resolution import promotion
from app.v2.domain.financing_resolution import FactSelection
from app.v2.tests.db.evidence_helpers import refused
from app.v2.tests.db.financing_fakes import FORM_D, ANNOUNCEMENT, announcement, canonical_company, form_d, start_attempt
from app.v2.tests.db.financing_resolution_helpers import CANONICAL_TABLES, HUMAN, canonical_financing_counts
from app.v2.tests.db.resolution_helpers import untouched_snapshot
from app.v2.repositories import financing_event_candidates as candidates

pytestmark = pytest.mark.db

ANY = (IntegrityError, DBAPIError)
ME = human_authority(HUMAN)


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, FORM_D)
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    return db, company, candidate


def decision_sql(kind="create_event", by_kind="human", by_id="admin:jerrod", event="NULL", reason="NULL", candidate=":c"):
    return (f"INSERT INTO v2.financing_resolution_decision (candidate_id, decision_kind, financing_event_id, decided_by_kind, decided_by_id, reason_code) "
            f"VALUES ({candidate}, '{kind}', {event}, '{by_kind}', '{by_id}', {reason})")


# ---------------- AI is impossible; only human/rule; no rule is ever enabled

@pytest.mark.parametrize("by_kind", ["ai", "AI", "llm", "model", "system", "agent", ""])
def test_a_direct_insert_with_any_other_authority_kind_fails(world, by_kind):
    db, _, candidate = world
    before = canonical_financing_counts(db)
    _, message = refused(db, decision_sql("reject_candidate", by_kind, "admin:jerrod", reason="'nope'"), {"c": candidate.id}, exc=ANY)
    assert "ck_frd_authority_allowed" in message or "violates check constraint" in message
    assert canonical_financing_counts(db) == before


@pytest.mark.parametrize("actor", ["ai:gpt4", "admin:claude", "admin:openai", "bot:x"])
def test_a_human_decision_cannot_name_an_ai_actor(world, actor):
    db, _, candidate = world
    refused(db, decision_sql("reject_candidate", "human", actor, reason="'nope'"), {"c": candidate.id}, exc=ANY)


def test_a_rule_decision_is_always_refused_even_a_shape_valid_one(world):
    """No financing rule is enabled: EVERY 'rule' decision is refused, not just malformed ones."""
    db, company, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    b = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id="rule-1")[1].id, [announcement(company)]).candidates[0]
    _, message = refused(db, decision_sql("attach_to_event", "rule", "exact_financing_match.v1", event=f"'{event}'", candidate=":c"),
                         {"c": b.id}, exc=ANY)
    assert "no financing rule is enabled" in message


def test_a_rule_decision_still_must_be_shaped_as_an_attach_and_not_name_an_ai(world):
    db, _, candidate = world
    for kind, extra in (("create_event", dict(event="gen_random_uuid()")), ("reject_candidate", dict(reason="'nope'")),
                        ("defer_candidate", dict(reason="'later'"))):
        refused(db, decision_sql(kind, "rule", "exact_financing_match.v1", **extra), {"c": candidate.id}, exc=ANY)
    for actor in ("gpt_matcher.v1", "system", "exact_financing_match"):
        refused(db, decision_sql("attach_to_event", "rule", actor), {"c": candidate.id}, exc=ANY)


def test_the_schema_has_no_ai_authority_value_or_enum(migrated_db):
    with migrated_db.connect() as conn:
        definition = conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_frd_authority_allowed'")).scalar()
        enums = conn.execute(text("SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'v2' AND t.typtype = 'e'")).scalar()
    assert "'rule'" in definition and "'human'" in definition and "'ai'" not in definition.lower() and enums == 0


# ---------------- decision shape

def test_decision_kind_event_and_reason_shapes_are_enforced(world):
    db, _, candidate = world
    bad = [decision_sql("reject_candidate", event="gen_random_uuid()", reason="'nope'"), decision_sql("defer_candidate", event="gen_random_uuid()", reason="'later'"),
           decision_sql("reject_candidate"), decision_sql("defer_candidate"), decision_sql("attach_to_event"), decision_sql("create_event"),
           decision_sql("attach_to_event", event="gen_random_uuid()", reason="'x1'"), decision_sql("merge_events", event="gen_random_uuid()"),
           decision_sql("reject_candidate", reason="'Not A Code'")]
    for sql in bad:
        refused(db, sql, {"c": candidate.id}, exc=ANY)


def test_created_at_is_database_owned(world):
    db, _, candidate = world
    with db.begin() as conn:
        conn.execute(text("INSERT INTO v2.financing_resolution_decision (candidate_id, decision_kind, decided_by_kind, decided_by_id, reason_code, created_at) "
                          "VALUES (:c, 'defer_candidate', 'human', 'admin:jerrod', 'later', '2001-01-01T00:00:00Z')"), {"c": candidate.id})
        stamped = conn.execute(text("SELECT created_at FROM v2.financing_resolution_decision WHERE candidate_id = :c"), {"c": candidate.id}).scalar()
    assert stamped.year >= 2026


# ---------------- no contradictory resolutions

def test_one_final_decision_per_candidate_and_nothing_final_may_follow(world):
    db, _, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    refused(db, decision_sql("reject_candidate", reason="'again'"), {"c": candidate.id}, exc=ANY)
    refused(db, decision_sql("defer_candidate", reason="'again'"), {"c": candidate.id}, exc=ANY)
    refused(db, decision_sql("attach_to_event", event=f"'{event}'"), {"c": candidate.id}, exc=ANY)


def test_a_second_final_decision_on_the_same_candidate_is_refused(world):
    db, _, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    _, message = refused(db, decision_sql("attach_to_event", event=f"'{event}'"), {"c": candidate.id}, exc=ANY)
    assert "final resolution" in message or "unique" in message


def test_a_company_can_have_only_one_create_decision_per_event(world):
    db, _, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    refused(db, decision_sql("create_event", event=f"'{event}'"), {"c": candidate.id}, exc=ANY)


# ---------------- cross-company safety

def test_cross_company_attach_fails_at_the_database(world):
    db, company, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    other_company = canonical_company(db, "Globex Corporation", "globex.example")
    foreign = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id="cross-1")[1].id, [announcement(other_company)]).candidates[0]
    _, message = refused(db, decision_sql("attach_to_event", event=f"'{event}'", candidate=":c"), {"c": foreign.id}, exc=ANY)
    assert "own company" in message


def test_a_candidate_cannot_be_silently_assigned_to_two_canonical_events(world):
    db, company, candidate = world
    event_x = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    b = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id="two-1")[1].id, [announcement(company)]).candidates[0]
    promotion.attach_candidate_to_event(db, b.id, event_x, ME)
    other = candidates.persist_financing_event_candidates(db, start_attempt(db, FORM_D, record_id="two-2")[1].id, [form_d(company)]).candidates[0]
    event_y = promotion.create_event_from_candidate(db, other.id, ME).financing_event_id
    refused(db, decision_sql("attach_to_event", event=f"'{event_y}'", candidate=":c"), {"c": b.id}, exc=ANY)


# ---------------- FinancingEvent cannot exist without provenance

def test_a_bare_financing_event_cannot_be_committed(migrated_db):
    company = canonical_company(migrated_db)
    _, message = refused(migrated_db, "INSERT INTO v2.financing_event (company_id) VALUES (:c)", {"c": company}, exc=ANY)
    assert "create_event decision" in message
    assert canonical_financing_counts(migrated_db)["financing_event"] == 0


def test_financing_event_identity_and_timestamp_are_database_generated(world):
    db, company, candidate = world
    supplied = "11111111-1111-1111-1111-111111111111"
    with db.begin() as conn:
        eid = conn.execute(text("INSERT INTO v2.financing_event (id, company_id, created_at) VALUES (:i, :c, '2001-01-01T00:00:00Z') RETURNING id"),
                           {"i": supplied, "c": company}).scalar()
        conn.execute(text("INSERT INTO v2.financing_resolution_decision (candidate_id, decision_kind, financing_event_id, decided_by_kind, decided_by_id) "
                          "VALUES (:c, 'create_event', :e, 'human', 'admin:jerrod')"), {"c": candidate.id, "e": eid})
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.financing_event WHERE id = :i"), {"i": supplied}).scalar() == 0   # the id was overwritten
        row = conn.execute(text("SELECT id, created_at FROM v2.financing_event WHERE id = :i"), {"i": eid}).one()
    assert str(row.id) != supplied and row.created_at.year >= 2026   # neither id nor time is the writer's


# ---------------- accepted-fact acceptance rules

def test_a_stage_fact_must_come_from_a_human_decision_on_the_resolved_candidate_with_the_true_value(world):
    db, company, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    b = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id="stage-sql-1")[1].id, [announcement(company)]).candidates[0]
    d = promotion.attach_candidate_to_event(db, b.id, event, ME).decision.id
    sql = "INSERT INTO v2.financing_event_stage (financing_event_id, stage, resolution_decision_id, candidate_id) VALUES (:e, :s, :d, :c)"
    for stage, dec, cand in (("series_a", d, candidate.id), ("series_b", d, b.id), ("unknown", d, b.id)):
        refused(db, sql, {"e": event, "s": stage, "d": dec, "c": cand}, exc=ANY)
    with db.begin() as conn:      # the true value: accepted
        conn.execute(text(sql), {"e": event, "s": "series_a", "d": d, "c": b.id})


def test_a_verified_round_amount_fact_must_come_from_the_candidates_own_announced_amount_row(world):
    db, company, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    b = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id="amt-sql-1")[1].id, [announcement(company)]).candidates[0]
    d = promotion.attach_candidate_to_event(db, b.id, event, ME).decision.id
    with db.connect() as conn:
        b_amount_id = conn.execute(text("SELECT id FROM v2.financing_event_candidate_amount WHERE candidate_id = :c"), {"c": b.id}).scalar()
        a_amount_id = conn.execute(text("SELECT id FROM v2.financing_event_candidate_amount WHERE candidate_id = :c AND amount_semantics = 'offering_amount'"), {"c": candidate.id}).scalar()
    sql = ("INSERT INTO v2.financing_event_verified_round_amount (financing_event_id, currency_code, amount_minor_units, resolution_decision_id, candidate_amount_id) "
          "VALUES (:e, :cur, :m, :d, :ci)")
    refused(db, sql, {"e": event, "cur": "USD", "m": 2_000_000_000, "d": d, "ci": a_amount_id}, exc=ANY)     # from the WRONG candidate (offering, not announced)
    refused(db, sql, {"e": event, "cur": "USD", "m": 999, "d": d, "ci": b_amount_id}, exc=ANY)               # right row, wrong amount
    with db.begin() as conn:
        conn.execute(text(sql), {"e": event, "cur": "USD", "m": 2_000_000_000, "d": d, "ci": b_amount_id})


def test_a_date_fact_must_match_the_candidates_own_date_row_exactly(world):
    db, company, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    with db.connect() as conn:
        real_id = conn.execute(text("SELECT id FROM v2.financing_event_candidate_date WHERE candidate_id = :c AND date_kind = 'filing_date'"), {"c": candidate.id}).scalar()
        decision_id = conn.execute(text("SELECT id FROM v2.financing_resolution_decision WHERE candidate_id = :c"), {"c": candidate.id}).scalar()
    sql = ("INSERT INTO v2.financing_event_date (financing_event_id, date_kind, date_precision, date_start, resolution_decision_id, candidate_date_id) "
          "VALUES (:e, :k, :p, :s, :d, :ci)")
    refused(db, sql, {"e": event, "k": "filing_date", "p": "day", "s": "2000-01-01T00:00:00Z", "d": decision_id, "ci": real_id}, exc=ANY)   # wrong value for the real row
    with db.begin() as conn:
        conn.execute(text(sql), {"e": event, "k": "filing_date", "p": "day", "s": "2026-04-02T00:00:00Z", "d": decision_id, "ci": real_id})


def test_only_one_canonical_value_per_fact_kind_per_event(world):
    db, company, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(dates=(__import__("app.v2.domain.financing", fromlist=["FinancingDateKind"]).FinancingDateKind.FILING_DATE,))).financing_event_id
    b = candidates.persist_financing_event_candidates(db, start_attempt(db, FORM_D, record_id="onefact-1")[1].id, [form_d(company)]).candidates[0]
    d = promotion.attach_candidate_to_event(db, b.id, event, ME).decision.id
    with db.connect() as conn:
        other_id = conn.execute(text("SELECT id FROM v2.financing_event_candidate_date WHERE candidate_id = :c AND date_kind = 'filing_date'"), {"c": b.id}).scalar()
        row = conn.execute(text("SELECT date_precision, date_start FROM v2.financing_event_candidate_date WHERE id = :i"), {"i": other_id}).one()
    refused(db, "INSERT INTO v2.financing_event_date (financing_event_id, date_kind, date_precision, date_start, resolution_decision_id, candidate_date_id) "
               "VALUES (:e, 'filing_date', :p, :s, :d, :ci)", {"e": event, "p": row.date_precision, "s": row.date_start, "d": d, "ci": other_id}, exc=ANY)


def test_a_candidate_amount_row_can_only_ever_back_one_verified_amount_row(world):
    db, company, candidate = world
    event_x = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    b = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id="reuse-sql-1")[1].id, [announcement(company)]).candidates[0]
    promotion.attach_candidate_to_event(db, b.id, event_x, ME, FactSelection(verified_round_amount=True))
    other = candidates.persist_financing_event_candidates(db, start_attempt(db, FORM_D, record_id="reuse-sql-2")[1].id, [form_d(company)]).candidates[0]
    event_y = promotion.create_event_from_candidate(db, other.id, ME).financing_event_id
    with db.connect() as conn:
        b_amount_id = conn.execute(text("SELECT id FROM v2.financing_event_candidate_amount WHERE candidate_id = :c"), {"c": b.id}).scalar()
        d = conn.execute(text("SELECT id FROM v2.financing_resolution_decision WHERE candidate_id = :c"), {"c": other.id}).scalar()
    refused(db, "INSERT INTO v2.financing_event_verified_round_amount (financing_event_id, currency_code, amount_minor_units, resolution_decision_id, candidate_amount_id) "
               "VALUES (:e, 'USD', 2000000000, :d, :ci)", {"e": event_y, "d": d, "ci": b_amount_id}, exc=ANY)


def test_canonical_date_precision_cannot_overclaim_at_the_database(world):
    db, company, candidate = world
    event = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    with db.connect() as conn:
        decision_id = conn.execute(text("SELECT id FROM v2.financing_resolution_decision WHERE candidate_id = :c"), {"c": candidate.id}).scalar()
        filing_id = conn.execute(text("SELECT id FROM v2.financing_event_candidate_date WHERE candidate_id = :c AND date_kind = 'filing_date'"), {"c": candidate.id}).scalar()
    sql = ("INSERT INTO v2.financing_event_date (financing_event_id, date_kind, date_precision, date_start, resolution_decision_id, candidate_date_id) "
          "VALUES (:e, 'filing_date', :p, :s, :d, :ci)")
    # the candidate's real filing_date is DAY precision (2026-04-02); a canonical row cannot claim finer or coarser
    # detail than its precision says, no matter what the candidate row's own timestamp is:
    _, message = refused(db, sql, {"e": event, "p": "year", "s": "2026-04-02T00:00:00Z", "d": decision_id, "ci": filing_id}, exc=ANY)
    assert "start_matches_precision" in message or "check constraint" in message or "exact value" in message
    with pytest.raises(ANY):
        with db.begin() as conn:
            conn.execute(text(sql), {"e": event, "p": "decade", "s": "2026-04-02T00:00:00Z", "d": decision_id, "ci": filing_id})


# ---------------- append-only, restrict FKs

def _fully_populated_event(db, company, candidate):
    """One event with a row in every canonical fact table (stage, type, verified amount, date)."""
    from app.v2.domain.financing import FinancingDateKind
    event = promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(financing_type=True, dates=(FinancingDateKind.FIRST_SALE_DATE,))).financing_event_id
    b = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id="populate-1")[1].id, [announcement(company)]).candidates[0]
    promotion.attach_candidate_to_event(db, b.id, event, ME, FactSelection(stage=True, verified_round_amount=True))
    return event


@pytest.mark.parametrize("table", CANONICAL_TABLES)
def test_update_delete_and_truncate_are_blocked_on_every_financing_resolution_table(world, table):
    db, company, candidate = world
    _fully_populated_event(db, company, candidate)
    before = (canonical_financing_counts(db), untouched_snapshot(db))
    for sql in (f"UPDATE v2.{table} SET created_at = now()", f"DELETE FROM v2.{table}", f"TRUNCATE v2.{table} CASCADE",
                f"TRUNCATE v2.{table} RESTART IDENTITY CASCADE"):
        _, message = refused(db, sql, exc=ANY)
        assert "append-only" in message, sql
    assert (canonical_financing_counts(db), untouched_snapshot(db)) == before


def test_canonical_financing_rows_cannot_orphan_their_provenance(world):
    db, _, candidate = world
    promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(financing_type=True))
    for sql in ("DELETE FROM v2.financing_event_candidate", "DELETE FROM v2.company", "DELETE FROM v2.processing_attempt"):
        refused(db, sql, exc=ANY)
    with db.connect() as conn:
        defs = conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE contype = 'f' AND connamespace = 'v2'::regnamespace "
                                 "AND conrelid::regclass::text LIKE 'v2.financing_%' AND conrelid::regclass::text NOT LIKE '%_candidate%'")).all()
    assert defs and all("ON DELETE RESTRICT" in d[0] for d in defs)


def test_financing_resolution_never_modifies_the_candidate_layer_or_earlier_evidence(world):
    db, company, candidate = world
    before = untouched_snapshot(db)
    promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(financing_type=True, dates=(__import__("app.v2.domain.financing", fromlist=["FinancingDateKind"]).FinancingDateKind.FIRST_SALE_DATE,)))
    assert untouched_snapshot(db) == before
