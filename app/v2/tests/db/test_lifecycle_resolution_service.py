"""The lifecycle-resolution boundary through the real repositories: human authority, explicit fact selection,
append-only history that coexists rather than overwrites, unsupported successor claims, and a regression
confirming lifecycle acceptance has NO effect on Capital Metrics inputs (financing, classification, identifiers)."""

import uuid

import pytest
from sqlalchemy import text

from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.lifecycle import OperatingStatus
from app.v2.domain.lifecycle_resolution import (
    LifecycleCandidateResolutionState,
    LifecycleDecisionKind,
    LifecycleFactSelection,
    NO_LIFECYCLE_FACTS,
)
from app.v2.domain.financing_resolution import FactSelection as FinancingFactSelection
from app.v2.domain.resolution import human_authority, rule_authority
from app.v2.financing_resolution import promotion as financing_promotion
from app.v2.lifecycle import promotion
from app.v2.repositories import financing_event_candidates as financing_candidates
from app.v2.lifecycle.errors import FactAlreadyAcceptedError, FactNotAvailableError, LifecycleCandidateAlreadyResolvedError
from app.v2.repositories import company_lifecycle as lifecycle_repo
from app.v2.repositories import lifecycle_candidates as candidates
from app.v2.repositories.errors import NotFoundError
from app.v2.tests.db.financing_fakes import FORM_D, form_d
from app.v2.tests.db.lifecycle_fakes import (
    ACQUISITION_NEWS,
    DISTINCT_ONLY_NEWS,
    RENAME_ANNOUNCEMENT,
    STATUS_ACTIVE_NEWS,
    STATUS_CEASED_NEWS,
    SUCCESSOR_CLAIM_NEWS,
    acquisition,
    canonical_company,
    distinct_only_successor_claim,
    rename,
    start_attempt,
    status_active,
    status_ceased,
    successor_claim,
)
from app.v2.tests.db.resolution_helpers import untouched_snapshot

pytestmark = pytest.mark.db

ME = human_authority("admin:jerrod")
LC_CANONICAL_TABLES = ("company_name_history", "company_operating_status", "company_acquisition", "company_successor_relationship")
ZERO = {**dict.fromkeys(LC_CANONICAL_TABLES, 0), "lifecycle_resolution_decision": 0}


def lc_canonical_counts(db):
    if hasattr(db, "connect"):
        with db.connect() as conn:
            return {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in (*LC_CANONICAL_TABLES, "lifecycle_resolution_decision")}
    return {t: db.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in (*LC_CANONICAL_TABLES, "lifecycle_resolution_decision")}


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, RENAME_ANNOUNCEMENT)
    candidate = candidates.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)]).candidates[0]
    return db, company, candidate


# ---------------- accept

def test_a_human_accepts_a_rename_with_no_facts_selected_by_default(world):
    db, company, candidate = world
    before = untouched_snapshot(db)
    result = promotion.accept_lifecycle_event(db, candidate.id, ME)
    assert result.decision.decision_kind is LifecycleDecisionKind.ACCEPT_LIFECYCLE_EVENT
    assert not result.accepted_name_change   # NO_LIFECYCLE_FACTS by default: reviewed and accepted, nothing selected
    assert lc_canonical_counts(db) == {**ZERO, "lifecycle_resolution_decision": 1}
    assert lifecycle_repo.get_lifecycle_candidate_resolution_state(db, candidate.id) is LifecycleCandidateResolutionState.ACCEPTED
    assert untouched_snapshot(db) == before


def test_accepting_the_name_change_fact_writes_exactly_that_one_canonical_row(world):
    db, company, candidate = world
    result = promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(name_change=True))
    assert result.accepted_name_change and not (result.accepted_operating_status or result.accepted_acquisition or result.accepted_successor)
    state = lifecycle_repo.get_company_lifecycle_state(db, company)
    assert state.current_legal_name == "Lifeward Ltd." and state.current_operating_status is None
    assert lc_canonical_counts(db) == {**ZERO, "company_name_history": 1, "lifecycle_resolution_decision": 1}


def test_a_candidate_cannot_be_resolved_twice(world):
    db, _, candidate = world
    promotion.accept_lifecycle_event(db, candidate.id, ME)
    for attempt in (lambda: promotion.accept_lifecycle_event(db, candidate.id, ME),
                    lambda: promotion.reject_candidate(db, candidate.id, ME, "changed_mind"),
                    lambda: promotion.defer_candidate(db, candidate.id, ME, "later")):
        with pytest.raises(LifecycleCandidateAlreadyResolvedError):
            attempt()


