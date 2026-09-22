"""Concurrent financing-candidate persistence: the database and the row locks are the final authority."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.v2.domain.errors import InvariantViolationError
from app.v2.domain.financing import FinancingType
from app.v2.repositories import financing_event_candidates as repo
from app.v2.repositories import processing_attempts as attempts
from app.v2.repositories.errors import ConflictError
from app.v2.tests.db.evidence_helpers import count
from app.v2.tests.db.financing_fakes import FORM_D, canonical_company, form_d, make_financing, start_attempt

pytestmark = pytest.mark.db


def run_all(fn, n=16):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(fn, range(n)))


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, FORM_D)
    return db, company, attempt


def test_concurrent_replay_produces_exactly_one_stored_candidate_with_its_facts(world):
    db, company, attempt = world
    results = run_all(lambda _: repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)]))
    assert sum(r.created_count for r in results) == 1
    assert (count(db, "financing_event_candidate"), count(db, "financing_event_candidate_amount"), count(db, "financing_event_candidate_date")) == (1, 2, 2)
    assert len({r.candidates[0].id for r in results}) == 1 and len({r.candidates[0] for r in results}) == 1


def test_concurrent_conflicting_proposals_at_one_ordinal_admit_exactly_one_winner(world):
    db, company, attempt = world
    a = form_d(company)
    b = make_financing(FORM_D, company, event=b"SEC Form D notice", ftype=(FinancingType.EQUITY, b"Equity"))
    def store(i):
        try:
            return repo.persist_financing_event_candidates(db, attempt.id, [a if i % 2 == 0 else b]).created
        except ConflictError as exc:
            return exc.code
    results = run_all(store)
    assert count(db, "financing_event_candidate") == 1
    assert results.count((True,)) == 1 and all(r in ((True,), (False,), "candidate_ordinal_conflict") for r in results)


def test_completing_the_attempt_races_persistence_without_a_half_written_candidate(world):
    db, company, attempt = world
    def act(i):
        try:
            if i == 0:
                attempts.mark_processed(db, attempt.id)
                return "processed"
            repo.persist_financing_event_candidates(db, attempt.id, [form_d(company)])
            return "stored"
        except (InvariantViolationError, ConflictError):
            return "refused"
    run_all(act, 12)
    stored = count(db, "financing_event_candidate")
    assert stored in (0, 1) and count(db, "financing_event_candidate_amount") == 2 * stored and count(db, "financing_event_candidate_date") == 2 * stored
