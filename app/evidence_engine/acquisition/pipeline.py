"""
The acquisition pipeline orchestrator (Task 20). Ties together every
stage the task's own item 2 lists:

    1. Input normalization        -- this module, `_normalize_input()`
    2. Research planning          -- research_plan.py (deterministic)
    3. Source discovery/retrieval -- providers.py (Protocols) + this module
    4. Evidence extraction        -- extraction.py
    5. Evidence normalization     -- claim_identity.py::finalize_claim()
    6. Provenance/independence    -- claim_identity.py's own canonical
                                      independence_group_id (reused unchanged
                                      by ledger.py/provenance.py downstream)
    7. Contradiction/duplicate handling -- contradiction.py
    8. Evidence Ledger construction     -- EvidenceLedger.from_list()
    9. Stage resolution           -- full_analysis.py::assemble_full_analysis()
   10. Six-pillar evaluation      -- (same call)
   11. Cross-pillar audit         -- (same call)
   12. Company-level Coverage/Confidence/publication -- (same call)
   13. Final FullCompanyAnalysis  -- (same call)

**Stages 9-13 are NOT reimplemented here.** `full_analysis.py::
assemble_full_analysis()` (Tasks 18-19) already does exactly this,
already tested (357 tests), already proven against real evidence six
times over. This module's own job stops at producing a correct,
canonical `EvidenceLedger` -- everything downstream of that is the
existing, unmodified engine.

**Failure containment (item 16).** Every external-provider call (search,
retrieve, extract) is wrapped so a single failure degrades to an
`AcquisitionQualityFinding` and the pipeline continues with whatever
other queries/sources/extractions succeeded -- it never raises out of
`run_acquisition_pipeline()` for a partial failure. The one exception:
if NO source was ever successfully retrieved at all, the resulting
`EvidenceLedger` is legitimately empty, and `assemble_full_analysis()`'s
own existing behavior (every pillar withholds, company-level
publishable=False) is the correct, honest result -- not a pipeline
error.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import date, datetime, timezone

from app.evidence_engine.acquisition.claim_identity import finalize_claim
from app.evidence_engine.acquisition.contradiction import detect_contradictions
from app.evidence_engine.acquisition.extraction import extract_with_recovery
from app.evidence_engine.acquisition.models import (
    AcquisitionBudget,
    AcquisitionQualityFinding,
    AcquisitionTelemetry,
    CompanyAnalysisInput,
    ExtractionRequest,
    ResearchPlan,
    RetrievedSource,
    SearchResult,
    StageTelemetry,
)
from app.evidence_engine.acquisition.providers import EvidenceExtractor, SearchProvider, SourceRetriever
from app.evidence_engine.acquisition.research_plan import build_research_plan
from app.evidence_engine.full_analysis import FullCompanyAnalysis, assemble_full_analysis
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _NON_SLUG.sub("-", name.lower()).strip("-") or "company"


def _normalize_input(input: CompanyAnalysisInput) -> tuple[str, date]:
    """Stage 1. Deterministic -- no I/O, no model call."""
    company_ref = input.company_ref or _slugify(input.company_name)
    as_of = input.as_of or date.today()
    return company_ref, as_of


class AcquisitionResult:
    """The pipeline's own top-level output -- deliberately a plain,
    explicit container (not a dataclass field explosion) so telemetry,
    the ledger, and the final analysis are each independently
    inspectable. `full_analysis` is exactly the same `FullCompanyAnalysis`
    every other pillar sanity-check script already produces -- this
    pipeline's only contribution is HOW the ledger it is built from was
    populated."""

    def __init__(
        self, company_ref: str, ledger: EvidenceLedger, full_analysis: FullCompanyAnalysis,
        telemetry: AcquisitionTelemetry, rejected_count: int,
    ) -> None:
        self.company_ref = company_ref
        self.ledger = ledger
        self.full_analysis = full_analysis
        self.telemetry = telemetry
        self.rejected_count = rejected_count


def _retrieve_sources(
    plan: ResearchPlan, search_provider: SearchProvider, source_retriever: SourceRetriever,
    budget: AcquisitionBudget, as_of: date, quality_findings: list[AcquisitionQualityFinding],
) -> tuple[list[RetrievedSource], int]:
    """Stage 3. Returns the retrieved sources plus the number of search
    queries actually issued. Bounded by `budget.max_total_sources`
    across the whole run, not just per query."""
    sources: list[RetrievedSource] = []
    queries_issued = 0

    for query in plan.queries:
        if len(sources) >= budget.max_total_sources:
            break
        queries_issued += 1

        results: tuple[SearchResult, ...] = ()
        search_failed = False
        for attempt in range(budget.max_search_retries + 1):
            try:
                results = search_provider.search(query)
                search_failed = False
                break
            except Exception as exc:  # noqa: BLE001 -- one failed search must never crash the run
                search_failed = True
                if attempt == budget.max_search_retries:
                    quality_findings.append(AcquisitionQualityFinding(
                        stage="source_discovery", topic=query.topic,
                        description=f"search failed for query {query.query_text!r} after {attempt + 1} attempt(s): {exc}",
                    ))

        if search_failed:
            continue
        if not results:
            quality_findings.append(AcquisitionQualityFinding(
                stage="source_discovery", topic=query.topic,
                description=f"zero search results for query {query.query_text!r}",
            ))
            continue

        for result in results[: budget.max_sources_per_query]:
            if len(sources) >= budget.max_total_sources:
                break
            source: RetrievedSource | None = None
            retrieval_failed = False
            for attempt in range(budget.max_retrieval_retries + 1):
                try:
                    source = source_retriever.retrieve(result, as_of)
                    retrieval_failed = False
                    break
                except Exception as exc:  # noqa: BLE001 -- one failed retrieval must never crash the run
                    retrieval_failed = True
                    if attempt == budget.max_retrieval_retries:
                        quality_findings.append(AcquisitionQualityFinding(
                            stage="source_retrieval", topic=query.topic,
                            description=f"retrieval failed for {result.url!r} after {attempt + 1} attempt(s): {exc}",
                        ))
            if retrieval_failed:
                continue
            if source is None:
                quality_findings.append(AcquisitionQualityFinding(
                    stage="source_retrieval", topic=query.topic,
                    description=f"source retriever returned nothing for {result.url!r}",
                ))
                continue
            sources.append(source)

    return sources, queries_issued


def _extract_claims(
    sources: list[RetrievedSource], plan: ResearchPlan, company_name: str, company_ref: str,
    evidence_extractor: EvidenceExtractor, budget: AcquisitionBudget,
    quality_findings: list[AcquisitionQualityFinding],
) -> tuple[list[Claim], int, int]:
    """Stage 4-6. Returns (finalized claims, total accepted candidates,
    total rejected candidates)."""
    query_by_topic = {q.topic: q for q in plan.queries}
    claims: list[Claim] = []
    accepted_count = 0
    rejected_count = 0

    for source in sources[: budget.max_extraction_calls]:
        target_dims = query_by_topic.get(source.discovered_by_topic)
        request = ExtractionRequest(
            source=source,
            target_dimensions=target_dims.target_dimensions if target_dims else (),
            company_name=company_name,
        )
        try:
            accepted, rejected, attempts = extract_with_recovery(
                evidence_extractor, request, max_attempts=1 + budget.max_extraction_retries,
            )
        except Exception as exc:  # noqa: BLE001 -- one failed extraction must never crash the run
            quality_findings.append(AcquisitionQualityFinding(
                stage="evidence_extraction", topic=source.discovered_by_topic,
                description=f"extraction raised for source {source.url!r}: {exc}",
            ))
            continue

        accepted_count += len(accepted)
        rejected_count += len(rejected)
        if rejected and not accepted:
            quality_findings.append(AcquisitionQualityFinding(
                stage="evidence_extraction", topic=source.discovered_by_topic,
                description=f"all {len(rejected)} candidate(s) from {source.url!r} rejected on grounding validation",
            ))

        for candidate in accepted:
            claims.append(finalize_claim(candidate, source, company_ref))

    return claims, accepted_count, rejected_count


def run_acquisition_pipeline(
    input: CompanyAnalysisInput,
    search_provider: SearchProvider,
    source_retriever: SourceRetriever,
    evidence_extractor: EvidenceExtractor,
    budget: AcquisitionBudget | None = None,
    company_display_names: tuple[str, ...] | None = None,
) -> AcquisitionResult:
    """The one orchestration entry point. Providers are required,
    explicit arguments -- there is no default that silently reaches the
    network (`providers.py::NotConfiguredProvider` is the only built-in
    default anywhere in this package, and it raises immediately if ever
    actually called)."""
    budget = budget or AcquisitionBudget()
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc)
    stages: list[StageTelemetry] = []
    quality_findings: list[AcquisitionQualityFinding] = []

    company_ref, as_of = _normalize_input(input)
    display_names = company_display_names or (input.company_name,)

    t0 = time.monotonic()
    plan = build_research_plan(input, budget)
    stages.append(StageTelemetry("research_planning", time.monotonic() - t0, {"queries_planned": plan.query_count}))

    t0 = time.monotonic()
    sources, queries_issued = _retrieve_sources(
        plan, search_provider, source_retriever, budget, as_of, quality_findings,
    )
    stages.append(StageTelemetry(
        "source_discovery_and_retrieval", time.monotonic() - t0,
        {"queries_issued": queries_issued, "sources_retrieved": len(sources)},
    ))

    t0 = time.monotonic()
    claims, accepted_count, rejected_count = _extract_claims(
        sources, plan, input.company_name, company_ref, evidence_extractor, budget, quality_findings,
    )
    stages.append(StageTelemetry(
        "evidence_extraction", time.monotonic() - t0,
        {"claims_accepted": accepted_count, "claims_rejected": rejected_count},
    ))

    t0 = time.monotonic()
    deduplicated_count = 0  # informational only -- real dedup happens at scoring time via independence_group_id (module docstring)
    claims_tuple = detect_contradictions(tuple(claims))
    disputed_count = sum(1 for c in claims_tuple if c.support_status.value == "disputed")
    stages.append(StageTelemetry(
        "contradiction_detection", time.monotonic() - t0, {"claims_disputed": disputed_count},
    ))

    t0 = time.monotonic()
    ledger = EvidenceLedger.from_list(list(claims_tuple))
    stages.append(StageTelemetry("ledger_construction", time.monotonic() - t0, {"claims_in_ledger": len(claims_tuple)}))

    if not sources:
        quality_findings.append(AcquisitionQualityFinding(
            stage="pipeline", description="zero sources were retrieved for this company across every planned query",
        ))

    t0 = time.monotonic()
    analysis = assemble_full_analysis(ledger, company_ref, as_of, display_names)
    stages.append(StageTelemetry(
        "six_pillar_evaluation_and_aggregation", time.monotonic() - t0,
        {
            "published_pillars": len(analysis.published_pillars),
            "withheld_pillars": len(analysis.withheld_pillars),
        },
    ))

    telemetry = AcquisitionTelemetry(
        run_id=run_id, company_ref=company_ref, started_at=started_at, stages=tuple(stages),
        queries_issued=queries_issued, sources_retrieved=len(sources),
        claims_extracted=accepted_count, claims_rejected=rejected_count,
        claims_deduplicated=deduplicated_count, claims_disputed=disputed_count,
        quality_findings=tuple(quality_findings),
    )

    return AcquisitionResult(
        company_ref=company_ref, ledger=ledger, full_analysis=analysis,
        telemetry=telemetry, rejected_count=rejected_count,
    )
