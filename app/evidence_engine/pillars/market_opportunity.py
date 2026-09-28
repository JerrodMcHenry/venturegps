"""
Market Opportunity pillar (Task 13; NEW_ENGINE_SPEC.md Part 3.3). The
second pillar implemented in this engine, built on the exact same
architecture Product & Technology already validated (Tasks 8-12):
Evidence Ledger -> admissibility/provenance -> classification (via the
schema-constrained interface, with retry-once recovery) -> deterministic
label->score lookup -> coverage/confidence -> the shared two-gate
publishability rule. No shared-engine module was redesigned to build
this; the one shared-layer extension this pillar needed
(`EvidenceItem.structured_fact`, classification.py) is additive and
documented there and in the Task 13 completion report.

**Pillar boundary (Task 13, item 3) -- read this before touching any
dimension below.** Market Opportunity measures the OPPORTUNITY THE
MARKET REPRESENTS, never whether this specific company has captured it:

  - Customer/revenue adoption, usage, and growth belong to Commercial
    Traction (spec Part 3.1's own double-counting decision), not here.
  - Whether the COMPANY's product is differentiated belongs to Product &
    Technology's Differentiation Claim Corroboration. Competitive
    Landscape Position below asks a different question: what does the
    market's competitive STRUCTURE look like (fragmented vs.
    concentrated), independent of how this company stacks up within it.
  - Team quality, execution, and financial condition belong to their own
    pillars and are never evidence for any dimension here.

Every dimension below is Classified (spec Part 3.3's table lists no
Computed dimension for this pillar) and, per spec Part 3.3's own
"Minimum to score" column, EVERY scoring label requires at least one
INDEPENDENTLY-sourced citation -- a company's own TAM slide or growth
claim is retained in the ledger (never deleted, always auditable) but
can never, by itself, satisfy any dimension's minimum-to-score bar here,
directly implementing Task 13 item 4's instruction to treat claims like
"$50B market" or "massive TAM" as claims requiring evidence, not facts.

**Stage independence (Task 13, item 6) -- deliberate, not an oversight.**
Every label->score table in this module is a flat `dict[str, float]`,
never stage-indexed. Market Opportunity measures a property of the
external market; a real $10B category or a named regulatory catalyst
means the same thing regardless of which company's report happens to
cite it, and a younger company must not receive an easier market score
merely for being younger (the reverse of Product & Technology's own,
deliberately stage-VARYING design, where the same evidence is more
remarkable, and scores higher, for a company at an earlier stage -- that
logic applies to evidence ABOUT THE COMPANY, not evidence about the
market it operates in). `evaluate_pillar_for_company()` below still
accepts a `stage` parameter, purely for calling-convention consistency
with Product & Technology (a future orchestrator calling every pillar
with one shared `determine_stage()` result should not need to special-
case this pillar) -- it is accepted and never consulted, which this
docstring documents as the required reasoning per item 6's own
instruction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.evidence_engine import parameters as P
from app.evidence_engine.classification import (
    ClassificationModel,
    ClassificationRequest,
    ClassificationResponse,
    classify_with_recovery,
    requires_independent_source,
    to_evidence_items,
)
from app.evidence_engine.confidence import compute_dimension_confidence
from app.evidence_engine.ledger import DimensionEvidence, EvidenceLedger, resolve_dimension_evidence
from app.evidence_engine.models import INDEPENDENT_SOURCE_TYPES
from app.evidence_engine.scoring import (
    AvailabilityStatus,
    DimensionCategory,
    DimensionResult,
    PillarGateParameters,
    PillarResult,
    evaluate_pillar,
)
from app.evidence_engine.stage import Stage

PILLAR = P.MARKET_OPPORTUNITY_PILLAR

DIMENSION_MARKET_SIZE = "market_definition_size"
DIMENSION_MARKET_GROWTH = "market_growth_signal"
DIMENSION_TIMING_CATALYST = "timing_catalyst"
DIMENSION_COMPETITIVE_LANDSCAPE = "competitive_landscape_position"


def _company_claims(ledger: EvidenceLedger, company_ref: str) -> EvidenceLedger:
    return EvidenceLedger.from_list([c for c in ledger.claims if c.company_ref == company_ref])


def _reason_for_absence(evidence: DimensionEvidence) -> AvailabilityStatus:
    if evidence.disputed and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_DISPUTED
    if evidence.stale and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_STALE
    return AvailabilityStatus.UNSCORED_NO_EVIDENCE


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        # Never fabricate precision from malformed/unparseable data (Task
        # 13, item 4) -- a structured_fact that doesn't parse is treated
        # as not a usable candidate, not silently coerced to a number.
        return None


# --- Shared per-dimension evaluation harness (this pillar's own private ----
# --- copy of the same pattern pillars/product_technology.py established, --
# --- per Task 13's own "do not redesign shared infra for ordinary pillar- -
# --- specific behavior" instruction -- see the completion report's note --
# --- on this as a candidate for a FUTURE shared extraction, not decided --
# --- here) --------------------------------------------------------------

def _evaluate_classified_dimension(
    *,
    ledger: EvidenceLedger,
    company_ref: str,
    as_of: date,
    dimension: str,
    allowed_labels: tuple[str, ...],
    unscored_label_reasons: dict[str, AvailabilityStatus],
    label_table: dict[str, float],
    label_requirement_check,
    model: ClassificationModel,
    company_display_names: tuple[str, ...],
) -> DimensionResult:
    weight = P.MARKET_OPPORTUNITY_DIMENSION_WEIGHTS[dimension]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(scoped, dimension, as_of, P.MARKET_OPPORTUNITY_STALENESS_DAYS[dimension])

    if evidence.disputed and not evidence.admissible:
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_DISPUTED,
            classification_label="DISPUTED",
            rationale="Conflicting claims exist for this dimension and remain unresolved.",
        )

    if evidence.stale and not evidence.admissible:
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_STALE,
            rationale=(
                f"All evidence tagged for this dimension is older than its "
                f"{P.MARKET_OPPORTUNITY_STALENESS_DAYS[dimension]}-day staleness bound; none is currently admissible."
            ),
        )

    request = ClassificationRequest(
        dimension=dimension, allowed_labels=allowed_labels,
        evidence_items=to_evidence_items(evidence.admissible, company_display_names),
    )
    try:
        outcome = classify_with_recovery(model, request, evidence, label_requirement_check)
    except Exception as exc:  # noqa: BLE001 -- never let a model failure crash the analysis
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_EXTRACTION_FAILED,
            rationale=f"Classification call raised an exception: {exc}",
        )

    if outcome.response is None:
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_EXTRACTION_FAILED,
            rationale=(
                f"Rejected classification response after {outcome.attempts} attempt(s): "
                + "; ".join(outcome.violations)
            ),
        )

    response = outcome.response
    score = label_table.get(response.label)
    if score is None:
        reason = unscored_label_reasons.get(response.label, AvailabilityStatus.UNSCORED_NO_EVIDENCE)
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=reason, classification_label=response.label,
            rationale=f"Classified as {response.label!r}, which does not score this dimension.",
        )

    cited = tuple(c for c in evidence.admissible if c.claim_id in response.supporting_claim_ids)
    rationale = f"Classified as {response.label!r}, scored via the stage-independent lookup table."
    if outcome.recovered:
        rationale += " (accepted on retry, after validation feedback on the first attempt)"
    return DimensionResult(
        dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
        score=score, availability=AvailabilityStatus.SCORABLE,
        supporting_claim_ids=response.supporting_claim_ids,
        classification_label=response.label,
        confidence=compute_dimension_confidence(cited),
        rationale=rationale,
    )


# --- 1. Market Definition & Size ---------------------------------------------

@dataclass(frozen=True)
class WellBehavedMarketSizeClassifier:
    """A deterministic stand-in for a real classification call: reads a
    magnitude cue from `EvidenceItem.structured_fact` (never from parsed
    prose -- see this module's own docstring on why that is a documented,
    narrow interpretation, not a Computed dimension in disguise) and
    buckets it into a closed band. Only independently-sourced candidates
    are considered; among ties, the first in the already claim_id-stable
    admissible order is used (this module does not attempt automatic
    numeric-conflict resolution across disagreeing independent estimates
    -- a real disagreement is still expected to be marked `disputed`
    upstream, the same documented convention used throughout Tasks 10-12)."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        for item in request.evidence_items:
            if item.source_type not in INDEPENDENT_SOURCE_TYPES:
                continue
            if not item.structured_fact or item.structured_fact.get("kind") != "market_size_usd":
                continue
            value = _parse_float(item.structured_fact.get("value"))
            if value is None:
                continue
            if value < P.MARKET_SIZE_NARROW_MAX_USD:
                label = "NARROW"
            elif value < P.MARKET_SIZE_SUBSTANTIAL_MAX_USD:
                label = "SUBSTANTIAL"
            else:
                label = "LARGE"
            return ClassificationResponse(label=label, supporting_claim_ids=(item.claim_id,))
        return ClassificationResponse(label="NOT_DISCLOSED", supporting_claim_ids=())


