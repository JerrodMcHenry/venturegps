"""Pure tests: lifecycle decision vocabulary, authority, fact selection, derived state. No database."""

import uuid
from datetime import datetime, timezone

import pytest

from app.v2.domain.errors import InvalidInputError
from app.v2.domain.lifecycle import OperatingStatus, SuccessorRelationshipKind
from app.v2.domain.lifecycle_resolution import (
    FINAL_LIFECYCLE_DECISION_KINDS,
    LIFECYCLE_RULE_AUTHORITY,
    NO_LIFECYCLE_FACTS,
    AcceptedAcquisition,
    AcceptedNameChange,
    AcceptedOperatingStatus,
    AcceptedSuccessorRelationship,
    CompanyLifecycleState,
    LifecycleCandidateResolutionState,
    LifecycleDecisionKind,
    LifecycleFactSelection,
    StoredLifecycleResolutionDecision,
    derive_lifecycle_candidate_state,
    may_decide,
)
from app.v2.domain.resolution import human_authority, rule_authority

NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
COMPANY = uuid.UUID("00000000-0000-0000-0000-000000000001")


def decision(kind, *, reason=None, authority=None):
    return StoredLifecycleResolutionDecision(id=1, candidate_id=1, decision_kind=kind,
                                             authority=authority or human_authority("admin:jerrod"), reason_code=reason, created_at=NOW)


# ---------------- vocabulary and derived state

def test_the_decision_vocabulary_is_exactly_three_kinds_and_no_create_attach_split():
    assert {k.value for k in LifecycleDecisionKind} == {"accept_lifecycle_event", "reject_candidate", "defer_candidate"}
    assert FINAL_LIFECYCLE_DECISION_KINDS == {LifecycleDecisionKind.ACCEPT_LIFECYCLE_EVENT, LifecycleDecisionKind.REJECT_CANDIDATE}


def test_resolution_state_is_derived_and_contradictions_are_refused():
    K = LifecycleDecisionKind
    assert derive_lifecycle_candidate_state([]) is LifecycleCandidateResolutionState.UNRESOLVED
    assert derive_lifecycle_candidate_state([K.DEFER_CANDIDATE]) is LifecycleCandidateResolutionState.DEFERRED
    assert derive_lifecycle_candidate_state([K.DEFER_CANDIDATE, K.ACCEPT_LIFECYCLE_EVENT]) is LifecycleCandidateResolutionState.ACCEPTED
    assert derive_lifecycle_candidate_state([K.REJECT_CANDIDATE]) is LifecycleCandidateResolutionState.REJECTED
    with pytest.raises(InvalidInputError):
        derive_lifecycle_candidate_state([K.ACCEPT_LIFECYCLE_EVENT, K.REJECT_CANDIDATE])


def test_decision_shapes_reject_and_defer_need_a_reason_accept_does_not():
    assert decision(LifecycleDecisionKind.ACCEPT_LIFECYCLE_EVENT).is_final
    assert decision(LifecycleDecisionKind.REJECT_CANDIDATE, reason="not_a_valid_claim").is_final
    assert not decision(LifecycleDecisionKind.DEFER_CANDIDATE, reason="needs_second_source").is_final
    with pytest.raises(InvalidInputError):
        decision(LifecycleDecisionKind.REJECT_CANDIDATE, reason=None)
    with pytest.raises(InvalidInputError):
        decision(LifecycleDecisionKind.DEFER_CANDIDATE, reason=None)


# ---------------- authority: no lifecycle rule is registered -- human only, structurally

def test_no_lifecycle_rule_is_registered_a_rule_can_decide_nothing():
    assert LIFECYCLE_RULE_AUTHORITY == {}
    rule = rule_authority("exact_identifier_match.v1")   # a valid Company rule id, reused only as a shape example
    assert not any(may_decide(rule, kind) for kind in LifecycleDecisionKind)


def test_a_human_may_make_any_lifecycle_decision():
    human = human_authority("admin:jerrod")
    assert all(may_decide(human, kind) for kind in LifecycleDecisionKind)


def test_a_rule_authority_can_never_be_shaped_as_a_valid_lifecycle_decision():
    rule = rule_authority("exact_identifier_match.v1")
    for kind in LifecycleDecisionKind:
        with pytest.raises(InvalidInputError):
            decision(kind, reason="x1" if kind is not LifecycleDecisionKind.ACCEPT_LIFECYCLE_EVENT else None, authority=rule)


def test_ai_authority_cannot_be_constructed():
    with pytest.raises(Exception):
        human_authority("ai:gpt4")


# ---------------- fact selection: small, closed, nothing implicit

def test_the_default_selection_accepts_nothing():
    assert NO_LIFECYCLE_FACTS.is_empty and LifecycleFactSelection().is_empty
    assert not LifecycleFactSelection(name_change=True).is_empty


def test_accepting_one_fact_kind_never_implies_another():
    facts = LifecycleFactSelection(acquisition=True)
    assert facts.acquisition and not (facts.name_change or facts.operating_status or facts.successor)


def test_fact_selection_is_a_small_closed_set_not_a_patch_language():
    for extra in ("all", "patch", "value", "company_id", "status"):
        with pytest.raises(Exception):
            LifecycleFactSelection(**{extra: True})


# ---------------- accepted facts and derived "current"

def test_current_legal_name_and_status_are_derived_from_the_most_recent_accepted_fact():
    state = CompanyLifecycleState(
        company_id=COMPANY,
        name_history=(AcceptedNameChange(id=1, company_id=COMPANY, new_name="Lifeward Ltd.", effective=None, resolution_decision_id=1, candidate_id=1, created_at=NOW),),
        status_history=(
            AcceptedOperatingStatus(id=1, company_id=COMPANY, status=OperatingStatus.ACTIVE, as_of=None, resolution_decision_id=1, candidate_id=1, created_at=NOW),
            AcceptedOperatingStatus(id=2, company_id=COMPANY, status=OperatingStatus.CEASED_OPERATIONS, as_of=None, resolution_decision_id=2, candidate_id=2, created_at=NOW),
        ),
    )
    assert state.current_legal_name == "Lifeward Ltd."
    assert state.current_operating_status is OperatingStatus.CEASED_OPERATIONS   # the LATEST accepted row wins, never merged/averaged


def test_a_company_with_no_accepted_facts_has_no_derived_current_state():
    state = CompanyLifecycleState(company_id=COMPANY)
    assert state.current_legal_name is None and state.current_operating_status is None
    assert state.name_history == () and state.acquisitions == () and state.successors == ()


def test_accepted_acquisition_and_successor_carry_optional_canonical_links():
    acq = AcceptedAcquisition(id=1, company_id=COMPANY, acquirer_name="Siemens Healthineers AG", acquirer_company_id=None,
                              transaction_date=None, resolution_decision_id=1, candidate_id=1, created_at=NOW)
    assert acq.acquirer_company_id is None
    succ = AcceptedSuccessorRelationship(id=1, company_id=COMPANY, related_entity_name="NewCo Robotics", related_company_id=None,
                                         relationship_kind=SuccessorRelationshipKind.POSSIBLE_SUCCESSOR, resolution_decision_id=1, candidate_id=1, created_at=NOW)
    assert succ.related_company_id is None
