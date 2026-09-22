"""Financing-event candidates through the real repository: untrusted proposals only, exact evidence, atomic."""

import uuid

import pytest
from sqlalchemy import text

from app.v2.domain.errors import InvalidInputError, InvariantViolationError, UnsupportedInputError
from app.v2.domain.financing import (
    AmountSemantics,
    FinancingDateKind,
    FinancingType,
    Stage,
    StoredFinancingEventCandidate,
)
from app.v2.domain.time import EventTime, EventTimePrecision
from app.v2.repositories import financing_event_candidates as repo
from app.v2.repositories import observations, processing_attempts as attempts, raw_payloads, sources
from app.v2.repositories.errors import ConflictError, NotFoundError
from app.v2.tests.db.evidence_helpers import count, ingest_one
from app.v2.tests.db.financing_fakes import (
    ANNOUNCEMENT,
    CONFLICTING,
    FORM_D,
    SEED_NEWS,
    announcement,
    canonical_company,
    form_d,
    make_financing,
    start_attempt,
)
from app.v2.tests.db.resolution_helpers import canonical_counts, untouched_snapshot

pytestmark = pytest.mark.db

FIN_TABLES = ("financing_event_candidate", "financing_event_candidate_amount", "financing_event_candidate_date")


def fin_counts(db):
    return {t: count(db, t) for t in FIN_TABLES}


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    observation, attempt = start_attempt(db, FORM_D)
    return db, company, observation, attempt


# ---------------- Form D semantics: offering != sold != verified

