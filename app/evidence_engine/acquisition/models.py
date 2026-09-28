"""
Typed contracts for the acquisition pipeline (Task 20). Pydantic where the
shape crosses an external I/O boundary (mirrors `models.py::Claim`'s own
convention -- external/untrusted-origin data gets validated); plain
frozen dataclasses for pure, internal, already-trusted values (mirrors
`scoring.py`'s own convention).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.evidence_engine.models import SourceType, SupportStatus


# --- 1. Input normalization (spec item 3 -- deliberately narrow) ------------

class CompanyAnalysisInput(BaseModel):
    """The one supported input shape for this task: a company identity plus
    a website. Deliberately narrow (item 3) -- PDF/pitch-deck ingestion is
    out of scope unless it falls out for free, which it does not here."""

    company_name: str
    website_url: str
    # A lightweight, engine-native identity (spec Part 7.3's own "no V2
    # Company integration" decision, carried forward) -- if omitted, a
    # stable slug is derived from company_name at acquisition time.
    company_ref: str | None = None
    as_of: date | None = None


# --- 2. Research planning ----------------------------------------------------

class ResearchTopic(str, Enum):
    """One topic per pillar, plus a dedicated stage-signal topic -- the
    deterministic grouping `research_plan.py` uses (item 4's own "group
    related research where efficient," never one search per dimension)."""

    PRODUCT_AND_TECHNOLOGY = "product_and_technology"
    MARKET_AND_COMPETITION = "market_and_competition"
    TEAM_AND_LEADERSHIP = "team_and_leadership"
    TRACTION_AND_CUSTOMERS = "traction_and_customers"
    EXECUTION_AND_SHIPPING = "execution_and_shipping"
    FUNDING_AND_FINANCIALS = "funding_and_financials"


@dataclass(frozen=True)
class ResearchQuery:
    topic: ResearchTopic
    query_text: str
    target_dimensions: tuple[str, ...]


@dataclass(frozen=True)
class ResearchPlan:
    company_name: str
    queries: tuple[ResearchQuery, ...]

    @property
    def query_count(self) -> int:
        return len(self.queries)


# --- 3. Source discovery / retrieval -----------------------------------------

class SearchResult(BaseModel):
    """One search-engine result -- NOT yet evidence (item 6: "a URL alone
    is not evidence"). Must be retrieved and inspected before it can
    support a claim candidate."""

    url: str
    title: str
    snippet: str
    query_text: str
    topic: ResearchTopic


def _source_id(url: str) -> str:
    """A stable identifier derived from the URL alone -- used ONLY to
    reference a `RetrievedSource` within one acquisition run (an
    engineering convenience), never as `independence_group_id` or
    `claim_id` (item 11's own explicit "do not use source URL alone as
    claim identity" -- that rule governs FACT identity, computed in
    `claim_identity.py` from the claim's own normalized content, not
    from this source-referencing id)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


class RetrievedSource(BaseModel):
    """A source that was actually fetched and inspected -- the unit
    `extraction.py` reads from. Every field spec Part 2.1/2.2 requires a
    `Claim` to carry back to its own source is captured here first, so
    extraction never has to invent one."""

    source_id: str
    url: str
    title: str
    publisher: str
    source_type: SourceType
    published_at: date | None = None
    retrieved_at: date
    content: str  # bounded-length raw fetched text (item 6's own required fields)
    discovered_by_query: str
    discovered_by_topic: ResearchTopic

    @staticmethod
    def from_url(
        url: str, title: str, publisher: str, source_type: SourceType,
        content: str, retrieved_at: date, discovered_by_query: str, discovered_by_topic: ResearchTopic,
        published_at: date | None = None,
    ) -> "RetrievedSource":
        return RetrievedSource(
            source_id=_source_id(url), url=url, title=title, publisher=publisher,
            source_type=source_type, published_at=published_at, retrieved_at=retrieved_at,
            content=content, discovered_by_query=discovered_by_query, discovered_by_topic=discovered_by_topic,
        )


# --- 4. Evidence extraction (structured, grounded -- item 8/9) --------------

class ExtractedClaimCandidate(BaseModel):
    """What an extraction call may produce -- deliberately NOT a `Claim`
    yet. A candidate becomes a real `Claim` only after grounding
    validation (`extraction.py::validate_candidate`) and canonical-
    identity assignment (`claim_identity.py`) both succeed; a candidate
    that fails either is rejected, never "repaired" with model
    knowledge (item 9's own explicit instruction).

    Deliberately does NOT carry `source_publisher`/`source_type`/
    `retrieved_at`/`published_at` as free-form fields the model could
    assert independently of the source it cites -- those are always
    read from the `RetrievedSource` the candidate's own `source_id`
    references, never re-asserted by extraction (structurally prevents
    "fabricate a date/publisher," item 9)."""

    source_id: str
    claim_text: str
    subject_entity: str
    excerpt: str
    assessment_criteria: list[str] = Field(default_factory=list)
    structured_fact: dict[str, str] | None = None
    support_status: SupportStatus = SupportStatus.DIRECTLY_SUPPORTED


class ClaimRejectionReason(str, Enum):
    NO_SOURCE_ID = "no_source_id"
    UNKNOWN_SOURCE_ID = "unknown_source_id"
    EMPTY_EXCERPT = "empty_excerpt"
    EXCERPT_NOT_GROUNDED_IN_SOURCE = "excerpt_not_grounded_in_source"
    NO_RECOGNIZED_DIMENSION = "no_recognized_dimension"
    MALFORMED_STRUCTURED_FACT = "malformed_structured_fact"


@dataclass(frozen=True)
class RejectedClaimCandidate:
    candidate: ExtractedClaimCandidate
    reason: ClaimRejectionReason
    detail: str


@dataclass(frozen=True)
class ExtractionRequest:
    """What an `EvidenceExtractor` provider receives -- one already-
    retrieved source's own content plus the dimensions its discovering
    query targeted (research_plan.py). The extractor's only job is to
    propose `ExtractedClaimCandidate`s; it never sees, and cannot
    influence, any other company's data or any scoring table."""

    source: RetrievedSource
    target_dimensions: tuple[str, ...]
    company_name: str


@dataclass(frozen=True)
class ExtractionResponse:
    candidates: tuple[ExtractedClaimCandidate, ...]


# --- 5. Budgets (item 5) -----------------------------------------------------

@dataclass(frozen=True)
class AcquisitionBudget:
    """Every configurable limit item 5 asks for, in one place. Defaults
    are deliberately small -- see `docs/architecture/
    EVIDENCE_ACQUISITION_PIPELINE.md` §5 for the worked maximum-call-shape
    calculation these defaults imply."""

    max_queries_per_topic: int = 2
    max_topics: int = 6  # one per pillar -- see ResearchTopic
    max_sources_per_query: int = 3
    max_total_sources: int = 24
    max_extraction_calls: int = 24  # one per retained source, capped independently
    max_extraction_retries: int = 1  # matches classify_with_recovery's own established retry count
    max_search_retries: int = 1
    max_retrieval_retries: int = 1


# --- 6. Telemetry (item 18/19) -----------------------------------------------

@dataclass(frozen=True)
class StageTelemetry:
    stage_name: str
    duration_seconds: float
    detail: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ExternalCallRecord:
    """One record per external call the pipeline WOULD make (or, for the
    deterministic offline test providers, did make against a fake) --
    item 19's own "call count; model/provider if available; tokens if
    available; estimated/actual cost if the provider exposes it; elapsed
    time." Never invents a cost/token figure the provider did not
    actually report (item 19's own explicit prohibition) -- `tokens`/
    `cost_usd` are `None`, not `0`, when unknown."""

    call_type: str  # "search" | "retrieval" | "extraction"
    provider_name: str
    duration_seconds: float
    tokens: int | None = None
    cost_usd: float | None = None
    succeeded: bool = True


@dataclass(frozen=True)
class AcquisitionQualityFinding:
    """Item 23's own required distinction, made a first-class, structured
    record rather than a log line: an ACQUISITION-layer observation
    (research/extraction did not retrieve/extract available evidence),
    explicitly never a claim that the METHODOLOGY itself is wrong. Never
    used to justify loosening a gate or changing a score mapping."""

    stage: str
    description: str
    topic: ResearchTopic | None = None


@dataclass(frozen=True)
class AcquisitionTelemetry:
    run_id: str
    company_ref: str
    started_at: datetime
    stages: tuple[StageTelemetry, ...] = field(default_factory=tuple)
    external_calls: tuple[ExternalCallRecord, ...] = field(default_factory=tuple)
    queries_issued: int = 0
    sources_retrieved: int = 0
    claims_extracted: int = 0
    claims_rejected: int = 0
    claims_deduplicated: int = 0
    claims_disputed: int = 0
    retries_used: int = 0
    quality_findings: tuple[AcquisitionQualityFinding, ...] = field(default_factory=tuple)

    @property
    def total_duration_seconds(self) -> float:
        return sum(s.duration_seconds for s in self.stages)

    @property
    def total_external_calls(self) -> int:
        return len(self.external_calls)
