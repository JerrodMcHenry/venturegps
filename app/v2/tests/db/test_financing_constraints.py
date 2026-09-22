"""Direct-SQL attacks on the financing-candidate tables: the database is the last line, whatever the writer."""

import hashlib
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.v2.repositories import financing_event_candidates as repo
from app.v2.repositories import processing_attempts as attempts
from app.v2.tests.db.evidence_helpers import count, refused
from app.v2.tests.db.financing_fakes import FORM_D, canonical_company, form_d, start_attempt
from app.v2.tests.db.resolution_helpers import canonical_counts, untouched_snapshot

pytestmark = pytest.mark.db

ANY = (IntegrityError, DBAPIError)
TABLES = ("financing_event_candidate", "financing_event_candidate_amount", "financing_event_candidate_date")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def span(needle: bytes, payload: bytes = FORM_D):
    i = payload.index(needle)
    return i, i + len(needle), sha(needle)


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, FORM_D)
    return db, company, attempt


def insert_candidate(db, company, attempt_id, *, ordinal=1, needle=b"SEC Form D", extra="", extra_values="", event_hash=None, bounds=None, **binds):
    s, e, h = span(needle)
    if bounds:
        s, e = bounds
    sql = (f"INSERT INTO v2.financing_event_candidate (processing_attempt_id, company_id, candidate_ordinal, "
           f"event_evidence_start, event_evidence_end, event_evidence_hash{extra}) VALUES (:a, :c, :o, :s, :e, :h{extra_values}) RETURNING id")
    with db.begin() as conn:
        return conn.execute(text(sql), dict(a=attempt_id, c=company, o=ordinal, s=s, e=e, h=event_hash or h, **binds)).scalar()


def try_candidate(db, company, attempt_id, **kw):
    with pytest.raises(ANY) as info:
        insert_candidate(db, company, attempt_id, **kw)
    return str(info.value.orig)


# ---------------- structure and evidence

def test_a_valid_direct_insert_is_accepted_and_stamped_by_the_database(world):
    db, company, attempt = world
    insert_candidate(db, company, attempt.id)
    with db.connect() as conn:
        row = conn.execute(text("SELECT stage, financing_type, created_at FROM v2.financing_event_candidate")).one()
    assert (row.stage, row.financing_type) == ("unknown", "unknown") and row.created_at.year >= 2026


def test_created_at_is_database_owned(world):
    db, company, attempt = world
    insert_candidate(db, company, attempt.id, extra=", created_at", extra_values=", '2001-01-01T00:00:00Z'")
    with db.connect() as conn:
        assert conn.execute(text("SELECT created_at FROM v2.financing_event_candidate")).scalar().year >= 2026


def test_a_nonexistent_company_and_a_nonexistent_attempt_are_rejected_by_foreign_keys(world):
    db, company, attempt = world
    assert "fk_fec_company_id" in try_candidate(db, uuid.uuid4(), attempt.id)
    assert "fk_fec_processing_attempt_id" in try_candidate(db, company, 987654)
    assert count(db, "financing_event_candidate") == 0


@pytest.mark.parametrize("kw", [
    dict(event_hash="0" * 64),                                   # a wrong hash
    dict(event_hash="nothex"),                                   # a malformed hash
    dict(bounds=(0, 10**6)),                                     # past the end of the payload
    dict(bounds=(50, 40)),                                       # a reversed span
    dict(bounds=(10, 10)),                                       # an empty span
    dict(bounds=(-1, 5)),                                        # a negative start
])
def test_event_evidence_must_hash_to_the_exact_stored_bytes(world, kw):
    db, company, attempt = world
    message = try_candidate(db, company, attempt.id, **kw)
    assert "evidence" in message.lower() or "violates check constraint" in message
    assert count(db, "financing_event_candidate") == 0


def test_a_span_that_is_right_for_another_payload_is_rejected(world):
    db, company, attempt = world
    with pytest.raises(ANY):
        insert_candidate(db, company, attempt.id, bounds=(0, 9), event_hash=sha(b"Acme Robo"))     # bytes that are not at [0, 9)


