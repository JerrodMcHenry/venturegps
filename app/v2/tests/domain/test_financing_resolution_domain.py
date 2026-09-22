"""Pure tests: financing decision vocabulary, authority, fact selection, derived state. No database."""

import uuid
from datetime import datetime, timezone

import pytest

from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.financing import AmountSemantics, FinancingDateKind, FinancingType, Money, Stage
from app.v2.domain.financing_resolution import (
    FINAL_FINANCING_DECISION_KINDS,
    FINANCING_RULE_AUTHORITY,
    NO_FACTS,
    AcceptedDate,
    AcceptedFinancingType,
    AcceptedStage,
    AcceptedVerifiedRoundAmount,
    CanonicalFinancingEvent,
    FactSelection,
    FinancingCandidateResolutionState,
    FinancingDecisionKind,
    StoredFinancingEvent,
    StoredFinancingResolutionDecision,
    derive_financing_candidate_state,
    may_decide,
)
from app.v2.domain.resolution import human_authority, rule_authority
from app.v2.domain.time import EventTime

NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
EVENT = uuid.UUID("00000000-0000-0000-0000-000000000001")


def decision(kind, *, event=EVENT, reason=None, authority=None):
    return StoredFinancingResolutionDecision(id=1, candidate_id=1, decision_kind=kind, financing_event_id=event,
                                             authority=authority or human_authority("admin:jerrod"), reason_code=reason, created_at=NOW)


# ---------------- vocabulary and derived state

def test_the_decision_vocabulary_is_exactly_four_kinds():
    assert {k.value for k in FinancingDecisionKind} == {"create_event", "attach_to_event", "reject_candidate", "defer_candidate"}
    assert FINAL_FINANCING_DECISION_KINDS == {FinancingDecisionKind.CREATE_EVENT, FinancingDecisionKind.ATTACH_TO_EVENT, FinancingDecisionKind.REJECT_CANDIDATE}


def test_resolution_state_is_derived_and_contradictions_are_refused():
    K = FinancingDecisionKind
    assert derive_financing_candidate_state([]) is FinancingCandidateResolutionState.UNRESOLVED
    assert derive_financing_candidate_state([K.DEFER_CANDIDATE]) is FinancingCandidateResolutionState.DEFERRED
    assert derive_financing_candidate_state([K.DEFER_CANDIDATE, K.CREATE_EVENT]) is FinancingCandidateResolutionState.EVENT_CREATED
    assert derive_financing_candidate_state([K.ATTACH_TO_EVENT]) is FinancingCandidateResolutionState.ATTACHED
    assert derive_financing_candidate_state([K.REJECT_CANDIDATE]) is FinancingCandidateResolutionState.REJECTED
    with pytest.raises(InvariantViolationError):
        derive_financing_candidate_state([K.CREATE_EVENT, K.REJECT_CANDIDATE])


def test_decision_shapes():
    assert decision(FinancingDecisionKind.CREATE_EVENT).is_final and decision(FinancingDecisionKind.ATTACH_TO_EVENT).is_final
    assert decision(FinancingDecisionKind.REJECT_CANDIDATE, event=None, reason="not_a_financing").is_final
    assert not decision(FinancingDecisionKind.DEFER_CANDIDATE, event=None, reason="needs_review").is_final
    for bad in (dict(kind=FinancingDecisionKind.REJECT_CANDIDATE, event=EVENT, reason="x1"),
                dict(kind=FinancingDecisionKind.DEFER_CANDIDATE, event=None, reason=None),
                dict(kind=FinancingDecisionKind.CREATE_EVENT, event=None),
                dict(kind=FinancingDecisionKind.ATTACH_TO_EVENT, reason="x1")):
        with pytest.raises(InvariantViolationError):
            decision(bad.pop("kind"), **bad)


# ---------------- authority: no financing rule is registered

def test_no_financing_rule_is_registered_a_rule_can_decide_nothing():
    assert FINANCING_RULE_AUTHORITY == {}
    rule = rule_authority("exact_identifier_match.v1")   # a valid Company rule id, reused only as a shape example
    assert not any(may_decide(rule, kind) for kind in FinancingDecisionKind)


