"""Concurrent financing resolution: the database (row locks + unique indexes) is the final authority."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.v2.domain.financing_resolution import FactSelection, FinancingCandidateResolutionState
from app.v2.domain.resolution import human_authority
from app.v2.financing_resolution import promotion
from app.v2.financing_resolution.errors import FactAlreadyAcceptedError, FinancingCandidateAlreadyResolvedError
from app.v2.repositories import financing_event_candidates as candidates
from app.v2.repositories import financing_events as events
from app.v2.repositories.errors import ConflictError
from app.v2.tests.db.financing_fakes import ANNOUNCEMENT, FORM_D, announcement, canonical_company, form_d, start_attempt
from app.v2.tests.db.financing_resolution_helpers import HUMAN, canonical_financing_counts

pytestmark = pytest.mark.db

ME = human_authority(HUMAN)


def run_all(fn, n=12):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(fn, range(n)))


def outcome(fn):
    try:
        return fn()
    except ConflictError as exc:
        return type(exc)


@pytest.fixture
def candidate_and_company(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, FORM_D)
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    return db, company, candidate


def test_concurrent_create_from_the_same_candidate_creates_exactly_one_event(candidate_and_company):
    db, _, candidate = candidate_and_company
    results = run_all(lambda _: outcome(lambda: promotion.create_event_from_candidate(db, candidate.id, ME)))
    assert canonical_financing_counts(db)["financing_event"] == 1
    assert sum(1 for r in results if not isinstance(r, type)) == 1
    assert all(r is FinancingCandidateAlreadyResolvedError for r in results if isinstance(r, type))


def test_concurrent_final_decisions_cannot_split_a_candidate_across_events(candidate_and_company):
    db, company, candidate = candidate_and_company
    other_candidate = candidates.persist_financing_event_candidates(db, start_attempt(db, FORM_D, record_id="other-event")[1].id, [form_d(company)]).candidates[0]
    other = promotion.create_event_from_candidate(db, other_candidate.id, ME).financing_event_id
    def act(i):
        return outcome(lambda: promotion.create_event_from_candidate(db, candidate.id, ME) if i % 2 == 0
                       else promotion.attach_candidate_to_event(db, candidate.id, other, ME))
    results = run_all(act, 16)
    finals = [d for d in events.list_decisions_for_financing_candidate(db, candidate.id) if d.is_final]
    assert len(finals) == 1
    assert sum(1 for r in results if not isinstance(r, type)) == 1


def test_concurrent_attach_preserves_one_final_decision_per_candidate(candidate_and_company):
    db, company, candidate = candidate_and_company
    x = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    b = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id="attach-race")[1].id, [announcement(company)]).candidates[0]
    results = run_all(lambda _: outcome(lambda: promotion.attach_candidate_to_event(db, b.id, x, ME)))
    assert sum(1 for r in results if not isinstance(r, type)) == 1
    assert events.get_financing_candidate_resolution_state(db, b.id) is FinancingCandidateResolutionState.ATTACHED


def test_concurrent_fact_acceptance_admits_exactly_one_winner_per_event(candidate_and_company):
    db, company, candidate = candidate_and_company
    x = promotion.create_event_from_candidate(db, candidate.id, ME).financing_event_id
    b = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id="fact-race")[1].id, [announcement(company)]).candidates[0]
    promotion.attach_candidate_to_event(db, b.id, x, ME)                         # attach first (no facts), then race the fact acceptance
    def act(i):
        c = candidates.persist_financing_event_candidates(db, start_attempt(db, ANNOUNCEMENT, record_id=f"fact-race-{i}")[1].id, [announcement(company)]).candidates[0]
        return outcome(lambda: promotion.attach_candidate_to_event(db, c.id, x, ME, FactSelection(verified_round_amount=True)))
    results = run_all(act, 6)
    assert canonical_financing_counts(db)["financing_event_verified_round_amount"] == 1
    assert sum(1 for r in results if not isinstance(r, type) and r.accepted_verified_round_amount) == 1
