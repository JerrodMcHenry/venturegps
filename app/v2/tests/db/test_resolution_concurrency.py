"""Concurrent resolution: the database (row lock + unique indexes) is the final authority."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.v2.domain.resolution import CandidateResolutionState, human_authority
from app.v2.repositories import companies
from app.v2.repositories.errors import ConflictError
from app.v2.resolution import promotion, rules
from app.v2.resolution.errors import CandidateAlreadyResolvedError, IdentifierConflictError
from app.v2.tests.db.resolution_helpers import HUMAN, canonical_counts, make_candidate

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


def test_concurrent_creates_from_one_candidate_yield_exactly_one_company_and_decision(migrated_db):
    db = migrated_db
    candidate = make_candidate(db, "Acme Robotics", domain="acmerobotics.com", url="https://acmerobotics.com")
    results = run_all(lambda _: outcome(lambda: promotion.create_company_from_candidate(db, candidate.id, ME)))
    assert canonical_counts(db) == {"company": 1, "resolution_decision": 1, "company_name": 1, "company_identifier": 2}
    assert sum(1 for r in results if not isinstance(r, type)) == 1
    assert all(r is CandidateAlreadyResolvedError for r in results if isinstance(r, type))


def test_concurrent_mixed_final_decisions_on_one_candidate_admit_one_winner(migrated_db):
    db = migrated_db
    candidate = make_candidate(db, "Acme Robotics", domain="acmerobotics.com")
    def act(i):
        return outcome(lambda: promotion.create_company_from_candidate(db, candidate.id, ME) if i % 3 == 0
                       else promotion.reject_candidate(db, candidate.id, ME, "not_a_company") if i % 3 == 1
                       else promotion.defer_candidate(db, candidate.id, ME, "later"))
    run_all(act, 18)
    history = companies.list_decisions_for_candidate(db, candidate.id)
    finals = [d for d in history if d.is_final]
    assert len(finals) == 1
    assert all(history[i].id < history[i + 1].id for i in range(len(history) - 1))
    assert all(not d.is_final for d in history if d is not finals[0])
    assert companies.get_candidate_resolution_state(db, candidate.id) is not CandidateResolutionState.UNRESOLVED
    assert canonical_counts(db)["company"] == (1 if finals[0].decision_kind.value == "create_company" else 0)


def test_no_decision_can_follow_a_final_decision_under_concurrency(migrated_db):
    db = migrated_db
    candidate = make_candidate(db, "Acme Robotics")
    def act(i):
        return outcome(lambda: promotion.reject_candidate(db, candidate.id, ME, "not_a_company") if i == 0
                       else promotion.defer_candidate(db, candidate.id, ME, "later"))
    run_all(act, 16)
    history = companies.list_decisions_for_candidate(db, candidate.id)
    kinds = [d.decision_kind.value for d in history]
    if "reject_candidate" in kinds:
        assert kinds[-1] == "reject_candidate" and kinds.count("reject_candidate") == 1     # every deferral committed BEFORE the final one


def test_concurrent_creates_with_the_same_identifier_admit_exactly_one_owner(migrated_db):
    db = migrated_db
    cands = [make_candidate(db, f"Acme {i}", domain="shared.example") for i in range(8)]
    results = run_all(lambda i: outcome(lambda: promotion.create_company_from_candidate(db, cands[i].id, ME)), 8)
    assert canonical_counts(db) == {"company": 1, "resolution_decision": 1, "company_name": 1, "company_identifier": 1}
    assert sum(1 for r in results if not isinstance(r, type)) == 1
    assert all(r is IdentifierConflictError for r in results if isinstance(r, type))
    unresolved = [c for c in cands if companies.get_candidate_resolution_state(db, c.id) is CandidateResolutionState.UNRESOLVED]
    assert len(unresolved) == 7                                                             # the losers rolled back completely


def test_concurrent_rule_attaches_never_violate_uniqueness_or_double_resolve(migrated_db):
    db = migrated_db
    company_id = promotion.create_company_from_candidate(db, make_candidate(db, "One Co", domain="one.example").id, ME).company_id
    candidate = make_candidate(db, "One Company", domain="one.example")
    results = run_all(lambda _: rules.resolve_by_exact_identifier(db, candidate.id))
    attached = [r for r in results if r.kind.value == "attached"]
    assert len(attached) == 1 and all(r.kind.value in ("attached", "already_resolved") for r in results)
    assert canonical_counts(db) == {"company": 1, "resolution_decision": 2, "company_name": 1, "company_identifier": 1}
    assert attached[0].company_id == company_id


def test_a_rule_racing_a_human_leaves_one_final_decision(migrated_db):
    db = migrated_db
    company_id = promotion.create_company_from_candidate(db, make_candidate(db, "One Co", domain="one.example").id, ME).company_id
    candidate = make_candidate(db, "One Company", domain="one.example")
    def act(i):
        return outcome(lambda: rules.resolve_by_exact_identifier(db, candidate.id) if i % 2 == 0
                       else promotion.attach_candidate_to_company(db, candidate.id, company_id, ME))
    run_all(act, 10)
    assert sum(1 for d in companies.list_decisions_for_candidate(db, candidate.id) if d.is_final) == 1