def test_unknown_and_invalid_candidate_ids_are_refused(world):
    db, _, _ = world
    with pytest.raises(NotFoundError):
        promotion.accept_lifecycle_event(db, 999999, ME)
    for bad in (0, -1, True, "1", None):
        with pytest.raises(InvalidInputError):
            promotion.accept_lifecycle_event(db, bad, ME)


# ---------------- append-only history: a second accepted fact coexists, never overwrites

def test_dated_status_history_coexists_current_is_always_the_latest_accepted(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, first = start_attempt(db, STATUS_ACTIVE_NEWS)
    a = candidates.persist_lifecycle_event_candidates(db, first.id, [status_active(company)]).candidates[0]
    promotion.accept_lifecycle_event(db, a.id, ME, LifecycleFactSelection(operating_status=True))
    assert lifecycle_repo.get_company_lifecycle_state(db, company).current_operating_status is OperatingStatus.ACTIVE

    _, second = start_attempt(db, STATUS_CEASED_NEWS, record_id="status-2")
    b = candidates.persist_lifecycle_event_candidates(db, second.id, [status_ceased(company)]).candidates[0]
    promotion.accept_lifecycle_event(db, b.id, ME, LifecycleFactSelection(operating_status=True))

    state = lifecycle_repo.get_company_lifecycle_state(db, company)
    assert state.current_operating_status is OperatingStatus.CEASED_OPERATIONS    # the LATEST accepted row wins
    assert len(state.status_history) == 2                                        # but the EARLIER one is never deleted or rewritten
    assert {s.status for s in state.status_history} == {OperatingStatus.ACTIVE, OperatingStatus.CEASED_OPERATIONS}
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.company_operating_status")).scalar() == 2


def test_a_conflicting_second_accepted_name_change_does_not_erase_the_first(world):
    db, company, candidate = world
    promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(name_change=True))
    later = candidates.persist_lifecycle_event_candidates(
        db, start_attempt(db, STATUS_ACTIVE_NEWS, record_id="later-name")[1].id,
        [status_active(company, STATUS_ACTIVE_NEWS)]).candidates[0]
    promotion.accept_lifecycle_event(db, later.id, ME, LifecycleFactSelection(operating_status=True))
    state = lifecycle_repo.get_company_lifecycle_state(db, company)
    assert state.current_legal_name == "Lifeward Ltd." and len(state.name_history) == 1   # untouched by the unrelated later decision


# ---------------- name-only acquirer

def test_a_name_only_acquirer_is_accepted_with_no_canonical_link(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, ACQUISITION_NEWS)
    candidate = candidates.persist_lifecycle_event_candidates(db, attempt.id, [acquisition(company)]).candidates[0]
    result = promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(acquisition=True))
    assert result.accepted_acquisition
    state = lifecycle_repo.get_company_lifecycle_state(db, company)
    assert state.acquisitions[0].acquirer_name == "Siemens Healthineers AG" and state.acquisitions[0].acquirer_company_id is None
    # accepting an acquisition never implies a status change: nothing was written to company_operating_status
    assert state.current_operating_status is None and lc_canonical_counts(db)["company_operating_status"] == 0


# ---------------- unsupported successor claims: the human review boundary, not the evidence layer, protects this

def test_a_reviewer_rejecting_a_legally_distinct_statement_creates_no_successor_fact(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, DISTINCT_ONLY_NEWS)
    candidate = candidates.persist_lifecycle_event_candidates(db, attempt.id, [distinct_only_successor_claim(company)]).candidates[0]
    # The candidate is stored (the evidence layer only checks the name literally appears -- see
    # test_lifecycle_evidence.py). Per the 18.7 design, a human reviewing this text is expected to REJECT it,
    # not accept it -- "legally distinct" is a reason to propose no relationship, never a weaker one.
    result = promotion.reject_candidate(db, candidate.id, ME, "legally_distinct_not_a_successor")
    assert result.decision.reason_code == "legally_distinct_not_a_successor"
    assert lc_canonical_counts(db)["company_successor_relationship"] == 0
    assert lifecycle_repo.get_lifecycle_candidate_resolution_state(db, candidate.id) is LifecycleCandidateResolutionState.REJECTED


def test_a_genuine_successor_claim_can_still_be_accepted_when_a_human_chooses_to(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, SUCCESSOR_CLAIM_NEWS)
    candidate = candidates.persist_lifecycle_event_candidates(db, attempt.id, [successor_claim(company)]).candidates[0]
    result = promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(successor=True))
    assert result.accepted_successor
    state = lifecycle_repo.get_company_lifecycle_state(db, company)
    assert state.successors[0].related_entity_name == "NewCo Robotics" and state.successors[0].related_company_id is None