def test_event_level_evidence_columns_are_mandatory(world):
    db, company, attempt = world
    refused(db, "INSERT INTO v2.financing_event_candidate (processing_attempt_id, company_id, candidate_ordinal) VALUES (:a, :c, 1)",
            {"a": attempt.id, "c": company}, exc=ANY)


def test_only_a_processing_attempt_accepts_direct_inserts(world):
    db, company, attempt = world
    attempts.mark_processed(db, attempt.id)
    assert "processing" in try_candidate(db, company, attempt.id)
    assert count(db, "financing_event_candidate") == 0


def test_ordinals_are_unique_per_attempt_and_bounded(world):
    db, company, attempt = world
    insert_candidate(db, company, attempt.id)
    assert "uq_financing_event_candidate_ordinal" in try_candidate(db, company, attempt.id)
    for bad in (0, 1001, -1):
        try_candidate(db, company, attempt.id, ordinal=bad)


# ---------------- stage / type vocabulary and evidence pairing

def _pairing_refused(message: str, constraint: str) -> bool:
    """The BEFORE INSERT trigger may fire before the CHECK: either refusal is the database saying no."""
    return constraint in message or "evidence does not match the stored payload bytes" in message


def stage_kw(stage, with_evidence):
    s, e, h = span(b"Equity")
    if with_evidence:
        return dict(extra=", stage, stage_evidence_start, stage_evidence_end, stage_evidence_hash",
                    extra_values=", :st, :ss, :se, :sh", st=stage, ss=s, se=e, sh=h)
    return dict(extra=", stage", extra_values=", :st", st=stage)


def test_stage_needs_evidence_unless_unknown_and_unknown_cannot_carry_evidence(world):
    db, company, attempt = world
    for stage in ("seed", "series_a", "pre_seed", "series_b", "growth"):
        assert _pairing_refused(try_candidate(db, company, attempt.id, **stage_kw(stage, False)), "stage_evidence_matches_stage")
    assert _pairing_refused(try_candidate(db, company, attempt.id, **stage_kw("unknown", True)), "stage_evidence_matches_stage")
    for stage in ("series_c", "Seed", "", "ipo"):
        try_candidate(db, company, attempt.id, **stage_kw(stage, True))
    insert_candidate(db, company, attempt.id, ordinal=2, **stage_kw("seed", True))      # stated + evidenced: the DB does not judge the phrase


def test_a_stated_stage_must_still_hash_to_real_bytes(world):
    db, company, attempt = world
    with pytest.raises(ANY):
        insert_candidate(db, company, attempt.id, extra=", stage, stage_evidence_start, stage_evidence_end, stage_evidence_hash",
                         extra_values=", 'seed', 0, 5, :sh", sh=sha(b"nope!"))


def test_financing_type_vocabulary_and_evidence_pairing(world):
    db, company, attempt = world
    s, e, h = span(b"Equity")
    cols = ", financing_type, type_evidence_start, type_evidence_end, type_evidence_hash"
    for ftype in ("revenue_based", "EQUITY", "warrant", ""):
        try_candidate(db, company, attempt.id, extra=cols, extra_values=", :t, :s2, :e2, :h2", t=ftype, s2=s, e2=e, h2=h)
    assert _pairing_refused(try_candidate(db, company, attempt.id, extra=", financing_type", extra_values=", 'equity'"), "type_evidence_matches_type")
    for ftype in ("equity", "convertible", "debt", "other"):
        insert_candidate(db, company, attempt.id, ordinal={"equity": 3, "convertible": 4, "debt": 5, "other": 6}[ftype],
                         extra=cols, extra_values=", :t, :s2, :e2, :h2", t=ftype, s2=s, e2=e, h2=h)


# ---------------- amounts

@pytest.fixture
def parent(world):
    db, company, attempt = world
    return db, company, attempt, insert_candidate(db, company, attempt.id)


def insert_amount(db, cid, semantics="offering_amount", currency="USD", minor=1000, needle=b"$10,000,000", **over):
    s, e, h = span(needle)
    values = dict(c=cid, sem=semantics, cur=currency, m=minor, s=s, e=e, h=h)
    values.update(over)
    with db.begin() as conn:
        conn.execute(text("INSERT INTO v2.financing_event_candidate_amount (candidate_id, amount_semantics, currency_code, amount_minor_units, "
                          "evidence_start, evidence_end, evidence_hash) VALUES (:c, :sem, :cur, :m, :s, :e, :h)"), values)


