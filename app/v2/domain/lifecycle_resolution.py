"""
Lifecycle resolution: the explicit authority boundary between an UNTRUSTED LifecycleEventCandidate and
accepted canonical lifecycle facts about an already-existing Company (Increment 18.7).

    LifecycleEventCandidate [untrusted] -> LifecycleResolutionDecision [human] -> accepted fact(s) [trusted]

AI MAY PROPOSE. AI MAY NOT DECIDE. AI MAY NOT ACCEPT A LIFECYCLE FACT. AI MAY NOT MERGE COMPANIES. Structural,
not a promise: the authority vocabulary is exactly RULE and HUMAN (the domain re-uses the Company-resolution
Authority value object, which refuses AI-named actors), and LIFECYCLE_RULE_AUTHORITY is deliberately empty --
no rule is registered, so a rule can decide nothing. Mirrors financing_resolution.py's own stance exactly:
identity/lifecycle judgment calls are exactly the kind of case Increment 18.2.1 already decided rules aren't
safe for.

There is no create/attach split here (unlike financing): a lifecycle candidate never brings a new entity into
existence -- it always annotates an ALREADY-canonical company directly. Decision kinds are therefore simpler:
  accept_lifecycle_event   accept some (a LifecycleFactSelection) or all of the candidate's proposed facts
  reject_candidate         the candidate is not a valid lifecycle claim (reason code required)
  defer_candidate          unresolved / insufficient evidence (reason code required; NOT final)

A LifecycleFactSelection names exactly which of the resolved candidate's proposed facts become canonical --
nothing is accepted implicitly. Accepting an acquisition fact does NOT also accept/imply an operating_status
fact, even if both were proposed on the same candidate: each is its own explicit choice.

CORRECTIONS: every accepted fact is append-only (the database never permits UPDATE/DELETE on any of the four
canonical fact tables). A correction is a NEW accepted fact, from a NEW candidate/decision, with a later
created_at -- "current" is always the most-recently-accepted fact, derived at read time, never a rewrite of an
earlier one. The old fact is never deleted; it remains inspectable history.
"""

from collections.abc import Sequence
from enum import Enum
from types import MappingProxyType
from uuid import UUID

from pydantic import Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.lifecycle import OperatingStatus, SuccessorRelationshipKind
from app.v2.domain.processing_attempt import ReasonCode
from app.v2.domain.resolution import Authority, AuthorityKind
from app.v2.domain.time import EventTime, UtcDatetime


class LifecycleDecisionKind(str, Enum):
    ACCEPT_LIFECYCLE_EVENT = "accept_lifecycle_event"
    REJECT_CANDIDATE = "reject_candidate"
    DEFER_CANDIDATE = "defer_candidate"


FINAL_LIFECYCLE_DECISION_KINDS = frozenset({
    LifecycleDecisionKind.ACCEPT_LIFECYCLE_EVENT, LifecycleDecisionKind.REJECT_CANDIDATE,
})

# Deliberately empty, like FINANCING_RULE_AUTHORITY: no deterministic rule is safe for lifecycle identity
# claims. Adding one is a future, separately reviewed change to this registry AND a migration.
LIFECYCLE_RULE_AUTHORITY: "MappingProxyType[str, frozenset[LifecycleDecisionKind]]" = MappingProxyType({})


def may_decide(authority: Authority, kind: LifecycleDecisionKind) -> bool:
    if authority.kind is AuthorityKind.HUMAN:
        return True
    return kind in LIFECYCLE_RULE_AUTHORITY.get(authority.id, frozenset())


class LifecycleFactSelection(DomainModel):
    """Which of the resolved candidate's proposed facts the resolver explicitly accepts. Small and closed,
    exactly like financing's FactSelection: not a patch language."""

    name_change: bool = False
    operating_status: bool = False
    acquisition: bool = False
    successor: bool = False

    @property
    def is_empty(self) -> bool:
        return not (self.name_change or self.operating_status or self.acquisition or self.successor)


NO_LIFECYCLE_FACTS = LifecycleFactSelection()


