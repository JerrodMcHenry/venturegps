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
from app.evidence_engine.acquisition.concurrency_helpers import run_concurrently_with_containment
from app.evidence_engine.acquisition.contradiction import detect_contradictions
from app.evidence_engine.acquisition.dedup import dedup_search_results
from app.evidence_engine.acquisition.extraction import extract_many
from app.evidence_engine.acquisition.models import (
    AcquisitionBudget,
    AcquisitionQualityFinding,
    AcquisitionTelemetry,
    ClaimRoutingRecord,
    CompanyAnalysisInput,
    ExternalCallRecord,
    ExtractionRequest,
    ResearchPlan,
    RetrievedSource,
    SearchResult,
    StageTelemetry,
)
from app.evidence_engine.acquisition.providers import EvidenceExtractor, SearchProvider, SourceRetriever, drain_call_log
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


def _search_one(query, search_provider: SearchProvider, budget: AcquisitionBudget) -> tuple[SearchResult, ...]:
    """One query's own bounded retry loop (item 17's retry-ownership:
    THIS loop owns search retries, exclusively). Raises after the final
    attempt -- the caller (a `run_concurrently_with_containment` task)
    catches it, never this function itself, so a failure here never
    silently looks like "zero results" to the caller."""
    last_error: Exception | None = None
    for attempt in range(budget.max_search_retries + 1):
        try:
            return search_provider.search(query)
        except Exception as exc:  # noqa: BLE001 -- classified by the caller, not here
            last_error = exc
    assert last_error is not None
    raise last_error


def _retrieve_one(
    result: SearchResult, source_retriever: SourceRetriever, budget: AcquisitionBudget, as_of: date,
) -> RetrievedSource | None:
    """One source's own bounded retry loop (retrieval retries, owned
    exclusively here -- see module docstring's retry-ownership note)."""
    last_error: Exception | None = None
    for attempt in range(budget.max_retrieval_retries + 1):
        try:
            return source_retriever.retrieve(result, as_of)
        except Exception as exc:  # noqa: BLE001 -- classified by the caller, not here
            last_error = exc
    assert last_error is not None
    raise last_error


