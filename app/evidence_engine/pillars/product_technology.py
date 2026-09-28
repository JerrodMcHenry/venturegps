"""
Product & Technology pillar (NEW_ENGINE_SPEC.md Part 3.3). Task 9
calibration pass: dimension evaluation goes through the schema-
constrained AI classification/extraction interface
(app.evidence_engine.classification) instead of inspecting claims
directly, and is stage-aware (app.evidence_engine.stage). Task 10 adds
retry-with-validation-feedback (classify_with_recovery/
extract_with_recovery) before failing a dimension closed.

The `WellBehaved*` classes below are the DEFAULT models used everywhere
in this codebase -- deterministic, rule-based, and used specifically
because this engine must make no paid AI call. They are a faithful stand-
in for what a real, schema-constrained LLM call should return given
already-structured evidence, and they conform to exactly the same
Protocol a real model would (ClassificationModel / ExtractionModel) --
swapping one in for the other requires no change to the evaluator
functions below. Notably, none of them reads `EvidenceItem.redacted_text`
at all; they classify only from each item's already-typed
source_type/support_status/independence_group_id. This is deliberate: it
is what makes both identity-blindness (Design Principle 10) and
prompt-injection resistance (see tests/test_adversarial_robustness.py)
structural properties of this implementation rather than instructions a
model might or might not follow. Deliberately malicious models that DO
try to act on injected text, or that fabricate favorable labels/
citations, live in tests/test_adversarial_robustness.py and are used
specifically to prove `validate_classification`/`validate_extraction`
reject them regardless.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.evidence_engine import parameters as P
from app.evidence_engine.classification import (
    ClassificationModel,
    ClassificationRequest,
    ClassificationResponse,
    ExtractionModel,
    ExtractionRequest,
    ExtractionResponse,
    classify_with_recovery,
    extract_with_recovery,
    requires_independent_source,
    requires_minimum_distinct_facts,
    to_evidence_items,
)
from app.evidence_engine.confidence import compute_dimension_confidence
from app.evidence_engine.ledger import DimensionEvidence, EvidenceLedger, resolve_dimension_evidence
from app.evidence_engine.models import INDEPENDENT_SOURCE_TYPES, SourceType
from app.evidence_engine.scoring import (
    AvailabilityStatus,
    ConfidenceLevel,
    DimensionCategory,
    DimensionResult,
    PillarGateParameters,
    PillarResult,
    evaluate_pillar,
)
from app.evidence_engine.stage import ALL_TIERS, Stage, tier_for_stage

PILLAR = P.PRODUCT_TECHNOLOGY_PILLAR

DIMENSION_PRODUCT_EXISTENCE = "product_existence_maturity"
DIMENSION_DIFFERENTIATION = "differentiation_claim_corroboration"
DIMENSION_TECHNICAL_DEPTH = "technical_depth_signal"
DIMENSION_DEFENSIBILITY = "defensibility_signal"

_OBSERVABLE_SOURCE_TYPES = frozenset(
    {SourceType.PRODUCT_DOCUMENTATION, SourceType.INDEPENDENT_REPORTING, SourceType.AGGREGATOR_OR_DIRECTORY}
)


def _company_claims(ledger: EvidenceLedger, company_ref: str) -> EvidenceLedger:
    return EvidenceLedger.from_list([c for c in ledger.claims if c.company_ref == company_ref])


def _reason_for_absence(evidence: DimensionEvidence) -> AvailabilityStatus:
    if evidence.disputed and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_DISPUTED
    if evidence.stale and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_STALE
    return AvailabilityStatus.UNSCORED_NO_EVIDENCE


def _score_for_label(label_table: dict[str, dict[str, float]], label: str, stage: Stage) -> float | None:
    """spec Part 4.2/4.3: stage-indexed lookup, most-permissive band when
    stage is Undetermined. This pillar's tables (parameters.py) are all
    monotonically descending early > growth > established, so "most
    permissive" is always the maximum across tiers -- asserted, not
    assumed, by test_stage_aware_evaluation.py."""
    tier_scores = label_table.get(label)
    if tier_scores is None:
        return None
    if stage == Stage.UNDETERMINED:
        return max(tier_scores.values())
    tier = tier_for_stage(stage)
    if tier is None:
        return max(tier_scores.values())
    return tier_scores[tier.value]


# --- 1. Product Existence & Maturity (Computed, via extraction interface) ---

@dataclass(frozen=True)
class WellBehavedProductExistenceExtractor:
    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        observable = tuple(
            e.claim_id for e in request.evidence_items if e.source_type in _OBSERVABLE_SOURCE_TYPES
        )
        if observable:
            return ExtractionResponse(artifact_observed=True, supporting_claim_ids=observable)
        return ExtractionResponse(artifact_observed=False, supporting_claim_ids=())


_DEFAULT_PRODUCT_EXISTENCE_MODEL = WellBehavedProductExistenceExtractor()


def evaluate_product_existence_maturity(
    ledger: EvidenceLedger,
    company_ref: str,
    as_of: date,
    stage: Stage,
    company_display_names: tuple[str, ...] = (),
    model: ExtractionModel | None = None,
) -> DimensionResult:
    model = model or _DEFAULT_PRODUCT_EXISTENCE_MODEL
    weight = P.PRODUCT_TECHNOLOGY_DIMENSION_WEIGHTS[DIMENSION_PRODUCT_EXISTENCE]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(
        scoped, DIMENSION_PRODUCT_EXISTENCE, as_of,
        P.PRODUCT_TECHNOLOGY_STALENESS_DAYS[DIMENSION_PRODUCT_EXISTENCE],
    )

    if not evidence.all_tagged:
        return DimensionResult(
            dimension=DIMENSION_PRODUCT_EXISTENCE, pillar=PILLAR,
            category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            rationale="No claim is on record for this dimension.",
        )
    if not evidence.admissible:
        return DimensionResult(
            dimension=DIMENSION_PRODUCT_EXISTENCE, pillar=PILLAR,
            category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=_reason_for_absence(evidence),
            rationale="No admissible (non-stale, non-disputed) claim is on record.",
        )

    request = ExtractionRequest(
        dimension=DIMENSION_PRODUCT_EXISTENCE,
        evidence_items=to_evidence_items(evidence.admissible, company_display_names),
    )
    try:
        outcome = extract_with_recovery(model, request, evidence)
    except Exception as exc:  # noqa: BLE001 -- a failing model call must never crash the analysis
        return DimensionResult(
            dimension=DIMENSION_PRODUCT_EXISTENCE, pillar=PILLAR,
            category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_EXTRACTION_FAILED,
            rationale=f"Extraction call raised an exception: {exc}",
        )

    if outcome.response is None:
        # Task 10, item 2: already retried once with validation feedback
        # (extract_with_recovery) -- still invalid on the second attempt,
        # so this fails closed. Never a fabricated fallback, never an
        # unsupported citation accepted.
        return DimensionResult(
            dimension=DIMENSION_PRODUCT_EXISTENCE, pillar=PILLAR,
            category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_EXTRACTION_FAILED,
            rationale=(
                f"Rejected extraction response after {outcome.attempts} attempt(s): "
                + "; ".join(outcome.violations)
            ),
        )

    response = outcome.response
    if not response.artifact_observed:
        # Admissible evidence exists (e.g. a bare company disclosure) but
        # none of it is an independently observable artifact -- distinct
        # from "no evidence at all" (spec Part 3.1's fabricated/unsupported
        # claim resistance).
        return DimensionResult(
            dimension=DIMENSION_PRODUCT_EXISTENCE, pillar=PILLAR,
            category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
            rationale="Only an unverifiable company assertion is on record; no independently observable artifact.",
        )

    cited = tuple(c for c in evidence.admissible if c.claim_id in response.supporting_claim_ids)
    rationale = "A directly observable, independently-checkable product artifact is admissible."
    if outcome.recovered:
        rationale += " (accepted on retry, after validation feedback on the first attempt)"
    return DimensionResult(
        dimension=DIMENSION_PRODUCT_EXISTENCE, pillar=PILLAR,
        category=DimensionCategory.COMPUTED, weight=weight,
        score=P.PRODUCT_EXISTENCE_SCORE, availability=AvailabilityStatus.SCORABLE,
        supporting_claim_ids=response.supporting_claim_ids,
        confidence=compute_dimension_confidence(cited),
        rationale=rationale,
    )


# --- Shared Classified-dimension evaluation ---------------------------------

def _evaluate_classified_dimension(
    *,
    ledger: EvidenceLedger,
    company_ref: str,
    as_of: date,
    stage: Stage,
    dimension: str,
    allowed_labels: tuple[str, ...],
    unscored_label_reasons: dict[str, AvailabilityStatus],
    label_table: dict[str, dict[str, float]],
    label_requirement_check,
    model: ClassificationModel,
    company_display_names: tuple[str, ...],
) -> DimensionResult:
    weight = P.PRODUCT_TECHNOLOGY_DIMENSION_WEIGHTS[dimension]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(scoped, dimension, as_of, P.PRODUCT_TECHNOLOGY_STALENESS_DAYS[dimension])

    if evidence.disputed and not evidence.admissible:
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_DISPUTED,
            classification_label="DISPUTED",
            rationale="Conflicting claims exist for this dimension and remain unresolved.",
        )

    if evidence.stale and not evidence.admissible:
        # Task 12, item 3 (fixing a real error NEW_ENGINE_LIVE_EVALUATION.md
        # §4.2 found): previously, a Classified dimension with nothing
        # admissible would fall through to the classifier, which would
        # correctly see zero evidence_items and propose a "nothing here"
        # label -- but the resulting availability was always
        # UNSCORED_NO_EVIDENCE, identical to a genuine, real absence of
        # evidence, even when the ledger's own `evidence.stale` already
        # knew better. This mirrors the Computed dimension evaluator's own
        # pre-existing `_reason_for_absence` check, made explicit here too
        # rather than left implicit in the classifier's response.
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_STALE,
            rationale=(
                f"All evidence tagged for this dimension is older than its "
                f"{P.PRODUCT_TECHNOLOGY_STALENESS_DAYS[dimension]}-day staleness bound; none is currently admissible."
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
        # Task 10, item 2: already retried once with validation feedback
        # (classify_with_recovery) -- still invalid on the second attempt.
        # Fails closed: never a substituted score, never an accepted
        # unsupported citation.
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_EXTRACTION_FAILED,
            rationale=(
                f"Rejected classification response after {outcome.attempts} attempt(s): "
                + "; ".join(outcome.violations)
            ),
        )

    response = outcome.response
    score = _score_for_label(label_table, response.label, stage)
    if score is None:
        reason = unscored_label_reasons.get(response.label, AvailabilityStatus.UNSCORED_NO_EVIDENCE)
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=reason, classification_label=response.label,
            rationale=f"Classified as {response.label!r}, which does not score this dimension.",
        )

    cited = tuple(c for c in evidence.admissible if c.claim_id in response.supporting_claim_ids)
    rationale = f"Classified as {response.label!r}, scored via the stage-indexed lookup table (stage={stage.value})."
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


# --- 2. Differentiation Claim Corroboration ---------------------------------

@dataclass(frozen=True)
class WellBehavedDifferentiationClassifier:
    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        if not request.evidence_items:
            return ClassificationResponse(label="NONE_DISCLOSED", supporting_claim_ids=())
        independent = tuple(e.claim_id for e in request.evidence_items if e.source_type in INDEPENDENT_SOURCE_TYPES)
        if independent:
            return ClassificationResponse(label="CORROBORATED", supporting_claim_ids=independent)
        return ClassificationResponse(
            label="UNCORROBORATED", supporting_claim_ids=tuple(e.claim_id for e in request.evidence_items)
        )


_DEFAULT_DIFFERENTIATION_MODEL = WellBehavedDifferentiationClassifier()
_DIFFERENTIATION_REQUIREMENT = requires_independent_source(frozenset({"CORROBORATED"}))


def evaluate_differentiation_claim_corroboration(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_DIFFERENTIATION,
        allowed_labels=("NONE_DISCLOSED", "UNCORROBORATED", "CORROBORATED"),
        unscored_label_reasons={
            "NONE_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            "UNCORROBORATED": AvailabilityStatus.UNSCORED_UNCORROBORATED,
        },
        label_table=P.DIFFERENTIATION_LABEL_SCORES,
        label_requirement_check=_DIFFERENTIATION_REQUIREMENT,
        model=model or _DEFAULT_DIFFERENTIATION_MODEL,
        company_display_names=company_display_names,
    )


# --- 3. Technical Depth Signal -----------------------------------------------

@dataclass(frozen=True)
class WellBehavedTechnicalDepthClassifier:
    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        if not request.evidence_items:
            return ClassificationResponse(label="NONE", supporting_claim_ids=())
        representative_by_group: dict[str, str] = {}
        for item in request.evidence_items:
            representative_by_group.setdefault(item.independence_group_id, item.claim_id)
        distinct = len(representative_by_group)
        cited = tuple(representative_by_group.values())
        if distinct >= P.TECHNICAL_DEPTH_SUBSTANTIAL_MIN_FACTS:
            return ClassificationResponse(label="SUBSTANTIAL", supporting_claim_ids=cited)
        if distinct >= P.TECHNICAL_DEPTH_SOME_MIN_FACTS:
            return ClassificationResponse(label="SOME", supporting_claim_ids=cited)
        return ClassificationResponse(label="NONE", supporting_claim_ids=())


_DEFAULT_TECHNICAL_DEPTH_MODEL = WellBehavedTechnicalDepthClassifier()
_TECHNICAL_DEPTH_REQUIREMENT = requires_minimum_distinct_facts(
    {"SUBSTANTIAL": P.TECHNICAL_DEPTH_SUBSTANTIAL_MIN_FACTS, "SOME": P.TECHNICAL_DEPTH_SOME_MIN_FACTS}
)


def evaluate_technical_depth_signal(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_TECHNICAL_DEPTH,
        allowed_labels=("NONE", "SOME", "SUBSTANTIAL"),
        unscored_label_reasons={"NONE": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        label_table=P.TECHNICAL_DEPTH_LABEL_SCORES,
        label_requirement_check=_TECHNICAL_DEPTH_REQUIREMENT,
        model=model or _DEFAULT_TECHNICAL_DEPTH_MODEL,
        company_display_names=company_display_names,
    )


# --- 4. Defensibility Signal -------------------------------------------------

@dataclass(frozen=True)
class WellBehavedDefensibilityClassifier:
    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        if not request.evidence_items:
            return ClassificationResponse(label="NONE_DISCLOSED", supporting_claim_ids=())
        independent = tuple(e.claim_id for e in request.evidence_items if e.source_type in INDEPENDENT_SOURCE_TYPES)
        if independent:
            return ClassificationResponse(label="CORROBORATED_MOAT", supporting_claim_ids=independent)
        return ClassificationResponse(
            label="UNCORROBORATED_CLAIM", supporting_claim_ids=tuple(e.claim_id for e in request.evidence_items)
        )


_DEFAULT_DEFENSIBILITY_MODEL = WellBehavedDefensibilityClassifier()
_DEFENSIBILITY_REQUIREMENT = requires_independent_source(frozenset({"CORROBORATED_MOAT"}))


def evaluate_defensibility_signal(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_DEFENSIBILITY,
        allowed_labels=("NONE_DISCLOSED", "UNCORROBORATED_CLAIM", "CORROBORATED_MOAT"),
        unscored_label_reasons={
            "NONE_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            "UNCORROBORATED_CLAIM": AvailabilityStatus.UNSCORED_UNCORROBORATED,
        },
        label_table=P.DEFENSIBILITY_LABEL_SCORES,
        label_requirement_check=_DEFENSIBILITY_REQUIREMENT,
        model=model or _DEFAULT_DEFENSIBILITY_MODEL,
        company_display_names=company_display_names,
    )


# --- Orchestration -----------------------------------------------------------

def evaluate_all(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
    product_existence_model: ExtractionModel | None = None,
    differentiation_model: ClassificationModel | None = None,
    technical_depth_model: ClassificationModel | None = None,
    defensibility_model: ClassificationModel | None = None,
) -> tuple[DimensionResult, ...]:
    return (
        evaluate_product_existence_maturity(
            ledger, company_ref, as_of, stage, company_display_names, product_existence_model
        ),
        evaluate_differentiation_claim_corroboration(
            ledger, company_ref, as_of, stage, company_display_names, differentiation_model
        ),
        evaluate_technical_depth_signal(
            ledger, company_ref, as_of, stage, company_display_names, technical_depth_model
        ),
        evaluate_defensibility_signal(
            ledger, company_ref, as_of, stage, company_display_names, defensibility_model
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