def test_a_human_may_make_any_financing_decision():
    human = human_authority("admin:jerrod")
    assert all(may_decide(human, kind) for kind in FinancingDecisionKind)


def test_a_rule_decision_can_only_ever_be_shaped_as_an_attach():
    rule = rule_authority("exact_identifier_match.v1")
    with pytest.raises(InvariantViolationError):
        decision(FinancingDecisionKind.CREATE_EVENT, authority=rule)
    with pytest.raises(InvariantViolationError):
        decision(FinancingDecisionKind.REJECT_CANDIDATE, event=None, reason="x1", authority=rule)
    decision(FinancingDecisionKind.ATTACH_TO_EVENT, authority=rule)      # shape-valid even though no rule may actually decide it


def test_ai_authority_cannot_be_constructed_reusing_the_company_resolution_vocabulary():
    from app.v2.domain.resolution import AuthorityKind
    assert {a.value for a in AuthorityKind} == {"rule", "human"}
    with pytest.raises(Exception):
        human_authority("ai:gpt4")


# ---------------- fact selection

def test_the_default_selection_accepts_nothing():
    assert NO_FACTS.is_empty and FactSelection().is_empty
    assert not FactSelection(stage=True).is_empty


def test_duplicate_date_kinds_in_one_selection_are_refused():
    with pytest.raises(InvalidInputError):
        FactSelection(dates=(FinancingDateKind.FILING_DATE, FinancingDateKind.FILING_DATE))


def test_fact_selection_is_a_small_closed_set_not_a_patch_language():
    for extra in ("offering_amount", "amount_sold", "patch", "value", "company_id"):
        with pytest.raises(Exception):
            FactSelection(**{extra: True})


def test_a_selection_can_target_multiple_distinct_dates():
    selection = FactSelection(dates=(FinancingDateKind.FILING_DATE, FinancingDateKind.ANNOUNCEMENT_DATE))
    assert set(selection.dates) == {FinancingDateKind.FILING_DATE, FinancingDateKind.ANNOUNCEMENT_DATE}


# ---------------- accepted facts: unknown is never accepted, values must be stated

def test_unknown_stage_and_type_cannot_be_accepted():
    with pytest.raises(InvalidInputError):
        AcceptedStage(stage=Stage.UNKNOWN, resolution_decision_id=1, candidate_id=1)
    with pytest.raises(InvalidInputError):
        AcceptedFinancingType(financing_type=FinancingType.UNKNOWN, resolution_decision_id=1, candidate_id=1)


def test_a_canonical_event_with_no_accepted_facts_is_legitimate():
    event = CanonicalFinancingEvent(event=StoredFinancingEvent(id=EVENT, company_id=uuid.uuid4(), created_at=NOW))
    assert event.stage is None and event.financing_type is None and event.verified_round_amount is None and event.dates == ()


def test_verified_round_amount_carries_exact_money_and_provenance_to_the_candidate_amount_row():
    accepted = AcceptedVerifiedRoundAmount(money=Money.from_decimal("20000000", "USD"), resolution_decision_id=7, candidate_amount_id=42)
    assert accepted.money.minor_units == 2_000_000_000 and accepted.candidate_amount_id == 42


def test_accepted_dates_keep_kind_and_precision():
    accepted = AcceptedDate(kind=FinancingDateKind.ANNOUNCEMENT_DATE, time=EventTime.of_month(2026, 3), resolution_decision_id=1, candidate_date_id=2)
    assert accepted.kind is FinancingDateKind.ANNOUNCEMENT_DATE and not accepted.time.is_exact


def test_there_is_no_verified_round_amount_from_offering_or_sold_semantics_in_the_domain_surface():
    surface = " ".join(list(FactSelection.model_fields) + list(AcceptedVerifiedRoundAmount.model_fields))
    for word in ("offering_amount", "amount_sold"):
        assert word not in surface
    assert set(AmountSemantics) == {AmountSemantics.OFFERING_AMOUNT, AmountSemantics.AMOUNT_SOLD, AmountSemantics.ANNOUNCED_ROUND_AMOUNT}
