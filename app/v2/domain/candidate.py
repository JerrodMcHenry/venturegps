"""
Company candidates: UNTRUSTED PROPOSALS that some evidence may describe a company.

A candidate is what a processor PROPOSED. It is not canonical truth, a Company, a
claim, a classification, or an accepted AI answer. Two things are kept apart:

  CompanyCandidateProposal   unpersisted output of a proposer.
  StoredCompanyCandidate     an immutable record of a proposal that passed
                             structural and EVIDENCE validation.

Validation here means exactly: "the proposal is structurally valid and the
evidence it cites exists in the immutable RawPayload and contains the proposed
value". It does NOT mean "the proposed company identity is correct". Deciding
that is future deterministic-rule or human resolution; nothing in this layer
can promote a candidate.

Evidence is deterministic and byte-based: an EvidenceLocator names a half-open
byte range [byte_start, byte_end) of the exact stored payload bytes and the
sha256 of those bytes. Character offsets are never used (payload truth is
bytes). A free-floating quote that cannot be re-verified is not evidence.

A proposal carries no confidence, model, provider or prompt fields: those
belong to a later, separately reviewed layer, and extra fields are forbidden.
"""

import re
from enum import Enum
from typing import ClassVar

from pydantic import Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.content import ContentHash
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.source import validate_source_url
from app.v2.domain.time import UtcDatetime

MAX_EVIDENCE_SPAN_BYTES = 4096
MAX_CANDIDATE_NAME_LENGTH = 300
MAX_IDENTIFIERS_PER_CANDIDATE = 10
MAX_CANDIDATES_PER_ATTEMPT = 50

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DOMAIN = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")


class IdentifierType(str, Enum):
    """The only identifier kinds Phase 1 can propose. Each is a PROPOSAL, never a canonical identifier."""

    DOMAIN = "domain"
    WEBSITE_URL = "website_url"


def validate_candidate_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_CANDIDATE_NAME_LENGTH
        or value != value.strip()
        or _CONTROL.search(value)
    ):
        raise InvalidInputError("invalid_candidate_name", "candidate name must be 1-300 printable characters without surrounding whitespace")
    return value


def validate_domain_name(value: object) -> str:
    """A lowercase ASCII (punycode for IDNs) hostname with at least one dot. Proposers normalize; the domain never guesses."""
    if not isinstance(value, str) or len(value) > 253 or _DOMAIN.fullmatch(value) is None:
        raise InvalidInputError("invalid_domain", "domain must be a lowercase ASCII hostname such as example.com")
    return value


class EvidenceLocator(DomainModel):
    """Where a proposed value is supported: a byte range of the immutable payload plus the hash of those bytes."""

    byte_start: int = Field(ge=0)
    byte_end: int = Field(ge=1)
    evidence_hash: ContentHash

    @model_validator(mode="after")
    def _span_is_well_formed(self) -> "EvidenceLocator":
        if self.byte_end <= self.byte_start:
            raise InvalidInputError("evidence_span_invalid", "evidence span must end after it starts")
        if self.byte_end - self.byte_start > MAX_EVIDENCE_SPAN_BYTES:
            raise InvalidInputError("evidence_span_too_large", "evidence span exceeds the maximum length")
        return self

    @property
    def length(self) -> int:
        return self.byte_end - self.byte_start


class ProposedIdentifier(DomainModel):
    identifier_type: IdentifierType
    value: str
    evidence: EvidenceLocator

    @model_validator(mode="after")
    def _value_matches_its_type(self) -> "ProposedIdentifier":
        if self.identifier_type is IdentifierType.DOMAIN:
            validate_domain_name(self.value)
        else:
            validate_source_url(self.value)
        return self


class CompanyCandidateProposal(DomainModel):
    proposed_name: str
    name_evidence: EvidenceLocator
    identifiers: tuple[ProposedIdentifier, ...] = ()

    @model_validator(mode="after")
    def _well_formed(self) -> "CompanyCandidateProposal":
        validate_candidate_name(self.proposed_name)
        if len(self.identifiers) > MAX_IDENTIFIERS_PER_CANDIDATE:
            raise InvalidInputError("too_many_identifiers", "a candidate may propose at most 10 identifiers")
        seen = {(i.identifier_type, i.value) for i in self.identifiers}
        if len(seen) != len(self.identifiers):
            raise InvalidInputError("duplicate_identifier", "an identifier may be proposed only once per candidate")
        return self


class StoredCompanyCandidate(DomainModel):
    """A persisted, immutable, STILL UNTRUSTED candidate. Candidates have no updated_time."""

    TRUST_LEVEL: ClassVar[str] = "untrusted_proposal"

    id: int = Field(gt=0)
    processing_attempt_id: int = Field(gt=0)
    candidate_ordinal: int = Field(ge=1)   # position in the proposer's output; identity is (attempt, ordinal), never the name
    proposal: CompanyCandidateProposal
    created_at: UtcDatetime                # assigned by the database