class StoredLifecycleResolutionDecision(DomainModel):
    id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    decision_kind: LifecycleDecisionKind
    authority: Authority
    reason_code: ReasonCode | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _shape_matches_the_kind(self) -> "StoredLifecycleResolutionDecision":
        needs_reason = self.decision_kind in (LifecycleDecisionKind.REJECT_CANDIDATE, LifecycleDecisionKind.DEFER_CANDIDATE)
        if needs_reason and self.reason_code is None:
            raise InvalidInputError("invalid_decision_state", "reject/defer requires a reason code")
        if self.authority.kind is AuthorityKind.RULE:
            raise InvalidInputError("authority_exceeded", "no lifecycle rule is registered; only a human may decide")
        return self

    @property
    def is_final(self) -> bool:
        return self.decision_kind in FINAL_LIFECYCLE_DECISION_KINDS


class LifecycleCandidateResolutionState(str, Enum):
    UNRESOLVED = "unresolved"
    DEFERRED = "deferred"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


def derive_lifecycle_candidate_state(decision_kinds: Sequence[LifecycleDecisionKind]) -> LifecycleCandidateResolutionState:
    """Resolution state is DERIVED from decision history (oldest first); candidates never store it."""
    kinds = list(decision_kinds)
    finals = [k for k in kinds if k in FINAL_LIFECYCLE_DECISION_KINDS]
    if len(finals) > 1:
        raise InvalidInputError("contradictory_resolutions", "a candidate has more than one final decision")
    if finals:
        return {
            LifecycleDecisionKind.ACCEPT_LIFECYCLE_EVENT: LifecycleCandidateResolutionState.ACCEPTED,
            LifecycleDecisionKind.REJECT_CANDIDATE: LifecycleCandidateResolutionState.REJECTED,
        }[finals[0]]
    return LifecycleCandidateResolutionState.DEFERRED if kinds else LifecycleCandidateResolutionState.UNRESOLVED


# ---------------- canonical facts, each with the decision and candidate that established it, append-only

class AcceptedNameChange(DomainModel):
    id: int = Field(gt=0)
    company_id: UUID
    new_name: str
    effective: EventTime | None
    resolution_decision_id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    created_at: UtcDatetime


class AcceptedOperatingStatus(DomainModel):
    id: int = Field(gt=0)
    company_id: UUID
    status: OperatingStatus
    as_of: EventTime | None
    resolution_decision_id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    created_at: UtcDatetime


class AcceptedAcquisition(DomainModel):
    id: int = Field(gt=0)
    company_id: UUID
    acquirer_name: str
    acquirer_company_id: UUID | None
    transaction_date: EventTime | None
    resolution_decision_id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    created_at: UtcDatetime


class AcceptedSuccessorRelationship(DomainModel):
    id: int = Field(gt=0)
    company_id: UUID
    related_entity_name: str
    related_company_id: UUID | None
    relationship_kind: SuccessorRelationshipKind
    resolution_decision_id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    created_at: UtcDatetime


class CompanyLifecycleState(DomainModel):
    """A company's lifecycle history: EVERY accepted fact, oldest first, per fact kind -- never just the
    latest. "Current" (e.g. current_legal_name / current_operating_status) is a plain derived property here
    (most recent by created_at), computed at read time; nothing about the underlying rows is ever rewritten to
    reflect it."""

    company_id: UUID
    name_history: tuple[AcceptedNameChange, ...] = ()
    status_history: tuple[AcceptedOperatingStatus, ...] = ()
    acquisitions: tuple[AcceptedAcquisition, ...] = ()
    successors: tuple[AcceptedSuccessorRelationship, ...] = ()

    @property
    def current_legal_name(self) -> str | None:
        """None means "no rename has ever been accepted" -- the caller falls back to the company's own
        original company_name (canonical role), which this module never reads or duplicates."""
        return self.name_history[-1].new_name if self.name_history else None

    @property
    def current_operating_status(self) -> OperatingStatus | None:
        return self.status_history[-1].status if self.status_history else None


class LifecycleLineageLink(DomainModel):
    """One canonical lifecycle claim traced to its exact evidence:
    fact -> LifecycleResolutionDecision -> LifecycleEventCandidate -> ProcessingAttempt -> Observation -> RawPayload -> Source."""

    fact_kind: str   # "name_change" | "operating_status" | "acquisition" | "successor"
    fact_id: int = Field(gt=0)
    company_id: UUID
    resolution_decision_id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    processing_attempt_id: int = Field(gt=0)
    observation_id: int = Field(gt=0)
    content_hash: str
    source_id: int = Field(gt=0)
    source_key: str
    evidence: EvidenceLocator