def amount_refused(db, cid, **kw):
    with pytest.raises(ANY) as info:
        insert_amount(db, cid, **kw)
    return str(info.value.orig)


def test_the_three_semantics_are_stored_side_by_side_as_distinct_rows(parent):
    db, _, _, cid = parent
    insert_amount(db, cid, "offering_amount", minor=1_000_000_000)
    insert_amount(db, cid, "amount_sold", minor=700_000_000, needle=b"$7,000,000")
    insert_amount(db, cid, "announced_round_amount", minor=2_000_000_000)
    with db.connect() as conn:
        assert conn.execute(text("SELECT amount_semantics, amount_minor_units FROM v2.financing_event_candidate_amount ORDER BY id")).all() == [
            ("offering_amount", 1_000_000_000), ("amount_sold", 700_000_000), ("announced_round_amount", 2_000_000_000)]


def test_amount_semantics_are_a_closed_vocabulary_with_no_generic_or_verified_value(parent):
    db, _, _, cid = parent
    for bad in ("amount", "funding_amount", "verified_round_amount", "round_amount", "", "OFFERING_AMOUNT"):
        assert "semantics_allowed" in amount_refused(db, cid, semantics=bad)
    insert_amount(db, cid, "amount_sold")
    assert "uq_financing_event_candidate_amount_semantics" in amount_refused(db, cid, semantics="amount_sold")


def test_the_currency_is_mandatory_and_shaped_and_never_defaulted(parent):
    db, _, _, cid = parent
    for bad in ("usd", "US", "USDX", "", "$", "12A"):
        assert "currency_shape" in amount_refused(db, cid, currency=bad)
    assert "null value" in amount_refused(db, cid, currency=None)              # no silent USD
    with db.connect() as conn:
        assert conn.execute(text("SELECT column_default FROM information_schema.columns WHERE table_schema='v2' AND table_name='financing_event_candidate_amount' "
                                 "AND column_name='currency_code'")).scalar() is None


def test_money_is_exact_bigint_minor_units_never_a_float_or_negative(parent):
    db, _, _, cid = parent
    with db.connect() as conn:
        types = dict(conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='v2' AND table_name='financing_event_candidate_amount'")).all())
        floats = conn.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='v2' AND table_name LIKE 'financing_event_candidate%' "
                                   "AND data_type IN ('real','double precision','numeric')")).scalar()
    assert types["amount_minor_units"] == "bigint" and floats == 0
    assert "non_negative" in amount_refused(db, cid, minor=-1)
    insert_amount(db, cid, "offering_amount", minor=2**63 - 1)                 # exact at the extreme
    with db.connect() as conn:
        assert conn.execute(text("SELECT amount_minor_units FROM v2.financing_event_candidate_amount")).scalar() == 2**63 - 1
    with pytest.raises(ANY):
        insert_amount(db, cid, "amount_sold", minor=2**63)                     # out of range: refused, not rounded


def test_amount_evidence_must_hash_to_real_bytes_and_a_span_error_is_refused(parent):
    db, _, _, cid = parent
    for over in (dict(h="0" * 64), dict(s=0, e=10**6), dict(s=30, e=20), dict(h="zz")):
        with pytest.raises(ANY):
            insert_amount(db, cid, **over)
    assert count(db, "financing_event_candidate_amount") == 0


def test_amounts_cannot_be_added_once_the_attempt_is_terminal(parent):
    db, _, attempt, cid = parent
    attempts.mark_processed(db, attempt.id)
    assert "processing" in amount_refused(db, cid)


# ---------------- dates

def insert_date(db, cid, kind="filing_date", precision="day", start="2026-04-02T00:00:00Z", needle=b"2026-04-02", **over):
    s, e, h = span(needle)
    values = dict(c=cid, k=kind, p=precision, d=start, s=s, e=e, h=h)
    values.update(over)
    with db.begin() as conn:
        conn.execute(text("INSERT INTO v2.financing_event_candidate_date (candidate_id, date_kind, date_precision, date_start, evidence_start, evidence_end, evidence_hash) "
                          "VALUES (:c, :k, :p, :d, :s, :e, :h)"), values)


