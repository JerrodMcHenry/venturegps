"""
The Evidence Ledger's core data model (NEW_ENGINE_SPEC.md Part 2.1).

A Claim is the atomic, persisted unit of evidence. Nothing in this engine's
Assessment or Scoring layers ever reads raw research text directly -- only
Claim records, each with mandatory provenance.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SourceType(str, Enum):
    COMPANY_DISCLOSURE = "company_disclosure"
    INDEPENDENT_REPORTING = "independent_reporting"
    PUBLIC_FILING = "public_filing"
    PRODUCT_DOCUMENTATION = "product_documentation"
    AGGREGATOR_OR_DIRECTORY = "aggregator_or_directory"
    # Task 12, item 3: a public, third-party account with no identified
    # author/editorial process (e.g. an anonymous forum/comment-section
    # post) -- independent of the company, same as INDEPENDENT_REPORTING,
    # but NOT the same kind of independence as bylined, attributable
    # reporting. Kept as its own SourceType rather than a flag on
    # INDEPENDENT_REPORTING so the distinction is visible wherever
    # source_type is inspected, not just in the reliability weight table.
    COMMUNITY_COMMENTARY = "community_commentary"
    OTHER = "other"


# Source types a human reviewer would recognize as independent of the
# company itself -- used by dimension rubrics that explicitly require
# independent corroboration (spec Part 3.3: Differentiation Claim
# Corroboration, Defensibility Signal). COMPANY_DISCLOSURE and
# PRODUCT_DOCUMENTATION are the company's own words/product, not
# independent of it, even though PRODUCT_DOCUMENTATION is directly
# observable (spec Part 5's "URL is not proof of independent
# verification" -- a locatable, directly-observable source is not
# automatically an INDEPENDENT one). COMMUNITY_COMMENTARY is included --
# an anonymous forum comment is still independent of the company -- but
# it carries a lower SOURCE_RELIABILITY_WEIGHT (parameters.py) than
# attributable reporting, which is the separate question of how much any
# one independent source should be trusted (Task 12, item 3).
INDEPENDENT_SOURCE_TYPES = frozenset(
    {
        SourceType.INDEPENDENT_REPORTING,
        SourceType.PUBLIC_FILING,
        SourceType.AGGREGATOR_OR_DIRECTORY,
        SourceType.COMMUNITY_COMMENTARY,
    }
)


class SupportStatus(str, Enum):
    DIRECTLY_SUPPORTED = "directly_supported"
    INFERRED = "inferred"
    DISPUTED = "disputed"


LEDGER_VERSION = "1"


class Claim(BaseModel):
    """One atomic, checkable assertion, always traceable to a source.

    Field-by-field rationale: NEW_ENGINE_SPEC.md Part 2.1.
    """

    claim_id: str
    company_ref: str
    claim_text: str
    subject_entity: str

    source_url: str | None = None
    source_publisher: str
    source_type: SourceType

    published_at: date | None = None
    retrieved_at: date

    support_status: SupportStatus
    excerpt: str | None = None

    assessment_criteria: list[str] = Field(default_factory=list)
    independence_group_id: str

    contradicts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    # Generic carrier for an already-typed, already-extracted fact (e.g.
    # {"kind": "funding_round_type", "value": "Series B"} or {"kind":
    # "founding_year", "value": "2015"}) -- the same concept spec Part 5.1
    # calls a Computed dimension's "typed fact," generalized here so it can
    # also carry stage-determination signals (spec Part 4.1), which are not
    # themselves a scored Product & Technology dimension. Never used for
    # anything a Classified dimension's label should instead express.
    structured_fact: dict[str, str] | None = None

    ledger_version: str = LEDGER_VERSION

    @model_validator(mode="after")
    def _excerpt_required_when_scorable(self) -> "Claim":
        # Spec Part 2.1: excerpt is "Required when support_status is
        # directly_supported or inferred; absent for disputed entries
        # pending resolution." A directly_supported/inferred claim with
        # no excerpt is malformed and must be rejected at write time,
        # never silently persisted half-formed (spec Part 2.2).
        if self.support_status != SupportStatus.DISPUTED and not self.excerpt:
            raise ValueError(
                f"Claim {self.claim_id!r}: excerpt is required when "
                f"support_status is {self.support_status.value!r}"
            )
        if not self.source_publisher.strip():
            raise ValueError(f"Claim {self.claim_id!r}: source_publisher must not be blank")
        return self