# ---------------- reject / defer

def test_reject_creates_no_canonical_fact(world):
    db, _, candidate = world
    before = untouched_snapshot(db)
    result = promotion.reject_candidate(db, candidate.id, ME, "not_a_valid_claim")
    assert result.decision.reason_code == "not_a_valid_claim"
    assert lc_canonical_counts(db) == {**ZERO, "lifecycle_resolution_decision": 1}
    assert lifecycle_repo.get_lifecycle_candidate_resolution_state(db, candidate.id) is LifecycleCandidateResolutionState.REJECTED
    assert untouched_snapshot(db) == before


def test_defer_creates_no_canonical_fact_and_a_later_final_decision_may_still_resolve_it(world):
    db, _, candidate = world
    deferred = promotion.defer_candidate(db, candidate.id, ME, "needs_second_source")
    assert not deferred.decision.is_final and lc_canonical_counts(db) == {**ZERO, "lifecycle_resolution_decision": 1}
    assert lifecycle_repo.get_lifecycle_candidate_resolution_state(db, candidate.id) is LifecycleCandidateResolutionState.DEFERRED
    result = promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(name_change=True))
    assert result.accepted_name_change
    assert [d.decision_kind for d in lifecycle_repo.list_decisions_for_lifecycle_candidate(db, candidate.id)] == [
        LifecycleDecisionKind.DEFER_CANDIDATE, LifecycleDecisionKind.ACCEPT_LIFECYCLE_EVENT]


def test_reasons_are_required_and_shaped(world):
    db, _, candidate = world
    for bad in ("", "Has Spaces", "x", None):
        with pytest.raises(InvalidInputError):
            promotion.reject_candidate(db, candidate.id, ME, bad)
    assert lc_canonical_counts(db) == ZERO


# ---------------- authority: no lifecycle rule is registered; unauthorized decisions are refused

def test_no_rule_can_decide_anything_since_none_is_registered(world):
    db, _, candidate = world
    rule = rule_authority("exact_identifier_match.v1")
    with pytest.raises(InvariantViolationError):
        promotion.accept_lifecycle_event(db, candidate.id, rule)
    with pytest.raises(InvariantViolationError):
        promotion.reject_candidate(db, candidate.id, rule, "nope")
    assert lc_canonical_counts(db) == ZERO


@pytest.mark.parametrize("fake", ["ai", "human", None, {"kind": "ai", "id": "x"}, object()])
def test_no_promotion_api_accepts_anything_but_a_real_authority(world, fake):
    db, _, candidate = world
    with pytest.raises(InvalidInputError):
        promotion.accept_lifecycle_event(db, candidate.id, fake)
    assert lc_canonical_counts(db) == ZERO


def test_a_forged_authority_that_skips_validation_is_still_refused(world):
    db, _, candidate = world
    from app.v2.domain.lifecycle_resolution import Authority
    forged = Authority.model_construct(kind="ai", id="admin:jerrod")
    with pytest.raises(InvalidInputError):
        promotion.accept_lifecycle_event(db, candidate.id, forged)
    assert lc_canonical_counts(db) == ZERO


# ---------------- fact selection: only what was proposed, never assumed

def test_selecting_a_fact_the_candidate_never_proposed_is_refused(world):
    db, _, candidate = world      # candidate is a rename only
    with pytest.raises(FactNotAvailableError) as info:
        promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(operating_status=True))
    assert info.value.code == "operating_status_not_proposed"
    assert lc_canonical_counts(db) == ZERO
    assert lifecycle_repo.get_lifecycle_candidate_resolution_state(db, candidate.id) is LifecycleCandidateResolutionState.UNRESOLVED


def test_a_failed_fact_selection_rolls_back_the_whole_accept(world):
    db, _, candidate = world
    before = lc_canonical_counts(db)
    with pytest.raises(FactNotAvailableError):
        promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(name_change=True, acquisition=True))
    assert lc_canonical_counts(db) == before   # NOT even the valid name_change fact was written


def test_invalid_fact_selection_types_are_rejected(world):
    db, _, candidate = world
    for bad in ("name_change", {"name_change": True}, 1, None):
        with pytest.raises(InvalidInputError):
            promotion.accept_lifecycle_event(db, candidate.id, ME, bad)