def date_refused(db, cid, **kw):
    with pytest.raises(ANY) as info:
        insert_date(db, cid, **kw)
    return str(info.value.orig)


def test_dates_are_distinct_kinds_with_their_own_precision_and_no_generic_event_date(parent):
    db, _, _, cid = parent
    insert_date(db, cid, "first_sale_date", needle=b"2026-03-15", start="2026-03-15T00:00:00Z")
    insert_date(db, cid, "filing_date")
    for bad in ("event_date", "announced", "date", ""):
        assert "kind_allowed" in date_refused(db, cid, kind=bad)
    assert "uq_financing_event_candidate_date_kind" in date_refused(db, cid, kind="filing_date")


def test_precision_cannot_overclaim_a_day_a_month_or_a_time(parent):
    db, _, _, cid = parent
    assert "start_matches_precision" in date_refused(db, cid, kind="filing_date", precision="year", start="2026-03-01T00:00:00Z")
    assert "start_matches_precision" in date_refused(db, cid, kind="filing_date", precision="month", start="2026-03-15T00:00:00Z")
    assert "start_matches_precision" in date_refused(db, cid, kind="filing_date", precision="day", start="2026-03-15T10:00:00Z")
    assert "precision_allowed" in date_refused(db, cid, kind="filing_date", precision="decade")
    insert_date(db, cid, "announcement_date", precision="year", start="2026-01-01T00:00:00Z")           # a year stays a year
    with db.connect() as conn:
        assert conn.execute(text("SELECT date_precision FROM v2.financing_event_candidate_date")).scalar() == "year"


# ---------------- immutability

UPDATE_SET = {"financing_event_candidate": "created_at = now()", "financing_event_candidate_amount": "currency_code = 'EUR'",
              "financing_event_candidate_date": "date_kind = 'filing_date'"}


@pytest.fixture
def populated(world):
    db, company, attempt = world
    repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    return db


@pytest.mark.parametrize("table", TABLES)
def test_update_delete_and_truncate_are_blocked_on_every_financing_table(populated, table):
    db = populated
    before = (untouched_snapshot(db), canonical_counts(db), {t: count(db, t) for t in TABLES})
    for sql in (f"UPDATE v2.{table} SET {UPDATE_SET[table]}", f"DELETE FROM v2.{table}", f"TRUNCATE v2.{table} CASCADE",
                f"TRUNCATE v2.{table} RESTART IDENTITY CASCADE"):
        _, message = refused(db, sql, exc=ANY)
        assert "append-only" in message, sql
    assert (untouched_snapshot(db), canonical_counts(db), {t: count(db, t) for t in TABLES}) == before


def test_a_plain_truncate_of_the_parent_or_the_company_is_refused_by_the_foreign_keys(populated):
    for sql in ("TRUNCATE v2.financing_event_candidate", "TRUNCATE v2.company"):
        _, message = refused(populated, sql, exc=ANY)
        assert "foreign key" in message


def test_an_upsert_cannot_rewrite_a_candidate(world):
    db, company, attempt = world
    insert_candidate(db, company, attempt.id)
    s, e, h = span(b"Issuer: Acme")
    _, message = refused(db, "INSERT INTO v2.financing_event_candidate (processing_attempt_id, company_id, candidate_ordinal, event_evidence_start, "
                             "event_evidence_end, event_evidence_hash) VALUES (:a, :c, 1, :s, :e, :h) ON CONFLICT (processing_attempt_id, candidate_ordinal) "
                             "DO UPDATE SET candidate_ordinal = 1", {"a": attempt.id, "c": company, "s": s, "e": e, "h": h}, exc=ANY)
    assert "append-only" in message


def test_financing_rows_cannot_orphan_their_provenance_and_all_foreign_keys_restrict(populated):
    db = populated
    for sql in ("DELETE FROM v2.company", "DELETE FROM v2.processing_attempt", "DELETE FROM v2.observation"):
        refused(db, sql, exc=ANY)
    with db.connect() as conn:
        defs = conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE contype = 'f' AND conrelid::regclass::text LIKE 'v2.financing_event_candidate%'")).scalars().all()
    assert len(defs) == 4 and all("ON DELETE RESTRICT" in d for d in defs)
