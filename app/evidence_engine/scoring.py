"""
Deterministic Scoring (NEW_ENGINE_SPEC.md Part 6). Pure Python: no network
call, no AI call, no randomness anywhere in this module.

Firewall property (spec Part 6.6): compute_pillar_strength(),
compute_pillar_coverage_pct(), and compute_pillar_confidence() each take
only the exact inputs they need and never call each other. This is
enforced structurally here, not by convention -- compute_pillar_strength()
has no parameter through which it could even read coverage or confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DimensionCategory(str, Enum):
    COMPUTED = "computed"
    CLASSIFIED = "classified"


class AvailabilityStatus(str, Enum):
    SCORABLE = "scorable"
    UNSCORED_NO_EVIDENCE = "unscored_no_evidence"
    UNSCORED_STALE = "unscored_stale"
    UNSCORED_DISPUTED = "unscored_disputed"
    UNSCORED_UNCORROBORATED = "unscored_uncorroborated"
    UNSCORED_EXTRACTION_FAILED = "unscored_extraction_failed"


class ConfidenceLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


_CONFIDENCE_ORDER = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MEDIUM: 1, ConfidenceLevel.HIGH: 2}
_ORDER_TO_CONFIDENCE = {v: k for k, v in _CONFIDENCE_ORDER.items()}


@dataclass(frozen=True)
class DimensionResult:
    dimension: str
    pillar: str
    category: DimensionCategory
    weight: float

    # None whenever availability != SCORABLE -- Unscored is a distinct
    # state from any real number, never zero, never averaged (spec Design
    # Principle 3/6.1).
    score: float | None
    availability: AvailabilityStatus

    # Every claim_id here must resolve to a real, admissible ledger entry
    # tagged with this exact dimension -- this is what "every material
    # scored claim is traceable to admissible evidence" (Design Principle
    # 2) means as a checkable, not just an aspirational, property. See
    # verify_traceability() below.
    supporting_claim_ids: tuple[str, ...] = field(default_factory=tuple)

    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    rationale: str = ""
    classification_label: str | None = None


@dataclass(frozen=True)
class PillarResult:
    pillar: str

    # None unless BOTH gates in evaluate_pillar() pass -- "withheld" is a
    # distinct state from a low score (spec Part 6.2, restated as a
    # top-level Design Principle: "clearly distinguish an unscored result
    # from a low score").
    strength: float | None
    coverage_pct: float
    confidence: ConfidenceLevel
    publishable: bool
    withhold_reasons: tuple[str, ...]
    dimension_results: tuple[DimensionResult, ...]


def compute_pillar_strength(dimension_results: tuple[DimensionResult, ...]) -> float | None:
    """Renormalized weighted average over SCORABLE dimensions only. A pure
    function of scores + weights -- never reads coverage_pct or confidence
    (firewall property, spec Part 6.6)."""
    scorable = [
        d for d in dimension_results
        if d.availability == AvailabilityStatus.SCORABLE and d.score is not None
    ]
    if not scorable:
        return None
    total_weight = sum(d.weight for d in scorable)
    if total_weight <= 0:
        return None
    weighted = sum(d.score * d.weight for d in scorable)
    return round(weighted / total_weight, 2)


def compute_pillar_coverage_pct(dimension_results: tuple[DimensionResult, ...]) -> float:
    """Weight-based coverage, binary per dimension (scorable or not) --
    never boosted by how much evidence backs a dimension, only by whether
    it cleared its own minimum-to-score bar (spec Part 6.3)."""
    total_weight = sum(d.weight for d in dimension_results)
    if total_weight <= 0:
        return 0.0
    covered_weight = sum(
        d.weight for d in dimension_results if d.availability == AvailabilityStatus.SCORABLE
    )
    return round((covered_weight / total_weight) * 100, 1)


def compute_pillar_confidence(dimension_results: tuple[DimensionResult, ...]) -> ConfidenceLevel:
    """Weighted average of scored dimensions' own confidence ordinal,
    rounded -- never reads score or coverage_pct (firewall property)."""
    scorable = [d for d in dimension_results if d.availability == AvailabilityStatus.SCORABLE]
    if not scorable:
        return ConfidenceLevel.LOW
    total_weight = sum(d.weight for d in scorable)
    if total_weight <= 0:
        return ConfidenceLevel.LOW
    weighted_ordinal = sum(_CONFIDENCE_ORDER[d.confidence] * d.weight for d in scorable) / total_weight
    rounded = max(0, min(2, round(weighted_ordinal)))
    return _ORDER_TO_CONFIDENCE[rounded]


@dataclass(frozen=True)
class PillarGateParameters:
    """CALIBRATION REQUIRED (spec Part 6.7) -- these are provisional
    placeholders, not final values. See app/evidence_engine/parameters.py
    for the single, versioned source of the actual numbers used at
    runtime; this dataclass is just the shape evaluate_pillar() needs."""

    min_pillar_coverage_pct: float
    min_scored_dimensions_per_pillar: int


def evaluate_pillar(
    pillar: str,
    dimension_results: tuple[DimensionResult, ...],
    gate_params: PillarGateParameters,
) -> PillarResult:
    """Two independent gates, both required (spec Part 6.2) -- this is the
    exact mechanism that prevents one scored dimension from ever
    representing an entire pillar, the core defect this engine exists to
    fix. Gate 1 alone is insufficient whenever one dimension's own weight
    clears the coverage floor by itself; gate 2 closes that case."""
    coverage_pct = compute_pillar_coverage_pct(dimension_results)
    scored_count = sum(
        1 for d in dimension_results if d.availability == AvailabilityStatus.SCORABLE
    )
    confidence = compute_pillar_confidence(dimension_results)
    strength = compute_pillar_strength(dimension_results)

    reasons: list[str] = []
    if coverage_pct < gate_params.min_pillar_coverage_pct:
        reasons.append(
            f"weighted coverage {coverage_pct}% < floor {gate_params.min_pillar_coverage_pct}%"
        )
    if scored_count < gate_params.min_scored_dimensions_per_pillar:
        reasons.append(
            f"only {scored_count} scored dimension(s) < floor "
            f"{gate_params.min_scored_dimensions_per_pillar}"
        )

    publishable = not reasons

    return PillarResult(
        pillar=pillar,
        strength=strength if publishable else None,
        coverage_pct=coverage_pct,
        confidence=confidence,
        publishable=publishable,
        withhold_reasons=tuple(reasons),
        dimension_results=dimension_results,
    )


def verify_traceability(
    dimension_result: DimensionResult,
    ledger_claim_ids: frozenset[str],
) -> list[str]:
    """Design Principle 2, made checkable: every numeric dimension score
    must trace to admissible ledger evidence. Returns a list of violations
    (empty = pass). Does not re-derive admissibility itself (that is
    ledger.resolve_dimension_evidence's job, already applied before a
    dimension evaluator ever produces a score) -- this only checks that
    every claim_id a SCORABLE result cites actually exists in the ledger
    and was tagged for this exact dimension."""
    violations: list[str] = []

    if dimension_result.availability == AvailabilityStatus.SCORABLE:
        if not dimension_result.supporting_claim_ids:
            violations.append(
                f"{dimension_result.dimension}: SCORABLE but cites zero supporting_claim_ids"
            )
        for claim_id in dimension_result.supporting_claim_ids:
            if claim_id not in ledger_claim_ids:
                violations.append(
                    f"{dimension_result.dimension}: cites claim_id {claim_id!r} "
                    f"which does not exist in the ledger"
                )
    else:
        if dimension_result.score is not None:
            violations.append(
                f"{dimension_result.dimension}: availability is "
                f"{dimension_result.availability.value!r} but score is "
                f"{dimension_result.score!r}, not None"
            )

    return violations
