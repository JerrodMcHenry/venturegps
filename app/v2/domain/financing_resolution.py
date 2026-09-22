"""
Financing resolution: the explicit authority boundary between an UNTRUSTED FinancingEventCandidate and a
canonical FinancingEvent.

    FinancingEventCandidate [untrusted] -> FinancingResolutionDecision [human or rule] -> FinancingEvent [trusted]

AI MAY PROPOSE. AI MAY NOT DECIDE. AI MAY NOT PROMOTE. AI MAY NOT MERGE FINANCING EVENTS. AI MAY NOT DETERMINE A
VERIFIED ROUND AMOUNT. Structural, not a promise: the authority vocabulary is exactly RULE and HUMAN (there is no AI
member; the domain re-uses the Company-resolution Authority value object, which refuses AI-named actors), the database
CHECKs the same two values, and no financing rule is registered, so a rule can decide nothing.

This is deliberately NOT a generalisation of Company resolution: financing-event identity has different semantics
(many candidates from different sources may describe ONE real-world financing; facts are selected, not blindly copied).

Decision kinds:
  create_event        the candidate describes a NEW canonical financing event of the candidate's Company
  attach_to_event     the candidate describes an EXISTING canonical event of the SAME Company (no merge, ever)
  reject_candidate    the candidate is not a valid financing event (reason code required)
  defer_candidate     unresolved / insufficient evidence (reason code required; NOT final)

The canonical event is only what was explicitly ACCEPTED. A FactSelection names exactly which of the resolved candidate's
facts become canonical; nothing is copied implicitly, an attach with no selection is legitimate, and a fact the event
already holds is never overwritten (FactAlreadyAcceptedError): correction/versioning is a future increment.

verified_round_amount means only: "VentureGPS explicitly accepted this amount as the canonical round amount of this
event under an authoritative decision". It can come ONLY from a candidate's announced_round_amount, ONLY by human
authority. offering_amount and amount_sold never become it (a Form D offering or sold amount is not a round size).
"""

from collections.abc import Sequence
from enum import Enum
from types import MappingProxyType
from uuid import UUID

from pydantic import Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.financing import FinancingDateKind, FinancingType, Money, Stage
from app.v2.domain.processing_attempt import ReasonCode
from app.v2.domain.resolution import Authority, AuthorityKind
from app.v2.domain.time import EventTime, UtcDatetime


class FinancingDecisionKind(str, Enum):
    CREATE_EVENT = "create_event"
    ATTACH_TO_EVENT = "attach_to_event"
    REJECT_CANDIDATE = "reject_candidate"
    DEFER_CANDIDATE = "defer_candidate"


FINAL_FINANCING_DECISION_KINDS = frozenset({
    FinancingDecisionKind.CREATE_EVENT, FinancingDecisionKind.ATTACH_TO_EVENT, FinancingDecisionKind.REJECT_CANDIDATE,
})

# Every financing rule that may decide, and the kinds it is authorised to make. DELIBERATELY EMPTY: no deterministic
# rule is yet safe enough for financing identity (same company / amount / stage / similar date / similar text / same
# investor are never sufficient). Adding one is a future, separately reviewed change to this registry AND a migration.
FINANCING_RULE_AUTHORITY: "MappingProxyType[str, frozenset[FinancingDecisionKind]]" = MappingProxyType({})


def may_decide(authority: Authority, kind: FinancingDecisionKind) -> bool:
    """A human may make any financing decision; a rule only what a REGISTERED financing rule is authorised to."""
    if authority.kind is AuthorityKind.HUMAN:
        return True
    return kind in FINANCING_RULE_AUTHORITY.get(authority.id, frozenset())


class FactSelection(DomainModel):
    """Which of the resolved candidate's facts the resolver explicitly accepts as canonical. Small and closed: not a patch language.

      stage                    accept the candidate's stage (must have been proposed with evidence)
      financing_type           accept the candidate's financing type
      verified_round_amount    accept the candidate's ANNOUNCED_ROUND_AMOUNT as the verified round amount (human only)
      dates                    accept these candidate date kinds (each keeps its precision)
    """

    stage: bool = False
    financing_type: bool = False
    verified_round_amount: bool = False
    dates: tuple[FinancingDateKind, ...] = ()

    @model_validator(mode="after")
    def _dates_are_unique(self) -> "FactSelection":
        if len(set(self.dates)) != len(self.dates):
            raise InvalidInputError("duplicate_date_selection", "a date kind may be selected at most once")
        return self

    @property
    def is_empty(self) -> bool:
        return not (self.stage or self.financing_type or self.verified_round_amount or self.dates)


NO_FACTS = FactSelection()


class StoredFinancingEvent(DomainModel):
    """The whole canonical identity row: an opaque id, the ONE Company it belongs to, and when it was created."""

    id: UUID
    company_id: UUID
    created_at: UtcDatetime


