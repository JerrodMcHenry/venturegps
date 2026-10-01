"""
Task 31 item 6 -- the Evidence Engine v1 production adapter.

The ONE place application code translates a product-level request into
`app.evidence_engine.acquisition.models.CompanyAnalysisInput` and invokes
the exact, tested acquisition pipeline
(`app.evidence_engine.acquisition.pipeline.run_acquisition_pipeline`)
with the exact, tested production providers
(`app.evidence_engine.acquisition.providers_live`). This module does NOT
reimplement, copy, or bypass any methodology logic -- it calls the real
pipeline and returns its real, unmodified output, serialized for
persistence. Canonicalization, semantic-fit validation, routing,
provenance, cross-pillar audit, and company aggregation are the pipeline's
own job; nothing here duplicates or second-guesses any of it.

`app.evidence_engine` itself never imports anything from this module (or
from any other legacy/product code) -- confirmed by
`app.evidence_engine.tests.test_isolation_boundary`, unaffected by this
file's existence, which lives outside `app/evidence_engine/` precisely so
that boundary stays intact. This module is the one direction the
dependency is allowed to run: product code -> evidence_engine, never the
reverse.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app.evidence_engine.acquisition.models import AcquisitionBudget, CompanyAnalysisInput
from app.evidence_engine.acquisition.pipeline import AcquisitionResult, run_acquisition_pipeline
from app.evidence_engine.acquisition.providers_live import (
    HttpSourceRetriever,
    OpenAIEvidenceExtractor,
    TavilySearchProvider,
)


class EvidenceV1AdapterError(Exception):
    """Raised for any failure in the adapter's own setup (e.g. a missing
    provider credential) -- distinct from an exception the pipeline
    itself raises, so the service layer (app/evidence_v1/service.py) can
    map each to its own clear, non-leaking user-facing message (item 15)."""


@dataclass(frozen=True)
class EvidenceV1RunResult:
    """What the adapter hands back to the service layer -- everything the
    persistence/report layers need, already a plain, JSON-serializable
    shape (no pipeline-internal Pydantic/dataclass objects escape this
    module). `raw_result` is kept only for the same-request response
    build; it is never itself persisted."""

    company_ref: str
    stage: str
    as_of: str
    generated_at: str
    total_claims_in_ledger: int
    rejected_count: int
    accepted_claims: list[dict]
    pillar_results: list[dict]
    company_coverage_pct: float | None
    company_confidence: str | None
    company_publishable: bool
    company_withhold_reasons: list[str]
    cross_pillar_audit: list[dict]
    telemetry: dict
    wall_clock_seconds: float


def _require_provider_credentials() -> None:
    """Fails closed, BEFORE any pipeline/provider object is constructed,
    with a specific, actionable message -- item 15's own 'missing
    provider keys' error case. `OpenAIEvidenceExtractor`/
    `TavilySearchProvider` read their own keys from the environment
    lazily (via the openai/tavily SDKs); checking here means a
    misconfigured server fails the SAME way every time, not once a
    real acquisition run is already partway through."""
    import os

    missing = [name for name in ("OPENAI_API_KEY", "TAVILY_API_KEY") if not os.environ.get(name)]
    if missing:
        raise EvidenceV1AdapterError(
            f"Evidence Engine v1 is not configured: missing {', '.join(missing)}."
        )


def _claim_to_dict(claim) -> dict:
    return {
        "claim_id": claim.claim_id,
        "claim_text": claim.claim_text,
        "subject_entity": claim.subject_entity,
        "source_url": claim.source_url,
        "source_publisher": claim.source_publisher,
        "source_type": claim.source_type.value,
        "published_at": claim.published_at.isoformat() if claim.published_at else None,
        "retrieved_at": claim.retrieved_at.isoformat(),
        "support_status": claim.support_status.value,
        "excerpt": claim.excerpt,
        "assessment_criteria": list(claim.assessment_criteria),
        "independence_group_id": claim.independence_group_id,
        "structured_fact": claim.structured_fact,
    }


def _dimension_to_dict(dr) -> dict:
    return {
        "dimension": dr.dimension,
        "category": dr.category.value,
        "weight": dr.weight,
        "score": dr.score,
        "availability": dr.availability.value,
        "supporting_claim_ids": list(dr.supporting_claim_ids),
        "confidence": dr.confidence.value,
        "rationale": dr.rationale,
        "classification_label": dr.classification_label,
    }


def _pillar_to_dict(pr) -> dict:
    return {
        "pillar": pr.pillar,
        "strength": pr.strength,
        "coverage_pct": pr.coverage_pct,
        "confidence": pr.confidence.value,
        "publishable": pr.publishable,
        "withhold_reasons": list(pr.withhold_reasons),
        "dimension_results": [_dimension_to_dict(dr) for dr in pr.dimension_results],
    }


def _audit_finding_to_dict(f) -> dict:
    return {
        "finding_type": f.finding_type.value,
        "severity": f.severity.value,
        "description": f.description,
        "related_claim_ids": list(f.related_claim_ids),
        "related_pillars": list(f.related_pillars),
        "related_dimensions": list(f.related_dimensions),
    }


def _telemetry_to_dict(t) -> dict:
    return {
        "run_id": t.run_id,
        "company_ref": t.company_ref,
        "started_at": t.started_at.isoformat(),
        "queries_issued": t.queries_issued,
        "sources_retrieved": t.sources_retrieved,
        "claims_extracted": t.claims_extracted,
        "claims_rejected": t.claims_rejected,
        "claims_deduplicated": t.claims_deduplicated,
        "claims_disputed": t.claims_disputed,
        "total_duration_seconds": t.total_duration_seconds,
        "total_external_calls": t.total_external_calls,
        "total_extraction_tokens": t.total_extraction_tokens,
        "total_extraction_input_tokens": t.total_extraction_input_tokens,
        "total_extraction_output_tokens": t.total_extraction_output_tokens,
        "total_extraction_provider_attempts": t.total_extraction_provider_attempts,
        "total_extraction_validation_retries": t.total_extraction_validation_retries,
        "extraction_batches_with_input_truncation": t.extraction_batches_with_input_truncation,
        "extraction_batches_with_output_truncation": t.extraction_batches_with_output_truncation,
        "total_sources_excluded_for_budget": t.total_sources_excluded_for_budget,
        "quality_findings": [
            {"stage": qf.stage, "description": qf.description, "topic": qf.topic}
            for qf in t.quality_findings
        ],
        "claim_routing": [
            {
                "claim_id": r.claim_id,
                "status": r.decision.status,
                "reason": r.decision.reason,
                "fact_kind": r.decision.fact_kind,
                "final_criteria": list(r.decision.final_criteria),
                "semantic_fit_status": r.decision.semantic_fit_status,
            }
            for r in t.claim_routing
        ],
    }


def run_evidence_v1_analysis(
    company_name: str, website_url: str, as_of: date | None = None,
) -> EvidenceV1RunResult:
    """The adapter's one public function. Constructs the real production
    providers, runs the real, unmodified acquisition pipeline exactly
    once, and returns a plain, JSON-serializable result. Raises
    `EvidenceV1AdapterError` for a configuration problem (missing
    credentials) and lets any exception the pipeline itself raises
    (a provider failure the pipeline's own error containment did not
    absorb) propagate unchanged -- the service layer (item 15) maps
    both to distinct, user-facing messages; this module never catches
    broadly and never silently degrades into a fabricated result."""
    _require_provider_credentials()

    company_input = CompanyAnalysisInput(company_name=company_name, website_url=website_url, as_of=as_of)
    budget = AcquisitionBudget()  # unchanged production defaults -- see docs/architecture/EVIDENCE_ENGINE_PRODUCT_INTEGRATION.md

    search_provider = TavilySearchProvider()
    source_retriever = HttpSourceRetriever(company_website_url=website_url)
    evidence_extractor = OpenAIEvidenceExtractor()

    t0 = time.monotonic()
    result: AcquisitionResult = run_acquisition_pipeline(
        company_input, search_provider, source_retriever, evidence_extractor, budget=budget,
    )
    wall_clock_seconds = time.monotonic() - t0

    full_analysis = result.full_analysis

    return EvidenceV1RunResult(
        company_ref=result.company_ref,
        stage=full_analysis.stage.value,
        as_of=full_analysis.as_of.isoformat(),
        generated_at=full_analysis.generated_at.isoformat(),
        total_claims_in_ledger=full_analysis.total_claims_in_ledger,
        rejected_count=result.rejected_count,
        accepted_claims=[_claim_to_dict(c) for c in result.ledger.claims],
        pillar_results=[_pillar_to_dict(pr) for pr in full_analysis.pillar_results],
        company_coverage_pct=full_analysis.company_coverage_pct,
        company_confidence=full_analysis.company_confidence.value if full_analysis.company_confidence else None,
        company_publishable=full_analysis.company_publishable,
        company_withhold_reasons=list(full_analysis.company_withhold_reasons),
        cross_pillar_audit=[_audit_finding_to_dict(f) for f in full_analysis.cross_pillar_audit],
        telemetry=_telemetry_to_dict(result.telemetry),
        wall_clock_seconds=wall_clock_seconds,
    )