def test_form_d_offering_and_amount_sold_are_both_stored_and_stay_distinguishable(world):
    db, company, _, attempt = world
    stored = repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    assert isinstance(stored, StoredFinancingEventCandidate) and stored.TRUST_LEVEL == "untrusted_proposal"
    amounts = {a.semantics: a.money for a in stored.proposal.amounts}
    assert amounts[AmountSemantics.OFFERING_AMOUNT].minor_units == 1_000_000_000
    assert amounts[AmountSemantics.AMOUNT_SOLD].minor_units == 700_000_000
    assert amounts[AmountSemantics.OFFERING_AMOUNT] != amounts[AmountSemantics.AMOUNT_SOLD]
    assert AmountSemantics.ANNOUNCED_ROUND_AMOUNT not in amounts                    # nothing was collapsed into a "round size"
    assert stored.proposal.financing_type_value is FinancingType.EQUITY and stored.proposal.stage_value is Stage.UNKNOWN
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.financing_event_candidate_amount")).scalar() == 2
        columns = {r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name LIKE 'financing_event_candidate%'"))}
    for banned in ("amount", "funding_amount", "verified_round_amount", "round_amount", "event_date", "date", "confidence", "company_name", "domain", "url"):
        assert banned not in columns, banned


def test_dates_are_distinct_and_keep_their_precision(world):
    db, company, _, attempt = world
    stored = repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    dates = {d.kind: d.time for d in stored.proposal.dates}
    assert dates[FinancingDateKind.FIRST_SALE_DATE] == EventTime.of_day(2026, 3, 15) != dates[FinancingDateKind.FILING_DATE]
    assert FinancingDateKind.ANNOUNCEMENT_DATE not in dates


def test_an_announcement_proposes_an_announced_amount_and_a_stage_with_independent_evidence(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    observation, attempt = start_attempt(db, ANNOUNCEMENT)
    stored = repo.persist_financing_event_candidates(db, attempt.id, [announcement(company)]).candidates[0]
    p = stored.proposal
    assert [(a.semantics, a.money.currency_code, a.money.minor_units) for a in p.amounts] == [(AmountSemantics.ANNOUNCED_ROUND_AMOUNT, "USD", 2_000_000_000)]
    assert p.stage_value is Stage.SERIES_A and p.stage.evidence != p.amounts[0].evidence != p.event_evidence
    assert p.dates[0].kind is FinancingDateKind.ANNOUNCEMENT_DATE and p.dates[0].time.precision is EventTimePrecision.MONTH
    assert canonical_counts(db)["company"] == 1 and count(db, "resolution_decision") == 1   # only the company we made ourselves


def test_a_year_only_date_stays_a_year_in_the_database(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    payload = b"Acme Robotics raised a $3 million seed round in 2025."
    _, attempt = start_attempt(db, payload)
    proposal = make_financing(payload, company, event=b"Acme Robotics raised", stage=(Stage.SEED, b"seed round"),
                              dates=[(FinancingDateKind.ANNOUNCEMENT_DATE, EventTime.of_year(2025), b"2025")])
    stored = repo.persist_financing_event_candidates(db, attempt.id, [proposal]).candidates[0]
    (date,) = stored.proposal.dates
    assert date.time.precision is EventTimePrecision.YEAR and not date.time.is_exact
    with db.connect() as conn:
        assert conn.execute(text("SELECT date_precision FROM v2.financing_event_candidate_date")).scalar() == "year"


def test_unknown_stage_and_type_are_stored_as_unknown_and_amounts_never_infer_them(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    payload = b"Acme Robotics raised $500 million."
    _, attempt = start_attempt(db, payload)
    huge = make_financing(payload, company, event=b"Acme Robotics raised",
                          amounts=[(AmountSemantics.ANNOUNCED_ROUND_AMOUNT, "500000000", "USD", b"$500 million")])
    stored = repo.persist_financing_event_candidates(db, attempt.id, [huge]).candidates[0]
    assert stored.proposal.stage is None and stored.proposal.stage_value is Stage.UNKNOWN
    assert stored.proposal.financing_type_value is FinancingType.UNKNOWN
    with db.connect() as conn:
        row = conn.execute(text("SELECT stage, financing_type, stage_evidence_hash, type_evidence_hash FROM v2.financing_event_candidate")).one()
    assert tuple(row) == ("unknown", "unknown", None, None)


def test_explicit_seed_and_series_a_are_accepted_only_with_evidence(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, seed_attempt = start_attempt(db, SEED_NEWS)
    seed = make_financing(SEED_NEWS, company, event=b"Acme Robotics closed", stage=(Stage.SEED, b"seed round"))
    assert repo.persist_financing_event_candidates(db, seed_attempt.id, [seed]).candidates[0].proposal.stage_value is Stage.SEED
    _, a_attempt = start_attempt(db, ANNOUNCEMENT)
    assert repo.persist_financing_event_candidates(db, a_attempt.id, [announcement(company)]).candidates[0].proposal.stage_value is Stage.SERIES_A
    _, bad_attempt = start_attempt(db, ANNOUNCEMENT, record_id="other")
    unsupported = make_financing(ANNOUNCEMENT, company, event=b"announced a", stage=(Stage.SERIES_B, b"Series A"))
    with pytest.raises(InvalidInputError) as info:
        repo.persist_financing_event_candidates(db, bad_attempt.id, [unsupported])
    assert info.value.code == "stage_not_in_evidence"


# ---------------- the company

def test_the_company_must_already_exist_canonically_and_nothing_is_created(world):
    db, _, _, attempt = world
    before = (canonical_counts(db), untouched_snapshot(db))
    with pytest.raises(NotFoundError) as info:
        repo.persist_financing_event_candidates(db, attempt.id, [form_d(uuid.uuid4())])
    assert info.value.code == "company_not_found"
    assert fin_counts(db) == dict.fromkeys(FIN_TABLES, 0) and (canonical_counts(db), untouched_snapshot(db)) == before


def test_the_company_is_a_real_fk_and_the_company_name_is_not_stored_on_the_candidate(world):
    db, company, _, attempt = world
    stored = repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    assert stored.proposal.company_id == company
    with db.connect() as conn:
        fk = conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'fk_fec_company_id'")).scalar()
        columns = [r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='financing_event_candidate'"))]
    assert "REFERENCES v2.company(id)" in fk and "ON DELETE RESTRICT" in fk
    assert "company_id" in columns and not [c for c in columns if "name" in c or "domain" in c or "url" in c]
    assert [c.id for c in repo.list_financing_event_candidates_for_company(db, company)] == [stored.id]


def test_a_financing_candidate_can_never_create_or_change_a_company(world):
    db, company, _, attempt = world
    before = (canonical_counts(db), untouched_snapshot(db))
    repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    assert (canonical_counts(db), untouched_snapshot(db)) == before


# ---------------- processing attempt

def test_only_a_processing_attempt_accepts_candidates_and_it_is_never_modified(world):
    db, company, _, attempt = world
    before = attempts.get_processing_attempt(db, attempt.id)
    repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    assert attempts.get_processing_attempt(db, attempt.id) == before            # not completed, not touched
    attempts.mark_processed(db, attempt.id)
    frozen = untouched_snapshot(db)
    with pytest.raises(InvariantViolationError) as info:
        repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    assert info.value.code == "attempt_not_processing" and untouched_snapshot(db) == frozen


@pytest.mark.parametrize("terminal", ["failed", "quarantined"])
def test_failed_and_quarantined_attempts_reject_candidates(migrated_db, terminal):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, FORM_D)
    (attempts.mark_failed if terminal == "failed" else attempts.mark_quarantined)(db, attempt.id, "some_reason")
    with pytest.raises(InvariantViolationError):
        repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    assert fin_counts(db) == dict.fromkeys(FIN_TABLES, 0)


def test_an_unknown_attempt_is_not_found_and_bad_ids_are_refused(world):
    db, company, _, _ = world
    with pytest.raises(NotFoundError):
        repo.persist_financing_event_candidates(db, 999999, [form_d(company)])
    for bad in (0, -1, True, "1", None):
        with pytest.raises(InvalidInputError):
            repo.persist_financing_event_candidates(db, bad, [form_d(company)])


def test_only_financing_proposals_are_accepted(world):
    db, _, _, attempt = world
    for bad in ("x", {"company_id": 1}, object()):
        with pytest.raises(InvalidInputError):
            repo.persist_financing_event_candidates(db, attempt.id, [bad])
    assert fin_counts(db) == dict.fromkeys(FIN_TABLES, 0)


# ---------------- evidence and media

def test_evidence_from_another_payload_or_with_a_wrong_hash_is_rejected_and_nothing_is_stored(world):
    db, company, _, attempt = world
    with pytest.raises(InvalidInputError):
        repo.persist_financing_event_candidates(db, attempt.id, [announcement(company, ANNOUNCEMENT)])   # locators hashed over a different payload
    assert fin_counts(db) == dict.fromkeys(FIN_TABLES, 0)


@pytest.mark.parametrize("data, event", [(b"%PDF-1.7 Issuer Acme Total offering amount $10,000,000 stream\x00\x01", b"Total offering"),
                                         (b"\x00\x01\x02 binary Total offering $10,000,000", b"Total offering")])
def test_binary_evidence_is_refused(migrated_db, data, event):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, data)
    proposal = make_financing(data, company, event=event, amounts=[(AmountSemantics.OFFERING_AMOUNT, "10000000", "USD", b"$10,000,000")])
    with pytest.raises(UnsupportedInputError) as info:
        repo.persist_financing_event_candidates(db, attempt.id, [proposal])
    assert info.value.code == "evidence_media_unsupported" and fin_counts(db) == dict.fromkeys(FIN_TABLES, 0)


# ---------------- multiple observations: conflict is preserved, never merged

def test_two_observations_can_yield_conflicting_untrusted_candidates_and_nothing_is_merged(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, first = start_attempt(db, ANNOUNCEMENT)
    _, second = start_attempt(db, CONFLICTING)
    a = repo.persist_financing_event_candidates(db, first.id, [announcement(company)]).candidates[0]
    b = repo.persist_financing_event_candidates(db, second.id, [announcement(company, CONFLICTING, "25000000")]).candidates[0]
    assert a.id != b.id
    amounts = {c.id: c.proposal.amounts[0].money.minor_units for c in repo.list_financing_event_candidates_for_company(db, company)}
    assert amounts == {a.id: 2_000_000_000, b.id: 2_500_000_000}
    assert fin_counts(db)["financing_event_candidate"] == 2
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.financing_event")).scalar() == 0   # nothing was merged into a canonical event


# ---------------- idempotency

def test_replaying_a_batch_does_not_duplicate_and_returns_the_same_candidates(world):
    db, company, _, attempt = world
    first = repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    again = repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    assert first.created == (True,) and again.created == (False,) and first.candidates == again.candidates
    assert fin_counts(db) == {"financing_event_candidate": 1, "financing_event_candidate_amount": 2, "financing_event_candidate_date": 2}


def test_replay_is_independent_of_the_order_facts_were_listed_in(world):
    db, company, _, attempt = world
    proposal = form_d(company)
    repo.persist_financing_event_candidates(db, attempt.id, [proposal])
    reordered = proposal.model_copy(update={"amounts": tuple(reversed(proposal.amounts)), "dates": tuple(reversed(proposal.dates))})
    assert repo.persist_financing_event_candidates(db, attempt.id, [reordered]).created == (False,)


def test_a_changed_proposal_at_the_same_ordinal_conflicts_and_is_never_overwritten(world):
    db, company, _, attempt = world
    original = repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    changed = make_financing(FORM_D, company, event=b"SEC Form D notice", ftype=(FinancingType.EQUITY, b"Equity"),
                             amounts=[(AmountSemantics.OFFERING_AMOUNT, "99000000", "USD", b"$10,000,000")])
    with pytest.raises(ConflictError) as info:
        repo.persist_financing_event_candidates(db, attempt.id, [changed])
    assert info.value.code == "candidate_ordinal_conflict"
    assert repo.get_financing_event_candidate(db, original.id) == original


def test_a_different_company_at_the_same_ordinal_is_also_a_conflict(world):
    db, company, _, attempt = world
    repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    other = canonical_company(db, "Globex Corporation", "globex.example")
    with pytest.raises(ConflictError):
        repo.persist_financing_event_candidates(db, attempt.id, [form_d(other)])


def test_a_later_processor_version_adds_another_candidate_never_an_update(world):
    db, company, observation, attempt = world
    repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    attempts.mark_processed(db, attempt.id)
    later = attempts.start_processing(db, observation.id, "fin_extractor_v2_proc", "fin_extractor_v2_proc.v1")
    repo.persist_financing_event_candidates(db, later.id, [form_d(company)])
    assert [c.processing_attempt_id for c in repo.list_financing_event_candidates_for_observation(db, observation.id)] == [attempt.id, later.id]


# ---------------- atomicity

def test_an_invalid_second_candidate_rolls_back_the_first(world):
    db, company, _, attempt = world
    bad = make_financing(FORM_D, company, ftype=(FinancingType.DEBT, b"Equity"))                    # "debt" is not stated in its evidence
    with pytest.raises(InvalidInputError):
        repo.persist_financing_event_candidates(db, attempt.id, [form_d(company), bad])
    assert fin_counts(db) == dict.fromkeys(FIN_TABLES, 0)


def test_a_conflict_at_a_later_ordinal_rolls_back_the_whole_batch(world):
    db, company, _, attempt = world
    first = form_d(company)
    second = make_financing(FORM_D, company, event=b"SEC Form D notice")
    repo.persist_financing_event_candidates(db, attempt.id, [first, second])
    before = fin_counts(db)
    changed_second = make_financing(FORM_D, company, event=b"Date of first sale")             # a DIFFERENT proposal at ordinal 2
    third = make_financing(FORM_D, company, event=b"Issuer: Acme")                             # a would-be new ordinal 3
    with pytest.raises(ConflictError):
        repo.persist_financing_event_candidates(db, attempt.id, [first, changed_second, third])
    assert fin_counts(db) == before                                                            # ordinal 3 was not stored either


def test_on_a_connection_a_failed_batch_undoes_only_itself(world):
    db, company, _, attempt = world
    bad = make_financing(FORM_D, company, ftype=(FinancingType.DEBT, b"Equity"))
    with db.begin() as conn:
        _, other_attempt = start_attempt(conn, FORM_D, record_id="caller-work")           # the caller's earlier work in its transaction
        repo.persist_financing_event_candidates(conn, attempt.id, [form_d(company)])
        with pytest.raises(InvalidInputError):
            repo.persist_financing_event_candidates(conn, other_attempt.id, [form_d(company), bad])
        assert count(conn, "financing_event_candidate") == 1                                # the caller's earlier work survived
    assert fin_counts(db)["financing_event_candidate"] == 1 and attempts.get_processing_attempt(db, other_attempt.id) is not None


def test_a_batch_may_not_exceed_the_cap(world):
    db, company, _, attempt = world
    with pytest.raises(InvalidInputError) as info:
        repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)] * 51)
    assert info.value.code == "too_many_candidates"


# ---------------- preservation and provenance

def test_persisting_candidates_changes_nothing_but_the_financing_tables(world):
    db, company, _, attempt = world
    before = (untouched_snapshot(db), canonical_counts(db))
    with db.connect() as conn:
        canonical = conn.execute(text("SELECT (SELECT array_agg(t::text ORDER BY id) FROM v2.company t), (SELECT array_agg(t::text ORDER BY id) FROM v2.resolution_decision t)")).one()
    repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
    assert (untouched_snapshot(db), canonical_counts(db)) == before
    with db.connect() as conn:
        assert tuple(conn.execute(text("SELECT (SELECT array_agg(t::text ORDER BY id) FROM v2.company t), (SELECT array_agg(t::text ORDER BY id) FROM v2.resolution_decision t)")).one()) == tuple(canonical)


def test_provenance_reaches_the_company_and_separately_the_source_through_the_attempt(world):
    db, company, observation, attempt = world
    stored = repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    assert stored.proposal.company_id == company                                                    # candidate -> Company
    walked_attempt = attempts.get_processing_attempt(db, stored.processing_attempt_id)              # candidate -> attempt
    walked_observation = observations.get_observation_by_id(db, walked_attempt.observation_id)      # -> observation
    payload = raw_payloads.get_raw_payload(db, walked_observation.observation.content_hash, verify=True)   # -> payload
    source = sources.get_source_by_key(db, walked_observation.observation.source_key)               # -> source
    assert (walked_observation.id, payload.payload_bytes, source.source.source_key) == (observation.id, FORM_D, "sec_edgar")
    with db.connect() as conn:                                                                      # and it is one SQL join too
        row = conn.execute(text("SELECT s.source_key FROM v2.financing_event_candidate c JOIN v2.processing_attempt a ON a.id = c.processing_attempt_id "
                                "JOIN v2.observation o ON o.id = a.observation_id JOIN v2.raw_payload p ON p.content_hash = o.content_hash "
                                "JOIN v2.source s ON s.id = o.source_id WHERE c.id = :i"), {"i": stored.id}).one()
    assert row.source_key == "sec_edgar"
    with db.connect() as conn:
        columns = {r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='financing_event_candidate'"))}
    assert not {"observation_id", "source_id", "source_key", "content_hash"} & columns              # never duplicated onto the candidate


def test_created_at_is_the_database_clock_and_there_is_no_updated_at(world):
    db, company, _, attempt = world
    stored = repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    assert stored.created_at.year >= 2026
    with db.connect() as conn:
        columns = {r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name LIKE 'financing_event_candidate%'"))}
    assert "updated_at" not in columns and "updated_time" not in columns