def _retrieve_sources(
    plan: ResearchPlan, search_provider: SearchProvider, source_retriever: SourceRetriever,
    budget: AcquisitionBudget, as_of: date, quality_findings: list[AcquisitionQualityFinding],
) -> tuple[list[RetrievedSource], int]:
    """Stage 3. Returns the retrieved sources plus the number of search
    queries actually issued.

    Task 21 changes from Task 20's own sequential version, in stage
    order (item 9's "search -> normalize -> dedup -> retrieve"):

    1. Search every query CONCURRENTLY (item 10), bounded by
       `budget.max_concurrent_searches`, each query's own retry loop
       (`_search_one`) unaffected -- concurrency is across queries, never
       a substitute for a query's own retry policy.
    2. Flatten every query's results, then `dedup_search_results()`
       (item 9) ONCE across the WHOLE plan, not per query -- a URL two
       different topic queries both happen to surface now costs exactly
       one retrieval+extraction slot, not two.
    3. Re-apply `budget.max_sources_per_query` on what SURVIVES dedup, in
       original (deduped) order, so no single query can crowd out every
       other query's own budget share even after cross-query collapsing.
    4. Retrieve every surviving result CONCURRENTLY (item 10), bounded by
       `budget.max_concurrent_retrievals`, each source's own retry loop
       (`_retrieve_one`) unaffected.

    Deterministic regardless of which concurrent call finishes first:
    every list this function builds is built by iterating a FIXED,
    already-known sequence (`plan.queries`, then `bounded_results`) and
    looking up that sequence's own outcome from the `{key: Outcome}` map
    `run_concurrently_with_containment` returns -- never by iterating the
    map itself or appending inside a concurrently-run task body."""
    search_tasks = {
        f"q{i}": (lambda q=query: _search_one(q, search_provider, budget))
        for i, query in enumerate(plan.queries)
    }
    search_outcomes = run_concurrently_with_containment(search_tasks, max_workers=budget.max_concurrent_searches)

    all_results: list[SearchResult] = []
    queries_issued = 0
    for i, query in enumerate(plan.queries):
        queries_issued += 1
        outcome = search_outcomes[f"q{i}"]
        if not outcome.ok:
            quality_findings.append(AcquisitionQualityFinding(
                stage="source_discovery", topic=query.topic,
                description=f"search failed for query {query.query_text!r} after "
                            f"{budget.max_search_retries + 1} attempt(s): {outcome.error}",
            ))
            continue
        if not outcome.value:
            quality_findings.append(AcquisitionQualityFinding(
                stage="source_discovery", topic=query.topic,
                description=f"zero search results for query {query.query_text!r}",
            ))
            continue
        all_results.extend(outcome.value)

    deduped_results = dedup_search_results(tuple(all_results))
    per_query_counts: dict[tuple, int] = {}
    bounded_results: list[SearchResult] = []
    for result in deduped_results:
        key = (result.topic, result.query_text)
        count = per_query_counts.get(key, 0)
        if count >= budget.max_sources_per_query:
            continue
        per_query_counts[key] = count + 1
        bounded_results.append(result)
        if len(bounded_results) >= budget.max_total_sources:
            break

    retrieve_tasks = {
        f"r{i}": (lambda res=result: _retrieve_one(res, source_retriever, budget, as_of))
        for i, result in enumerate(bounded_results)
    }
    retrieve_outcomes = run_concurrently_with_containment(retrieve_tasks, max_workers=budget.max_concurrent_retrievals)

    sources: list[RetrievedSource] = []
    for i, result in enumerate(bounded_results):
        outcome = retrieve_outcomes[f"r{i}"]
        if not outcome.ok:
            quality_findings.append(AcquisitionQualityFinding(
                stage="source_retrieval", topic=result.topic,
                description=f"retrieval failed for {result.url!r} after "
                            f"{budget.max_retrieval_retries + 1} attempt(s): {outcome.error}",
            ))
            continue
        if outcome.value is None:
            quality_findings.append(AcquisitionQualityFinding(
                stage="source_retrieval", topic=result.topic,
                description=f"source retriever returned nothing for {result.url!r}",
            ))
            continue
        sources.append(outcome.value)

    return sources, queries_issued