class StoredFinancingResolutionDecision(DomainModel):
    id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    decision_kind: FinancingDecisionKind
    financing_event_id: UUID | None = None
    authority: Authority
    reason_code: ReasonCode | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _shape_matches_the_kind(self) -> "StoredFinancingResolutionDecision":
        needs_event = self.decision_kind in (FinancingDecisionKind.CREATE_EVENT, FinancingDecisionKind.ATTACH_TO_EVENT)
        if (self.financing_event_id is not None) != needs_event or (self.reason_code is None) != needs_event:
            raise InvariantViolationError("invalid_decision_state", "decision kind, event and reason code are inconsistent")
        if self.authority.kind is AuthorityKind.RULE and self.decision_kind is not FinancingDecisionKind.ATTACH_TO_EVENT:
            raise InvariantViolationError("authority_exceeded", "a rule may only attach a candidate to an event")
        return self

    @property
    def is_final(self) -> bool:
        return self.decision_kind in FINAL_FINANCING_DECISION_KINDS


class FinancingCandidateResolutionState(str, Enum):
    UNRESOLVED = "unresolved"
    DEFERRED = "deferred"
    EVENT_CREATED = "event_created"
    ATTACHED = "attached"
    REJECTED = "rejected"


def derive_financing_candidate_state(decision_kinds: Sequence[FinancingDecisionKind]) -> FinancingCandidateResolutionState:
    """Resolution state is DERIVED from decision history (oldest first); candidates never store it."""
    kinds = list(decision_kinds)
    finals = [k for k in kinds if k in FINAL_FINANCING_DECISION_KINDS]
    if len(finals) > 1:
        raise InvariantViolationError("contradictory_resolutions", "a candidate has more than one final decision")
    if finals:
        return {
            FinancingDecisionKind.CREATE_EVENT: FinancingCandidateResolutionState.EVENT_CREATED,
            FinancingDecisionKind.ATTACH_TO_EVENT: FinancingCandidateResolutionState.ATTACHED,
            FinancingDecisionKind.REJECT_CANDIDATE: FinancingCandidateResolutionState.REJECTED,
        }[finals[0]]
    return FinancingCandidateResolutionState.DEFERRED if kinds else FinancingCandidateResolutionState.UNRESOLVED


# ---------------- canonical facts, each with the decision and candidate (fact) that established it

class AcceptedStage(DomainModel):
    stage: Stage
    resolution_decision_id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)        # the candidate's stage evidence is the evidence for this fact

    @model_validator(mode="after")
    def _is_stated(self) -> "AcceptedStage":
        if self.stage is Stage.UNKNOWN:
            raise InvalidInputError("unknown_stage_is_absence", "an unknown stage is expressed by holding no canonical stage")
        return self


class AcceptedFinancingType(DomainModel):
    financing_type: FinancingType
    resolution_decision_id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)

    @model_validator(mode="after")
    def _is_stated(self) -> "AcceptedFinancingType":
        if self.financing_type is FinancingType.UNKNOWN:
            raise InvalidInputError("unknown_type_is_absence", "an unknown financing type is expressed by holding no canonical type")
        return self


class AcceptedVerifiedRoundAmount(DomainModel):
    money: Money
    resolution_decision_id: int = Field(gt=0)
    candidate_amount_id: int = Field(gt=0)   # the exact candidate announced_round_amount row


class AcceptedDate(DomainModel):
    kind: FinancingDateKind
    time: EventTime                          # keeps its precision
    resolution_decision_id: int = Field(gt=0)
    candidate_date_id: int = Field(gt=0)


class CanonicalFinancingEvent(DomainModel):
    """A canonical event with ONLY the facts explicitly accepted. Unknown is legitimate: every fact may be absent."""

    event: StoredFinancingEvent
    stage: AcceptedStage | None = None
    financing_type: AcceptedFinancingType | None = None
    verified_round_amount: AcceptedVerifiedRoundAmount | None = None
    dates: tuple[AcceptedDate, ...] = ()


class FinancingLineageLink(DomainModel):
    """One canonical claim traced to its exact evidence:
    event/fact -> ResolutionDecision -> Candidate (fact) -> ProcessingAttempt -> Observation -> RawPayload -> Source -> bytes."""

    subject: str                    # "event" | "stage" | "financing_type" | "verified_round_amount" | "<date kind>"
    financing_event_id: UUID
    resolution_decision_id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    candidate_fact_id: int | None = None       # the candidate amount/date row; None for event/stage/type (they live on the candidate)
    processing_attempt_id: int = Field(gt=0)
    observation_id: int = Field(gt=0)
    content_hash: str
    source_id: int = Field(gt=0)
    source_key: str
    evidence: EvidenceLocator       # the exact byte span supporting THIS claim
