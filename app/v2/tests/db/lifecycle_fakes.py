"""Deterministic lifecycle-candidate fixtures (Increment 18.7). No AI, no network, no extractor: proposals are
built by hand from exact payload bytes, the same human-guided discipline manual_fact.py documents -- there is
no automated lifecycle extractor by design. canonical_company/start_attempt are reused unchanged from
financing_fakes.py: a canonical Company is made the same way regardless of which candidate kind follows it."""

from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.lifecycle import (
    LifecycleEventCandidateProposal,
    OperatingStatus,
    ProposedAcquisition,
    ProposedNameChange,
    ProposedOperatingStatus,
    ProposedSuccessorRelationship,
    SuccessorRelationshipKind,
)
from app.v2.observations.hashing import compute_content_hash

# Re-exported for convenience: the same canonical-company/attempt machinery used by every other candidate kind.
from app.v2.tests.db.financing_fakes import canonical_company, start_attempt  # noqa: F401

RENAME_ANNOUNCEMENT = (
    b"ReWalk Robotics Ltd. announced today that its Board of Directors approved changing the company's "
    b"registered name to Lifeward Ltd., effective September 12, 2024."
)
STATUS_ACTIVE_NEWS = b"As of 2026-03-01, Acme Robotics remains an active, independently operating company."
STATUS_CEASED_NEWS = b"Acme Robotics ceased operations in its original hardware business in 2016."
ACQUISITION_NEWS = (
    b"Siemens Healthineers AG completed its acquisition of Acme Robotics, Inc. on 2019-10-29, a transaction "
    b"valued at roughly $1.1 billion."
)
SUCCESSOR_CLAIM_NEWS = (
    b"Some industry observers have called NewCo Robotics a possible successor to Acme Robotics, citing "
    b"overlapping leadership and technology."
)
DISTINCT_ONLY_NEWS = (
    b"NewCo Robotics has stated publicly that it is a legally distinct company from Acme Robotics and has no "
    b"corporate or ownership relationship to it."
)


def locate(payload: bytes, needle: bytes, *, before: int = 0, after: int = 0) -> EvidenceLocator:
    index = payload.index(needle)
    start, end = max(0, index - before), min(len(payload), index + len(needle) + after)
    return EvidenceLocator(byte_start=start, byte_end=end, evidence_hash=compute_content_hash(payload[start:end]))


def make_lifecycle(payload: bytes, company_id, *, event: bytes, name_change=None, operating_status=None,
                   acquisition=None, successor=None, pad: int = 4) -> LifecycleEventCandidateProposal:
    """
    name_change      = (new_name, needle, effective_EventTime_or_None)
    operating_status = (OperatingStatus, needle, as_of_EventTime_or_None)
    acquisition      = (acquirer_name, needle, acquirer_company_id_or_None, transaction_date_or_None)
    successor        = (related_entity_name, SuccessorRelationshipKind, needle, related_company_id_or_None)
    """
    return LifecycleEventCandidateProposal(
        company_id=company_id, event_evidence=locate(payload, event, before=pad, after=pad),
        name_change=None if name_change is None else ProposedNameChange(
            new_name=name_change[0], evidence=locate(payload, name_change[1], before=pad, after=pad),
            effective=name_change[2] if len(name_change) > 2 else None),
        operating_status=None if operating_status is None else ProposedOperatingStatus(
            status=operating_status[0], evidence=locate(payload, operating_status[1], before=pad, after=pad),
            as_of=operating_status[2] if len(operating_status) > 2 else None),
        acquisition=None if acquisition is None else ProposedAcquisition(
            acquirer_name=acquisition[0], evidence=locate(payload, acquisition[1], before=pad, after=pad),
            acquirer_company_id=acquisition[2] if len(acquisition) > 2 else None,
            transaction_date=acquisition[3] if len(acquisition) > 3 else None),
        successor=None if successor is None else ProposedSuccessorRelationship(
            related_entity_name=successor[0], relationship_kind=successor[1],
            evidence=locate(payload, successor[2], before=pad, after=pad),
            related_company_id=successor[3] if len(successor) > 3 else None),
    )


def rename(company_id, payload=RENAME_ANNOUNCEMENT):
    return make_lifecycle(payload, company_id, event=b"Board of Directors approved",
                          name_change=("Lifeward Ltd.", b"Lifeward Ltd."))


def status_active(company_id, payload=STATUS_ACTIVE_NEWS):
    return make_lifecycle(payload, company_id, event=b"Acme Robotics remains",
                          operating_status=(OperatingStatus.ACTIVE, b"active, independently operating"))


def status_ceased(company_id, payload=STATUS_CEASED_NEWS):
    return make_lifecycle(payload, company_id, event=b"Acme Robotics ceased",
                          operating_status=(OperatingStatus.CEASED_OPERATIONS, b"ceased operations"))


def acquisition(company_id, payload=ACQUISITION_NEWS, *, acquirer_company_id=None):
    return make_lifecycle(payload, company_id, event=b"completed its acquisition",
                          acquisition=("Siemens Healthineers AG", b"Siemens Healthineers AG", acquirer_company_id))


def successor_claim(company_id, payload=SUCCESSOR_CLAIM_NEWS, *, related_company_id=None):
    return make_lifecycle(payload, company_id, event=b"possible successor",
                          successor=("NewCo Robotics", SuccessorRelationshipKind.POSSIBLE_SUCCESSOR, b"NewCo Robotics", related_company_id))


def distinct_only_successor_claim(company_id, payload=DISTINCT_ONLY_NEWS):
    """The evidence-verification layer only checks that the related entity's name literally appears in its
    cited span (see lifecycle_evidence.py's own docstring: a consistency check, never classification) -- it
    cannot and does not detect that this text is a "legally distinct" statement, not proof of succession. The
    18.7 design's safeguard against inventing a relationship is a HUMAN judgment at review time, not something
    this layer enforces; this fixture exists so the test suite can demonstrate that a human reviewing it is
    expected to REJECT it, and that nothing here does so automatically."""
    return make_lifecycle(payload, company_id, event=b"legally distinct",
                          successor=("NewCo Robotics", SuccessorRelationshipKind.POSSIBLE_SUCCESSOR, b"NewCo Robotics"))
