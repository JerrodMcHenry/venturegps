"""Pure tests: lifecycle candidate proposal vocabulary and shape. No database."""

import uuid
from datetime import datetime, timezone

import pytest

from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.lifecycle import (
    MAX_LIFECYCLE_CANDIDATES_PER_ATTEMPT,
    LifecycleEventCandidateProposal,
    OperatingStatus,
    ProposedAcquisition,
    ProposedNameChange,
    ProposedOperatingStatus,
    ProposedSuccessorRelationship,
    StoredLifecycleEventCandidate,
    SuccessorRelationshipKind,
)
from app.v2.domain.time import EventTime

NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
COMPANY = uuid.UUID("00000000-0000-0000-0000-000000000001")
LOC = EvidenceLocator(byte_start=0, byte_end=10, evidence_hash="a" * 64)


def test_an_empty_proposal_is_refused():
    with pytest.raises(InvalidInputError) as info:
        LifecycleEventCandidateProposal(company_id=COMPANY, event_evidence=LOC)
    assert info.value.code == "empty_lifecycle_proposal"


def test_a_proposal_may_carry_more_than_one_fact_kind_independently_evidenced():
    proposal = LifecycleEventCandidateProposal(
        company_id=COMPANY, event_evidence=LOC,
        name_change=ProposedNameChange(new_name="Lifeward Ltd.", evidence=LOC),
        operating_status=ProposedOperatingStatus(status=OperatingStatus.ACTIVE, evidence=LOC),
    )
    assert proposal.name_change is not None and proposal.operating_status is not None
    assert proposal.acquisition is None and proposal.successor is None


def test_operating_status_has_exactly_four_values_and_unknown_is_legitimate():
    assert {s.value for s in OperatingStatus} == {"active", "acquired", "ceased_operations", "unknown"}
    # Unlike Stage/FinancingType, UNKNOWN here is a real, explicit, evidenced claim -- constructing it is legal.
    ProposedOperatingStatus(status=OperatingStatus.UNKNOWN, evidence=LOC)


def test_successor_relationship_has_no_third_explicitly_distinct_kind():
    # Structural guard for the 18.7 approval: "an explicit statement that two entities are legally distinct is
    # a reason to propose NO successor fact, never a weaker relationship" -- there is deliberately no vocabulary
    # for it to be encoded into.
    assert {k.value for k in SuccessorRelationshipKind} == {"possible_successor", "confirmed_successor"}
    with pytest.raises(Exception):
        SuccessorRelationshipKind("explicitly_distinct")


def test_acquirer_and_related_company_id_are_optional_name_only_is_legitimate():
    acquisition = ProposedAcquisition(acquirer_name="Siemens Healthineers AG", evidence=LOC)
    assert acquisition.acquirer_company_id is None
    successor = ProposedSuccessorRelationship(related_entity_name="NewCo Robotics", relationship_kind=SuccessorRelationshipKind.POSSIBLE_SUCCESSOR, evidence=LOC)
    assert successor.related_company_id is None


def test_acquisition_never_implies_a_status_field_in_the_domain_surface():
    surface = " ".join(ProposedAcquisition.model_fields)
    assert "status" not in surface and "operating" not in surface


def test_blank_or_malformed_names_are_refused():
    for bad in ("", "   ", "x" * 2000):
        with pytest.raises(Exception):
            ProposedNameChange(new_name=bad, evidence=LOC)
        with pytest.raises(Exception):
            ProposedAcquisition(acquirer_name=bad, evidence=LOC)
        with pytest.raises(Exception):
            ProposedSuccessorRelationship(related_entity_name=bad, relationship_kind=SuccessorRelationshipKind.POSSIBLE_SUCCESSOR, evidence=LOC)


def test_effective_and_as_of_and_transaction_date_are_all_optional_event_times():
    proposal = LifecycleEventCandidateProposal(
        company_id=COMPANY, event_evidence=LOC,
        name_change=ProposedNameChange(new_name="Lifeward Ltd.", evidence=LOC, effective=EventTime.of_day(2024, 9, 12)),
    )
    assert proposal.name_change.effective == EventTime.of_day(2024, 9, 12)
    bare = ProposedNameChange(new_name="Lifeward Ltd.", evidence=LOC)
    assert bare.effective is None


def test_the_company_is_identified_only_by_id_never_a_name_domain_or_url():
    surface = " ".join(LifecycleEventCandidateProposal.model_fields)
    for word in ("company_name", "domain", "url"):
        assert word not in surface


def test_stored_candidate_is_marked_untrusted():
    stored = StoredLifecycleEventCandidate(
        id=1, processing_attempt_id=1, candidate_ordinal=1,
        proposal=LifecycleEventCandidateProposal(company_id=COMPANY, event_evidence=LOC, operating_status=ProposedOperatingStatus(status=OperatingStatus.ACTIVE, evidence=LOC)),
        created_at=NOW,
    )
    assert stored.TRUST_LEVEL == "untrusted_proposal"


def test_the_per_attempt_cap_is_a_real_positive_number():
    assert isinstance(MAX_LIFECYCLE_CANDIDATES_PER_ATTEMPT, int) and MAX_LIFECYCLE_CANDIDATES_PER_ATTEMPT > 0