def _chunk(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _extract_claims(
    sources: list[RetrievedSource], plan: ResearchPlan, company_name: str, company_ref: str,
    evidence_extractor: EvidenceExtractor, budget: AcquisitionBudget,
    quality_findings: list[AcquisitionQualityFinding],
) -> tuple[list[Claim], int, int, list[ClaimRoutingRecord]]:
    """Stage 4-6.

    Task 21 changes from Task 20's own one-call-per-source version (item
    6's own batching requirement): retained sources are grouped into
    fixed-size batches (`budget.max_sources_per_batch`), and each batch
    is handed to `extraction.py::extract_many()` in ONE call -- which
    itself only makes ONE real external call per batch if the extractor
    is batch-capable (`providers_live.py::OpenAIEvidenceExtractor`);
    every existing fake (fakes.py) is not, so `extract_many()` falls back
    to per-source calls for them, making this change a pure efficiency
    change for a real provider and a complete no-op (byte-identical
    behavior) for every offline test using a fake.

    Batches are then dispatched CONCURRENTLY (item 10), bounded by
    `budget.max_concurrent_extraction_batches`. `claims` is still built
    by iterating `batches` (a fixed, already-known sequence) in order,
    never by appending inside a concurrently-run task body -- the same
    determinism discipline `_retrieve_sources` above uses."""
    query_by_topic = {q.topic: q for q in plan.queries}
    retained = sources[: budget.max_extraction_calls]
    source_by_id = {s.source_id: s for s in retained}

    requests: list[ExtractionRequest] = []
    for source in retained:
        target_dims = query_by_topic.get(source.discovered_by_topic)
        requests.append(ExtractionRequest(
            source=source,
            target_dimensions=target_dims.target_dimensions if target_dims else (),
            company_name=company_name,
        ))

    batches = list(_chunk(requests, max(1, budget.max_sources_per_batch)))

    def _extract_one_batch(batch: list[ExtractionRequest]):
        return extract_many(evidence_extractor, tuple(batch), max_attempts=1 + budget.max_extraction_retries)

    extraction_tasks = {
        f"b{i}": (lambda b=batch: _extract_one_batch(b))
        for i, batch in enumerate(batches)
    }
    extraction_outcomes = run_concurrently_with_containment(
        extraction_tasks, max_workers=budget.max_concurrent_extraction_batches,
    )

    claims: list[Claim] = []
    routing_records: list[ClaimRoutingRecord] = []
    accepted_count = 0
    rejected_count = 0

    for i, batch in enumerate(batches):
        outcome = extraction_outcomes[f"b{i}"]
        if not outcome.ok:
            for request in batch:
                quality_findings.append(AcquisitionQualityFinding(
                    stage="evidence_extraction", topic=request.source.discovered_by_topic,
                    description=f"extraction raised for source {request.source.url!r}: {outcome.error}",
                ))
            continue

        accepted_by_source, rejected_by_source, errors_by_source, _attempts = outcome.value
        for request in batch:
            sid = request.source.source_id
            if sid in errors_by_source:
                quality_findings.append(AcquisitionQualityFinding(
                    stage="evidence_extraction", topic=request.source.discovered_by_topic,
                    description=f"extraction raised for source {request.source.url!r}: {errors_by_source[sid]}",
                ))
                continue
            accepted = accepted_by_source.get(sid, ())
            rejected = rejected_by_source.get(sid, ())
            accepted_count += len(accepted)
            rejected_count += len(rejected)
            if rejected and not accepted:
                quality_findings.append(AcquisitionQualityFinding(
                    stage="evidence_extraction", topic=request.source.discovered_by_topic,
                    description=f"all {len(rejected)} candidate(s) from {request.source.url!r} "
                                f"rejected on grounding validation",
                ))
            for candidate in accepted:
                claim = finalize_claim(candidate, source_by_id[sid], company_ref)
                claims.append(claim)
                # Task 25 item 9: pair this candidate's own routing/
                # relevance decision (already computed by extraction.py::
                # _sanitize_assessment_criteria(), attached to the
                # ACCEPTED candidate before finalize_claim ever ran) with
                # the claim_id finalize_claim() just produced -- this is
                # the one place both are available together, so no
                # signature change to finalize_claim() itself was needed.
                if candidate.routing_decision is not None:
                    routing_records.append(ClaimRoutingRecord(claim_id=claim.claim_id, decision=candidate.routing_decision))

    return claims, accepted_count, rejected_count, routing_records


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
    claims, accepted_count, rejected_count, routing_records = _extract_claims(
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

    # Item 19: drain whatever real ExternalCallRecords the providers
    # logged (a real providers_live.py adapter populates these; every
    # fake in fakes.py populates none, so this is `()` for every offline
    # test -- an honest reflection of "no real external call happened").
    external_calls: tuple[ExternalCallRecord, ...] = (
        drain_call_log(search_provider) + drain_call_log(source_retriever) + drain_call_log(evidence_extractor)
    )

    telemetry = AcquisitionTelemetry(
        run_id=run_id, company_ref=company_ref, started_at=started_at, stages=tuple(stages),
        external_calls=external_calls,
        queries_issued=queries_issued, sources_retrieved=len(sources),
        claims_extracted=accepted_count, claims_rejected=rejected_count,
        claims_deduplicated=deduplicated_count, claims_disputed=disputed_count,
        quality_findings=tuple(quality_findings),
        claim_routing=tuple(routing_records),
    )

    return AcquisitionResult(
        company_ref=company_ref, ledger=ledger, full_analysis=analysis,
        telemetry=telemetry, rejected_count=rejected_count,
    )
