"""
Lifecycle-event candidates: UNTRUSTED PROPOSALS about a company's legal name history, acquisition, operating
status, or relationship to another entity, evidenced against an ALREADY-canonical Company (Increment 18.7).

    Observation  !=  LifecycleEventCandidate  !=  (future) accepted canonical lifecycle fact

A LifecycleEventCandidate never creates a new Company and never merges two Companies. It answers "what is
VentureGPS being TOLD about a company it already knows?" -- name history, acquisition, operating status, and
successor relationships are each a narrow, typed, independently-evidenced sub-fact, mirroring exactly how
FinancingEventCandidateProposal carries multiple optional typed sub-facts (stage/financing_type/amounts/dates)
under one candidate. This is deliberately NOT a generic event/knowledge-graph table: there are exactly four
fact kinds, each its own Pydantic type, each its own narrow database table (see migration 0012).

Four fact kinds, and what each means (see docs/v2/LIFECYCLE_DESIGN_18_7.md for the full rationale):
  name_change        the SAME legal entity was renamed; never rewrites the company's original name
  operating_status    active | acquired | ceased_operations | unknown -- UNKNOWN IS A LEGITIMATE, EXPLICIT
                       CLAIM here (unlike Stage/FinancingType, where "unknown" means "not proposed"): a human
                       or source may explicitly state "current status could not be determined"
  acquisition         a documented relationship between DISTINCT entities; never implies a status change or a
                       legal merger by itself -- accepting an acquisition fact does not write a status fact
  successor           a possible or confirmed relationship between DISTINCT entities; never transfers
                       identifiers, financing history, or classifications. An explicit first-party statement
                       that two entities are legally distinct is NOT, by itself, evidence of a successor
                       relationship -- it is a reason to propose no successor fact at all, not a weaker one.

A candidate must carry at least one of the four kinds -- an empty candidate proposes nothing and is refused at
construction. It may carry more than one (e.g. a single acquisition announcement that also happens to state a
new legal name), each independently evidenced and independently acceptable.

The company is identified ONLY by a canonical Company id -- never a name, domain, or URL: a lifecycle fact is
always about a company that has ALREADY been resolved to canonical identity (create_company_from_candidate
first; this module has no path to create one).

Candidate identity is (processing_attempt_id, candidate_ordinal), exactly like every other candidate type.
"""

from enum import Enum
from typing import ClassVar
from uuid import UUID

from pydantic import Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.candidate import EvidenceLocator, validate_candidate_name
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.time import EventTime, UtcDatetime

MAX_LIFECYCLE_CANDIDATES_PER_ATTEMPT = 50


class OperatingStatus(str, Enum):
    ACTIVE = "active"
    ACQUIRED = "acquired"
    CEASED_OPERATIONS = "ceased_operations"
    UNKNOWN = "unknown"   # a legitimate, explicit claim here -- "the evidence states status could not be determined"


class SuccessorRelationshipKind(str, Enum):
    POSSIBLE_SUCCESSOR = "possible_successor"
    CONFIRMED_SUCCESSOR = "confirmed_successor"
    # Deliberately no third "explicitly_distinct" kind: per the approved design, a first-party statement that
    # two entities are legally distinct is a reason to propose NO successor fact, never a weaker relationship.


class ProposedNameChange(DomainModel):
    new_name: str
    evidence: EvidenceLocator
    effective: EventTime | None = None   # None: the evidence supports the rename but not a specific date

    @model_validator(mode="after")
    def _new_name_is_a_valid_candidate_name(self) -> "ProposedNameChange":
        validate_candidate_name(self.new_name)
        return self


class ProposedOperatingStatus(DomainModel):
    status: OperatingStatus
    evidence: EvidenceLocator
    as_of: EventTime | None = None


class ProposedAcquisition(DomainModel):
    """acquirer_company_id is set ONLY when the acquirer is itself already a canonical VentureGPS company --
    acquirer_name is always present regardless, since the acquirer very often is not (e.g. Siemens
    Healthineers is not itself onboarded). A canonical link may be added later through a separately reviewed
    operation; this module never creates the acquirer as a company."""

    acquirer_name: str
    evidence: EvidenceLocator
    acquirer_company_id: UUID | None = None
    transaction_date: EventTime | None = None

    @model_validator(mode="after")
    def _acquirer_name_is_valid(self) -> "ProposedAcquisition":
        validate_candidate_name(self.acquirer_name)
        return self


class ProposedSuccessorRelationship(DomainModel):
    """related_company_id is set ONLY when the related entity is already canonical -- same reasoning as
    ProposedAcquisition.acquirer_company_id. Accepting this NEVER transfers identifiers, financing history, or
    classifications between the two companies; it is purely an annotation."""

    related_entity_name: str
    relationship_kind: SuccessorRelationshipKind
    evidence: EvidenceLocator
    related_company_id: UUID | None = None

    @model_validator(mode="after")
    def _related_entity_name_is_valid(self) -> "ProposedSuccessorRelationship":
        validate_candidate_name(self.related_entity_name)
        return self


class LifecycleEventCandidateProposal(DomainModel):
    """Unpersisted output of a human-guided proposal (see app.v2.tools.manual_fact -- there is no automated
    lifecycle extractor, by the same "a human decides what a page states" discipline every non-Form-D fact in
    V2 already uses). Carries no confidence, model, provider, or prompt fields."""

    company_id: UUID                       # a CANONICAL company; never a name, domain or URL
    event_evidence: EvidenceLocator        # evidence that a lifecycle-relevant event is being discussed at all
    name_change: ProposedNameChange | None = None
    operating_status: ProposedOperatingStatus | None = None
    acquisition: ProposedAcquisition | None = None
    successor: ProposedSuccessorRelationship | None = None

    @model_validator(mode="after")
    def _at_least_one_fact_is_proposed(self) -> "LifecycleEventCandidateProposal":
        if not (self.name_change or self.operating_status or self.acquisition or self.successor):
            raise InvalidInputError("empty_lifecycle_proposal", "a lifecycle candidate must propose at least one fact")
        return self


class StoredLifecycleEventCandidate(DomainModel):
    """A persisted, immutable, STILL UNTRUSTED proposal. Not a canonical fact about the company."""

    TRUST_LEVEL: ClassVar[str] = "untrusted_proposal"

    id: int = Field(gt=0)
    processing_attempt_id: int = Field(gt=0)
    candidate_ordinal: int = Field(ge=1)
    proposal: LifecycleEventCandidateProposal
    created_at: UtcDatetime     # assigned by the database