_DEFAULT_MARKET_SIZE_MODEL = WellBehavedMarketSizeClassifier()
_MARKET_SIZE_REQUIREMENT = requires_independent_source(frozenset({"NARROW", "SUBSTANTIAL", "LARGE"}))


def evaluate_market_definition_size(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    del stage  # intentionally unused -- see module docstring, "Stage independence"
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of,
        dimension=DIMENSION_MARKET_SIZE,
        allowed_labels=("NOT_DISCLOSED", "NARROW", "SUBSTANTIAL", "LARGE"),
        unscored_label_reasons={"NOT_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        label_table=P.MARKET_SIZE_LABEL_SCORES,
        label_requirement_check=_MARKET_SIZE_REQUIREMENT,
        model=model or _DEFAULT_MARKET_SIZE_MODEL,
        company_display_names=company_display_names,
    )


# --- 2. Market Growth Signal --------------------------------------------------

@dataclass(frozen=True)
class WellBehavedMarketGrowthClassifier:
    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        for item in request.evidence_items:
            if item.source_type not in INDEPENDENT_SOURCE_TYPES:
                continue
            if not item.structured_fact or item.structured_fact.get("kind") != "category_growth_rate_pct":
                continue
            value = _parse_float(item.structured_fact.get("value"))
            if value is None:
                continue
            if value < P.MARKET_GROWTH_SLOW_MAX_PCT:
                label = "SLOW"
            elif value < P.MARKET_GROWTH_MODERATE_MAX_PCT:
                label = "MODERATE"
            else:
                label = "FAST"
            return ClassificationResponse(label=label, supporting_claim_ids=(item.claim_id,))
        return ClassificationResponse(label="NOT_DISCLOSED", supporting_claim_ids=())


_DEFAULT_MARKET_GROWTH_MODEL = WellBehavedMarketGrowthClassifier()
_MARKET_GROWTH_REQUIREMENT = requires_independent_source(frozenset({"SLOW", "MODERATE", "FAST"}))


def evaluate_market_growth_signal(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    del stage  # intentionally unused -- see module docstring, "Stage independence"
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of,
        dimension=DIMENSION_MARKET_GROWTH,
        allowed_labels=("NOT_DISCLOSED", "SLOW", "MODERATE", "FAST"),
        unscored_label_reasons={"NOT_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        label_table=P.MARKET_GROWTH_LABEL_SCORES,
        label_requirement_check=_MARKET_GROWTH_REQUIREMENT,
        model=model or _DEFAULT_MARKET_GROWTH_MODEL,
        company_display_names=company_display_names,
    )


# --- 3. Timing & Catalyst -----------------------------------------------------

@dataclass(frozen=True)
class WellBehavedTimingCatalystClassifier:
    """Distinguishes a named, specific, independently-reported catalyst
    from generic hype language ("fast-growing industry," "huge
    opportunity") -- Task 13, item 4's own explicit example of a claim
    that must not be treated as evidence. The specificity signal is,
    again, `structured_fact` (kind="catalyst_name") -- the mock's stand-in
    for "the AI actually named a concrete, checkable catalyst" rather than
    parsing prose for adjectives."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        independent = [e for e in request.evidence_items if e.source_type in INDEPENDENT_SOURCE_TYPES]
        if not independent:
            return ClassificationResponse(label="NONE_DISCLOSED", supporting_claim_ids=())
        for item in independent:
            if item.structured_fact and item.structured_fact.get("kind") == "catalyst_name":
                return ClassificationResponse(label="SPECIFIC_CATALYST", supporting_claim_ids=(item.claim_id,))
        return ClassificationResponse(
            label="GENERIC_ONLY", supporting_claim_ids=tuple(e.claim_id for e in independent)
        )


_DEFAULT_TIMING_CATALYST_MODEL = WellBehavedTimingCatalystClassifier()
_TIMING_CATALYST_REQUIREMENT = requires_independent_source(frozenset({"SPECIFIC_CATALYST"}))


def evaluate_timing_catalyst(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    del stage  # intentionally unused -- see module docstring, "Stage independence"
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of,
        dimension=DIMENSION_TIMING_CATALYST,
        allowed_labels=("NONE_DISCLOSED", "GENERIC_ONLY", "SPECIFIC_CATALYST"),
        unscored_label_reasons={
            "NONE_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            "GENERIC_ONLY": AvailabilityStatus.UNSCORED_UNCORROBORATED,
        },
        label_table=P.TIMING_CATALYST_LABEL_SCORES,
        label_requirement_check=_TIMING_CATALYST_REQUIREMENT,
        model=model or _DEFAULT_TIMING_CATALYST_MODEL,
        company_display_names=company_display_names,
    )


# --- 4. Competitive Landscape Position ----------------------------------------

@dataclass(frozen=True)
class WellBehavedCompetitiveLandscapeClassifier:
    """Reads the MARKET's competitive structure (fragmented vs.
    concentrated), never a company-vs-competitor comparison -- that
    question is Product & Technology's Differentiation Claim
    Corroboration, not this dimension (module docstring, "Pillar
    boundary"). `structured_fact` (kind="competitive_structure") stands in
    for an independent analyst's own structural read; a bare mention of
    named competitors with no independent structural characterization is
    deliberately NOT_ESTABLISHED, not guessed in either direction."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        independent = [e for e in request.evidence_items if e.source_type in INDEPENDENT_SOURCE_TYPES]
        for item in independent:
            if not item.structured_fact or item.structured_fact.get("kind") != "competitive_structure":
                continue
            value = (item.structured_fact.get("value") or "").strip().lower()
            if value == "fragmented":
                return ClassificationResponse(label="FRAGMENTED", supporting_claim_ids=(item.claim_id,))
            if value == "concentrated":
                return ClassificationResponse(label="CONCENTRATED", supporting_claim_ids=(item.claim_id,))
        return ClassificationResponse(label="NOT_ESTABLISHED", supporting_claim_ids=())


_DEFAULT_COMPETITIVE_LANDSCAPE_MODEL = WellBehavedCompetitiveLandscapeClassifier()
_COMPETITIVE_LANDSCAPE_REQUIREMENT = requires_independent_source(frozenset({"FRAGMENTED", "CONCENTRATED"}))


def evaluate_competitive_landscape_position(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    del stage  # intentionally unused -- see module docstring, "Stage independence"
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of,
        dimension=DIMENSION_COMPETITIVE_LANDSCAPE,
        allowed_labels=("NOT_ESTABLISHED", "FRAGMENTED", "CONCENTRATED"),
        unscored_label_reasons={"NOT_ESTABLISHED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        label_table=P.COMPETITIVE_LANDSCAPE_LABEL_SCORES,
        label_requirement_check=_COMPETITIVE_LANDSCAPE_REQUIREMENT,
        model=model or _DEFAULT_COMPETITIVE_LANDSCAPE_MODEL,
        company_display_names=company_display_names,
    )


# --- Orchestration -----------------------------------------------------------

def evaluate_all(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
    market_size_model: ClassificationModel | None = None,
    market_growth_model: ClassificationModel | None = None,
    timing_catalyst_model: ClassificationModel | None = None,
    competitive_landscape_model: ClassificationModel | None = None,
) -> tuple[DimensionResult, ...]:
    return (
        evaluate_market_definition_size(ledger, company_ref, as_of, stage, company_display_names, market_size_model),
        evaluate_market_growth_signal(ledger, company_ref, as_of, stage, company_display_names, market_growth_model),
        evaluate_timing_catalyst(ledger, company_ref, as_of, stage, company_display_names, timing_catalyst_model),
        evaluate_competitive_landscape_position(
            ledger, company_ref, as_of, stage, company_display_names, competitive_landscape_model
        ),
    )


def evaluate_pillar_for_company(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), **model_overrides,
) -> PillarResult:
    dimension_results = evaluate_all(ledger, company_ref, as_of, stage, company_display_names, **model_overrides)
    gate_params = PillarGateParameters(
        min_pillar_coverage_pct=P.MIN_PILLAR_COVERAGE_PCT,
        min_scored_dimensions_per_pillar=P.MIN_SCORED_DIMENSIONS_PER_PILLAR,
    )
    return evaluate_pillar(PILLAR, dimension_results, gate_params)
