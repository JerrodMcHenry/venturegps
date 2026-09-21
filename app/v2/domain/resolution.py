"""
Resolution: the explicit authority boundary between an UNTRUSTED candidate and
canonical truth.

    CompanyCandidate [untrusted] -> ResolutionDecision [authority: rule or human] -> Company [trusted]

AI MAY PROPOSE. AI MAY NOT DECIDE. AI MAY NOT PROMOTE. This is permanent, and it is
structural rather than a promise: the authority vocabulary is exactly RULE and
HUMAN (there is no AI member to misuse), the database CHECKs the same two values,
actor ids are bounded shapes, and ids that name an AI are refused. A model's
confidence, or agreement between models, is not an input to any of this.

Decision kinds (the smallest useful vocabulary):
  create_company      the candidate is resolved as a NEW canonical Company (human only in Phase 1)
  attach_to_company   the candidate refers to an EXISTING Company
  reject_candidate    the candidate is explicitly rejected (reason code required)
  defer_candidate     no canonical decision yet; the review is recorded (reason code required)

A RULE may only attach, and only when a registered, versioned rule is deciding (RULE_AUTHORITY):
rules cannot create companies, reject, or accept new canonical facts. A HUMAN acts
under an opaque actor id such as "admin:jerrod" (no profile data lives in V2).

Decisions are append-only. Candidates stay immutable; whether a candidate is
resolved is DERIVED from its decision history (derive_candidate_state). At most one
FINAL decision (create/attach/reject) exists per candidate; a deferral is not final.
"""

import re
from collections.abc import Mapping, Sequence
from enum import Enum
from types import MappingProxyType
from uuid import UUID

from pydantic import Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.processing_attempt import ReasonCode
from app.v2.domain.time import UtcDatetime
from app.v2.domain.versions import validate_version_id


class DecisionKind(str, Enum):
    CREATE_COMPANY = "create_company"
    ATTACH_TO_COMPANY = "attach_to_company"
    REJECT_CANDIDATE = "reject_candidate"
    DEFER_CANDIDATE = "defer_candidate"


FINAL_DECISION_KINDS = frozenset({DecisionKind.CREATE_COMPANY, DecisionKind.ATTACH_TO_COMPANY, DecisionKind.REJECT_CANDIDATE})


class AuthorityKind(str, Enum):
    """Who may decide. Exactly two members, by design: there is nothing else to promote with."""

    RULE = "rule"
    HUMAN = "human"


RULE_EXACT_IDENTIFIER_MATCH = "exact_identifier_match.v1"

# Every rule that may decide, and the decision kinds it is authorised to make. Nothing else.
RULE_AUTHORITY: Mapping[str, frozenset[DecisionKind]] = MappingProxyType({
    RULE_EXACT_IDENTIFIER_MATCH: frozenset({DecisionKind.ATTACH_TO_COMPANY}),
})

_HUMAN_ACTOR = re.compile(r"[a-z][a-z0-9_]{0,31}:[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_AI_TOKENS = frozenset({"ai", "llm", "gpt", "chatgpt", "openai", "anthropic", "claude", "gemini", "copilot", "model", "bot", "agent"})
_NON_LETTERS = re.compile(r"[^a-z]+")


def names_an_ai_actor(value: str) -> bool:
    """Does this id contain a token that names an AI system? (a guard on top of the two-value vocabulary)"""
    return any(token in _AI_TOKENS for token in _NON_LETTERS.split(value.lower()))


class Authority(DomainModel):
    kind: AuthorityKind
    id: str

    @model_validator(mode="after")
    def _id_fits_the_authority(self) -> "Authority":
        if names_an_ai_actor(self.id):
            raise InvalidInputError("ai_authority_refused", "an AI actor cannot hold decision authority")
        if self.kind is AuthorityKind.HUMAN:
            if _HUMAN_ACTOR.fullmatch(self.id) is None:
                raise InvalidInputError("invalid_human_actor", "a human actor id looks like admin:name")
        else:
            validate_version_id(self.id)   # a rule id is versioned: name.vN (shape only: history of retired rules stays readable)
        return self

    def may_decide(self, kind: DecisionKind) -> bool:
        """Deciding (not reading history) requires a REGISTERED rule acting within its explicit authority."""
        if self.kind is AuthorityKind.HUMAN:
            return True
        return kind in RULE_AUTHORITY.get(self.id, frozenset())


def human_authority(actor_id: str) -> Authority:
    return Authority(kind=AuthorityKind.HUMAN, id=actor_id)


def rule_authority(rule_id: str) -> Authority:
    return Authority(kind=AuthorityKind.RULE, id=rule_id)


class StoredResolutionDecision(DomainModel):
    id: int = Field(gt=0)
    candidate_id: int = Field(gt=0)
    decision_kind: DecisionKind
    company_id: UUID | None = None
    authority: Authority
    reason_code: ReasonCode | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _shape_matches_the_kind(self) -> "StoredResolutionDecision":
        has_company = self.company_id is not None
        needs_company = self.decision_kind in (DecisionKind.CREATE_COMPANY, DecisionKind.ATTACH_TO_COMPANY)
        if has_company != needs_company or (self.reason_code is None) != needs_company:
            raise InvariantViolationError("invalid_decision_state", "decision kind, company and reason code are inconsistent")
        if self.authority.kind is AuthorityKind.RULE and self.decision_kind is not DecisionKind.ATTACH_TO_COMPANY:
            raise InvariantViolationError("authority_exceeded", "a rule may only attach a candidate to a company")
        return self

    @property
    def is_final(self) -> bool:
        return self.decision_kind in FINAL_DECISION_KINDS


class CandidateResolutionState(str, Enum):
    UNRESOLVED = "unresolved"
    DEFERRED = "deferred"
    COMPANY_CREATED = "company_created"
    ATTACHED = "attached"
    REJECTED = "rejected"


def derive_candidate_state(decision_kinds: Sequence[DecisionKind]) -> CandidateResolutionState:
    """Resolution state is DERIVED from decision history (oldest first); candidates never store it."""
    kinds = list(decision_kinds)
    finals = [k for k in kinds if k in FINAL_DECISION_KINDS]
    if len(finals) > 1:
        raise InvariantViolationError("contradictory_resolutions", "a candidate has more than one final decision")
    if finals:
        return {
            DecisionKind.CREATE_COMPANY: CandidateResolutionState.COMPANY_CREATED,
            DecisionKind.ATTACH_TO_COMPANY: CandidateResolutionState.ATTACHED,
            DecisionKind.REJECT_CANDIDATE: CandidateResolutionState.REJECTED,
        }[finals[0]]
    return CandidateResolutionState.DEFERRED if kinds else CandidateResolutionState.UNRESOLVED