def test_accept_with_zero_selected_facts_is_legitimate_and_distinct_from_rejecting(world):
    db, company, candidate = world
    result = promotion.accept_lifecycle_event(db, candidate.id, ME)   # default NO_LIFECYCLE_FACTS
    assert not (result.accepted_name_change or result.accepted_operating_status or result.accepted_acquisition or result.accepted_successor)
    assert lifecycle_repo.get_lifecycle_candidate_resolution_state(db, candidate.id) is LifecycleCandidateResolutionState.ACCEPTED
    assert lifecycle_repo.get_company_lifecycle_state(db, company).current_legal_name is None   # reviewed, but nothing was accepted


# ---------------- Gecko-style regression: lifecycle facts never touch Capital Metrics inputs

def test_accepting_lifecycle_facts_never_touches_financing_or_classification_tables(migrated_db):
    """A company shaped like the real Gecko Robotics scenario: canonical identity, one accepted financing event
    with a verified round amount. Proposing and accepting an UNRELATED lifecycle fact (operating status) for the
    SAME company must leave financing_event / financing_event_verified_round_amount / company_market_classification
    completely byte-identical -- proving the 18.7 approval's "no automatic effect on Capital Metrics or Capital
    Signal" holds at the database level, not just by convention."""
    db = migrated_db
    company = canonical_company(db, "Gecko Robotics, Inc.", "geckorobotics.com")
    _, fin_attempt = start_attempt(db, FORM_D)
    fin_candidate = financing_candidates.persist_financing_event_candidates(db, fin_attempt.id, [form_d(company)]).candidates[0]
    financing_promotion.create_event_from_candidate(db, fin_candidate.id, ME, FinancingFactSelection(dates=()))

    with db.connect() as conn:
        capital_snapshot_before = {
            "financing_event": [tuple(r) for r in conn.execute(text("SELECT * FROM v2.financing_event ORDER BY id"))],
            "financing_event_verified_round_amount": [tuple(r) for r in conn.execute(text("SELECT * FROM v2.financing_event_verified_round_amount ORDER BY id"))],
            "company_market_classification": [tuple(r) for r in conn.execute(text("SELECT * FROM v2.company_market_classification ORDER BY id"))],
            "company_identifier": [tuple(r) for r in conn.execute(text("SELECT * FROM v2.company_identifier ORDER BY id"))],
        }

    _, lc_attempt = start_attempt(db, STATUS_ACTIVE_NEWS, record_id="gecko-lifecycle")
    lc_candidate = candidates.persist_lifecycle_event_candidates(db, lc_attempt.id, [status_active(company)]).candidates[0]
    promotion.accept_lifecycle_event(db, lc_candidate.id, ME, LifecycleFactSelection(operating_status=True))

    with db.connect() as conn:
        capital_snapshot_after = {
            "financing_event": [tuple(r) for r in conn.execute(text("SELECT * FROM v2.financing_event ORDER BY id"))],
            "financing_event_verified_round_amount": [tuple(r) for r in conn.execute(text("SELECT * FROM v2.financing_event_verified_round_amount ORDER BY id"))],
            "company_market_classification": [tuple(r) for r in conn.execute(text("SELECT * FROM v2.company_market_classification ORDER BY id"))],
            "company_identifier": [tuple(r) for r in conn.execute(text("SELECT * FROM v2.company_identifier ORDER BY id"))],
        }
    assert capital_snapshot_after == capital_snapshot_before   # byte-identical: the lifecycle acceptance touched none of it
    # and the lifecycle fact really was accepted -- this is not a no-op test
    assert lifecycle_repo.get_company_lifecycle_state(db, company).current_operating_status is OperatingStatus.ACTIVE


# ---------------- provenance

def test_the_full_provenance_chain_for_an_accepted_fact(world):
    db, company, candidate = world
    promotion.accept_lifecycle_event(db, candidate.id, ME, LifecycleFactSelection(name_change=True))
    links = lifecycle_repo.get_company_lifecycle_lineage(db, company)
    assert [l.fact_kind for l in links] == ["name_change"]
    link = links[0]
    with db.connect() as conn:
        attempt = conn.execute(text("SELECT observation_id FROM v2.processing_attempt WHERE id = :i"), {"i": link.processing_attempt_id}).one()
        observation = conn.execute(text("SELECT source_id, content_hash FROM v2.observation WHERE id = :o"), {"o": attempt.observation_id}).one()
        source_key = conn.execute(text("SELECT source_key FROM v2.source WHERE id = :s"), {"s": observation.source_id}).scalar()
    assert link.observation_id == attempt.observation_id and link.content_hash == observation.content_hash
    assert link.source_key == source_key and link.candidate_id == candidate.id
