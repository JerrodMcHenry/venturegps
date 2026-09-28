"""
Commercial Traction pillar (Task 15; NEW_ENGINE_SPEC.md Part 3.3). The
fourth pillar implemented in this engine, on the exact same architecture
Product & Technology, Market Opportunity, and Team & Leadership already
validated (Tasks 8-14). No shared scoring philosophy, evidence ledger,
classification system, provenance system, confidence model, stage model,
or publication gate was redesigned to build this.

**The one rule that overrides every other consideration in this module:
unknown private metrics are not evidence of weak traction.** Revenue,
retention, customer count, growth and similar metrics are routinely
unavailable for private companies -- that absence must remain Unscored,
never converted into a mediocre or negative score. Concretely, and
non-negotiably:

  - Every dimension below fails closed to `Unscored` (never zero, never a
    below-average number, never a fabricated estimate) the moment its own
    minimum-to-score bar (spec Part 3.3) is not cleared. There is no code
    path in this module that turns "no evidence" into any numeric score.
  - Absence of disclosure affects `coverage`/`confidence` only -- Strength
    (`scoring.py::compute_pillar_strength`) is a renormalized average over
    only the SCORABLE dimensions (the shared, unmodified firewall
    property), so an unscored dimension is excluded from the average
    entirely, never averaged in as a low number.
  - Stage-tiering (documented per dimension below) changes which SCORE a
    band that already cleared its own evidence bar receives -- it never
    lowers that bar, and an early-stage company with zero documented
    traction still receives zero scored dimensions, exactly like a company
    at any other stage with zero evidence. Stage sensitivity adjusts
    interpretation of real evidence; it never manufactures evidence.

**Existence vs. magnitude (Task 15 item 5).** "Company X has customers" and
"Company X has strong commercial traction" are different claims requiring
different evidence. Customer Base Breadth's label set below encodes only
the narrowest claim the cited evidence supports -- a named customer band,
nothing about scale, growth, retention or revenue contribution, which
remain the job of their own dimensions.

**Revenue vs. GMV vs. bookings vs. ARR vs. funding vs. valuation (item 6).**
Every magnitude-bearing claim in this pillar carries an explicit `metric`
field on its `structured_fact` (`revenue`/`arr`/`gmv`/`bookings`/
`active_users`/`paying_customers`) that is never collapsed or renamed --
Disclosed Scale's own rationale and `classification_label` always name the
metric it actually used, so a GMV-only company is reported as scored from
GMV, never silently reframed as "revenue." A claim whose `structured_fact.
kind` is anything other than `"traction_metric"` (e.g. a funding round or a
valuation figure, which belong to Financial & Funding Signals, not yet
built) is structurally invisible to `_qualifying_scale_claims()` below,
regardless of which dimension's `assessment_criteria` it was mistakenly
tagged with -- cross-pillar leakage is prevented mechanically, the same
`assessment_criteria`-tagging enforcement Market Opportunity's own report
already documented (Task 13 §2), not by convention.

**Revenue-scale evidence, extracted once (item 12, spec Part 3.1).** A
Disclosed Scale claim whose `metric` is specifically `"revenue"` is exactly
the claim spec Part 3.1 says Financial & Funding Signals' own (not yet
built) `Revenue Disclosure` dimension will reference, not re-extract, via
this same claim's `assessment_criteria` list. Nothing further is required
here to enable that future reuse -- `assessment_criteria` already supports
one claim serving multiple dimensions (the mechanism Market Opportunity's
report already used this way); this pillar simply does not invent a second,
duplicate extraction path that would need reconciling later.

**Conflicting metrics (item 10).** This module adds no new conflict-
resolution code -- it reuses the ledger's own existing, unmodified rule
(spec Part 2.3, `ledger.py::resolve_dimension_evidence`): two claims
disagreeing about the same fact are tagged `support_status=disputed` by
whoever authors them, and `resolve_dimension_evidence` already excludes
disputed claims from `admissible` entirely, which is exactly the required
fail-closed behavior ("unresolved material conflicts fail closed... while
remaining visible in the ledger"). Two claims describing genuinely
DIFFERENT facts (different metrics, different periods) are never disputed
in the first place -- they are simply two distinct, separately-usable
data points, handled by `_qualifying_scale_claims()`'s own metric-keyed
grouping and `TRACTION_METRIC_PREFERENCE_ORDER`'s deterministic,
non-magnitude-based tie-break when more than one metric type qualifies.

**Company disclosures (item 9).** No dimension in this pillar requires
independent sourcing (unlike Market Opportunity) -- a private company's
own disclosed revenue/customer/retention figures are legitimate, admissible
evidence per spec Part 3.3's own wording, exactly the same trust posture
Team & Leadership already established for self-reported biographies. What
is preserved, unconditionally, is `source_type` (so a downstream reader can
tell a company disclosure from independently-verified reporting) and,
identically to every other Classified dimension in this engine, a
specificity bar (`requires_named_entity_fact`) that blocks vague,
unsupported claims regardless of source.
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
    requires_minimum_distinct_facts,
    requires_named_entity_fact,
    to_evidence_items,
)
from app.evidence_engine.confidence import compute_dimension_confidence
from app.evidence_engine.ledger import DimensionEvidence, EvidenceLedger, resolve_dimension_evidence
from app.evidence_engine.models import Claim
from app.evidence_engine.scoring import (
    AvailabilityStatus,
    DimensionCategory,
    DimensionResult,
    PillarGateParameters,
    PillarResult,
    evaluate_pillar,
)
from app.evidence_engine.stage import Stage, tier_for_stage

PILLAR = P.COMMERCIAL_TRACTION_PILLAR

DIMENSION_DISCLOSED_SCALE = "disclosed_scale"
DIMENSION_GROWTH_TRAJECTORY = "growth_trajectory"
DIMENSION_CUSTOMER_BASE_BREADTH = "customer_base_breadth"
DIMENSION_COMMERCIAL_VALIDATION = "commercial_validation"
DIMENSION_RETENTION_RENEWAL_SIGNAL = "retention_renewal_signal"


def _company_claims(ledger: EvidenceLedger, company_ref: str) -> EvidenceLedger:
    return EvidenceLedger.from_list([c for c in ledger.claims if c.company_ref == company_ref])


def _reason_for_absence(evidence: DimensionEvidence) -> AvailabilityStatus:
    if evidence.disputed and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_DISPUTED
    if evidence.stale and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_STALE
    return AvailabilityStatus.UNSCORED_NO_EVIDENCE


def _score_for_label(label_table: dict[str, dict[str, float]], label: str, stage: Stage) -> float | None:
    """Same mechanism as pillars/product_technology.py and
    pillars/team_leadership.py's own private copies -- most-permissive-
    tier fallback when stage is Undetermined (spec Part 4.3). Duplicated
    here rather than imported, per this engine's own "do not redesign
    shared infra for ordinary pillar-specific behavior" instruction."""
    tier_scores = label_table.get(label)
    if tier_scores is None:
        return None
    if stage == Stage.UNDETERMINED:
        return max(tier_scores.values())
    tier = tier_for_stage(stage)
    if tier is None:
        return max(tier_scores.values())
    return tier_scores[tier.value]


# --- Disclosed Scale / Growth Trajectory: shared typed-fact parsing ---------
# Both dimensions read the SAME underlying claim shape
# (`structured_fact.kind == "traction_metric"`) -- Disclosed Scale needs
# one qualifying point, Growth Trajectory needs two for the SAME metric.
# Parsing/validity rules are centralized here so both dimensions apply the
# identical admissibility bar to what counts as a usable figure at all.

@dataclass(frozen=True)
class _ScalePoint:
    claim: Claim
    period_date: date
    amount: float


def _parse_scale_point(claim: Claim) -> _ScalePoint | None:
    """Returns None (never raises) for any claim that isn't a well-formed,
    confirmed-actual, currency-supported traction figure -- fails closed
    on ambiguous input (Task 15 item 6) rather than guessing."""
    fact = claim.structured_fact or {}
    if fact.get("kind") != "traction_metric":
        return None
    metric = fact.get("metric")
    if metric not in P.TRACTION_MONEY_METRICS and metric not in P.TRACTION_COUNT_METRICS:
        return None
    if fact.get("value_type") != "actual":
        # Never one confirmed actual paired with a projection/guidance
        # figure (spec Part 3.3's own explicit instruction) -- a
        # projection is simply not a usable point here at all.
        return None
    if metric in P.TRACTION_MONEY_METRICS and fact.get("currency") != P.TRACTION_SUPPORTED_CURRENCY:
        # No FX normalization exists (parameters.py) -- a non-USD money
        # figure is retained in the ledger but not usable here.
        return None
    raw_amount = fact.get("amount")
    raw_date = fact.get("period_date")
    if not raw_amount or not raw_date:
        return None
    try:
        amount = float(raw_amount)
    except ValueError:
        return None
    if amount <= 0:
        return None
    try:
        period_date = date.fromisoformat(raw_date)
    except ValueError:
        return None
    return _ScalePoint(claim=claim, period_date=period_date, amount=amount)


def _qualifying_scale_points(claims: tuple[Claim, ...]) -> dict[str, list[_ScalePoint]]:
    by_metric: dict[str, list[_ScalePoint]] = {}
    for c in claims:
        point = _parse_scale_point(c)
        if point is None:
            continue
        by_metric.setdefault((c.structured_fact or {})["metric"], []).append(point)
    return by_metric


def _scale_band(metric: str, amount: float) -> str:
    if metric in P.TRACTION_MONEY_METRICS:
        if amount < P.DISCLOSED_SCALE_MONEY_SMALL_MAX_USD:
            return "SMALL"
        if amount < P.DISCLOSED_SCALE_MONEY_MODERATE_MAX_USD:
            return "MODERATE"
        return "LARGE"
    if amount < P.DISCLOSED_SCALE_COUNT_SMALL_MAX:
        return "SMALL"
    if amount < P.DISCLOSED_SCALE_COUNT_MODERATE_MAX:
        return "MODERATE"
    return "LARGE"


def _growth_band(growth_pct: float) -> str:
    if growth_pct < 0:
        return "DECLINING"
    if growth_pct < P.GROWTH_SLOW_MAX_PCT:
        return "SLOW"
    if growth_pct < P.GROWTH_MODERATE_MAX_PCT:
        return "MODERATE"
    return "FAST"


# --- 1. Disclosed Scale (Computed) -------------------------------------------
# Pure deterministic function of an already-typed fact (spec Part 6.1: "no
# network call, no AI call, no randomness"), exactly the shape the spec's
# own example describes -- no classification/extraction model call is made
# for this dimension or Growth Trajectory at all, since there is no label
# for a model to choose: the typed fact is read directly, matching Market
# Opportunity's own precedent for magnitude-bearing evidence (Task 13).

def evaluate_disclosed_scale(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
) -> DimensionResult:
    weight = P.COMMERCIAL_TRACTION_DIMENSION_WEIGHTS[DIMENSION_DISCLOSED_SCALE]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(
        scoped, DIMENSION_DISCLOSED_SCALE, as_of, P.COMMERCIAL_TRACTION_STALENESS_DAYS[DIMENSION_DISCLOSED_SCALE]
    )

    if not evidence.all_tagged:
        return DimensionResult(
            dimension=DIMENSION_DISCLOSED_SCALE, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            rationale="No claim is on record for this dimension.",
        )
    if not evidence.admissible:
        return DimensionResult(
            dimension=DIMENSION_DISCLOSED_SCALE, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=_reason_for_absence(evidence),
            rationale="No admissible (non-stale, non-disputed) claim is on record.",
        )

    by_metric = _qualifying_scale_points(evidence.admissible)
    if not by_metric:
        return DimensionResult(
            dimension=DIMENSION_DISCLOSED_SCALE, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
            rationale=(
                "Admissible evidence exists but none carries a usable, dated, confirmed-actual figure "
                "in a supported currency (private metrics genuinely absent, or only a projection/estimate "
                "is on record)."
            ),
        )

    chosen_metric = next((m for m in P.TRACTION_METRIC_PREFERENCE_ORDER if by_metric.get(m)), None)
    if chosen_metric is None:
        # Defensive: by_metric is non-empty but keyed by a metric outside
        # the preference order -- cannot happen given _parse_scale_point's
        # own metric allowlist, but fail closed rather than crash.
        return DimensionResult(
            dimension=DIMENSION_DISCLOSED_SCALE, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
            rationale="Admissible figures exist but none match a recognized traction metric.",
        )

    # Most-recent point for the chosen metric -- "current disclosed scale,"
    # never the largest number across metrics (item 10) and never an
    # average across time.
    point = max(by_metric[chosen_metric], key=lambda p: p.period_date)
    band = _scale_band(chosen_metric, point.amount)
    score = _score_for_label(P.DISCLOSED_SCALE_LABEL_SCORES, band, stage)
    unit = "USD" if chosen_metric in P.TRACTION_MONEY_METRICS else "count"
    return DimensionResult(
        dimension=DIMENSION_DISCLOSED_SCALE, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
        score=score, availability=AvailabilityStatus.SCORABLE,
        supporting_claim_ids=(point.claim.claim_id,),
        classification_label=band,
        confidence=compute_dimension_confidence((point.claim,)),
        rationale=(
            f"Disclosed {chosen_metric} of {point.amount:,.0f} {unit} as of {point.period_date.isoformat()}, "
            f"banded {band}."
        ),
    )


# --- 2. Growth Trajectory (Computed) -----------------------------------------
# Spec Part 3.3's own staleness column reads "Newer point <=18 months old"
# -- a bound on the NEWER of the two points only, not a blanket per-claim
# filter (the older point exists purely to establish a rate's starting
# baseline; its own age carries no separate staleness meaning). Evidence
# is therefore resolved here with NO staleness ceiling
# (GROWTH_TRAJECTORY_RESOLUTION_STALENESS_DAYS -- disputed-exclusion and
# independence-group dedup still apply), and the real 18-month bound is
# applied explicitly below, only to whichever point is chosen as the
# newer one of a qualifying pair. A real, well-sourced older revenue
# figure is never discarded merely for being old -- only a too-old NEWER
# point disqualifies a pair. This is a genuine spec-fidelity fix the Task
# 15 real-evidence sanity check surfaced (see the Commercial Traction
# report), not a calibration change.

def evaluate_growth_trajectory(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
) -> DimensionResult:
    weight = P.COMMERCIAL_TRACTION_DIMENSION_WEIGHTS[DIMENSION_GROWTH_TRAJECTORY]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(
        scoped, DIMENSION_GROWTH_TRAJECTORY, as_of, P.GROWTH_TRAJECTORY_RESOLUTION_STALENESS_DAYS
    )

    if not evidence.all_tagged:
        return DimensionResult(
            dimension=DIMENSION_GROWTH_TRAJECTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            rationale="No claim is on record for this dimension.",
        )
    if not evidence.admissible:
        return DimensionResult(
            dimension=DIMENSION_GROWTH_TRAJECTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=_reason_for_absence(evidence),
            rationale="No admissible (non-stale, non-disputed) claim is on record.",
        )

    by_metric = _qualifying_scale_points(evidence.admissible)

    chosen = None
    newer_point_stale = False
    for metric in P.TRACTION_METRIC_PREFERENCE_ORDER:
        pool = by_metric.get(metric, [])
        if len(pool) < 2:
            continue
        pool_sorted = sorted(pool, key=lambda p: p.period_date)
        earliest, latest = pool_sorted[0], pool_sorted[-1]
        window_days = (latest.period_date - earliest.period_date).days
        if window_days < P.GROWTH_MIN_WINDOW_DAYS:
            # Two points exist for this metric but not far enough apart --
            # never annualized from a too-short window; try the next
            # metric in preference order rather than accepting it.
            continue
        # The real staleness rule (spec Part 3.3): only the NEWER point
        # must be within the bound. A qualifying pair whose newer point
        # has since aged out is not usable -- but a DIFFERENT metric's
        # pair, or this same metric re-evaluated at an earlier as_of,
        # might still be, so this only disqualifies this specific pair.
        reference = latest.claim.published_at or latest.claim.retrieved_at
        if (as_of - reference).days > P.COMMERCIAL_TRACTION_STALENESS_DAYS[DIMENSION_GROWTH_TRAJECTORY]:
            newer_point_stale = True
            continue
        chosen = (metric, earliest, latest, window_days)
        break

    if chosen is None:
        if newer_point_stale:
            return DimensionResult(
                dimension=DIMENSION_GROWTH_TRAJECTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
                score=None, availability=AvailabilityStatus.UNSCORED_STALE,
                rationale=(
                    "A qualifying two-point pair exists for at least one metric, but its newer point is older "
                    f"than the {P.COMMERCIAL_TRACTION_STALENESS_DAYS[DIMENSION_GROWTH_TRAJECTORY]}-day staleness "
                    "bound (spec: 'newer point <=18 months old') -- a growth trajectory this old is no longer "
                    "current, even though the underlying figures remain real."
                ),
            )
        return DimensionResult(
            dimension=DIMENSION_GROWTH_TRAJECTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
            rationale=(
                "No single metric has two admissible, confirmed-actual, dated points spanning at least "
                f"{P.GROWTH_MIN_WINDOW_DAYS} days -- a growth rate is not computable from what is on record "
                "(one data point, or two points too close together, or two points for different metrics)."
            ),
        )

    metric, earliest, latest, window_days = chosen
    if window_days >= P.GROWTH_ANNUALIZE_MIN_WINDOW_DAYS:
        years = window_days / 365.25
        growth_pct = ((latest.amount / earliest.amount) ** (1 / years) - 1) * 100
        method = "annualized (CAGR)"
    else:
        growth_pct = ((latest.amount - earliest.amount) / earliest.amount) * 100
        method = "raw period growth, not annualized (window below the annualization floor)"

    band = _growth_band(growth_pct)
    score = P.GROWTH_TRAJECTORY_LABEL_SCORES[band]  # flat, stage-independent -- see parameters.py
    return DimensionResult(
        dimension=DIMENSION_GROWTH_TRAJECTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
        score=score, availability=AvailabilityStatus.SCORABLE,
        supporting_claim_ids=(earliest.claim.claim_id, latest.claim.claim_id),
        classification_label=band,
        confidence=compute_dimension_confidence((earliest.claim, latest.claim)),
        rationale=(
            f"{metric} moved from {earliest.amount:,.0f} ({earliest.period_date.isoformat()}) to "
            f"{latest.amount:,.0f} ({latest.period_date.isoformat()}) over {window_days} days -- {method}: "
            f"{growth_pct:.1f}%, banded {band}."
        ),
    )


# --- Shared per-dimension Classified-evaluation harness (pillar-local, see --
# --- module docstring on why this is duplicated rather than extracted) ------

def _evaluate_classified_dimension(
    *,
    ledger: EvidenceLedger,
    company_ref: str,
    as_of: date,
    stage: Stage,
    dimension: str,
    allowed_labels: tuple[str, ...],
    unscored_label_reasons: dict[str, AvailabilityStatus],
    score_lookup,  # Callable[[str], float | None]
    label_requirement_check,
    model: ClassificationModel,
    company_display_names: tuple[str, ...],
) -> DimensionResult:
    weight = P.COMMERCIAL_TRACTION_DIMENSION_WEIGHTS[dimension]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(scoped, dimension, as_of, P.COMMERCIAL_TRACTION_STALENESS_DAYS[dimension])

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
                f"{P.COMMERCIAL_TRACTION_STALENESS_DAYS[dimension]}-day staleness bound; none is currently admissible."
            ),
        )

    if not evidence.admissible:
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            rationale="No claim is on record for this dimension.",
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
    score = score_lookup(response.label)
    if score is None:
        reason = unscored_label_reasons.get(response.label, AvailabilityStatus.UNSCORED_NO_EVIDENCE)
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=reason, classification_label=response.label,
            rationale=f"Classified as {response.label!r}, which does not score this dimension.",
        )

    cited = tuple(c for c in evidence.admissible if c.claim_id in response.supporting_claim_ids)
    rationale = f"Classified as {response.label!r}."
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


# --- 3. Customer Base Breadth ------------------------------------------------

@dataclass(frozen=True)
class WellBehavedCustomerBaseBreadthClassifier:
    """Reads `structured_fact.value` (SMALL|MODERATE|LARGE) directly --
    never a raw customer count, never a claim's text. A bare customer logo
    with no `structured_fact` (item 7: "customer logos alone are weak
    evidence") carries no `kind == 'customer_band'` fact and is simply
    invisible here, falling through to NOT_DISCLOSED."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        for item in request.evidence_items:
            if not item.structured_fact or item.structured_fact.get("kind") != "customer_band":
                continue
            value = item.structured_fact.get("value")
            if value in ("SMALL", "MODERATE", "LARGE"):
                return ClassificationResponse(label=value, supporting_claim_ids=(item.claim_id,))
        return ClassificationResponse(label="NOT_DISCLOSED", supporting_claim_ids=())


_DEFAULT_CUSTOMER_BASE_BREADTH_MODEL = WellBehavedCustomerBaseBreadthClassifier()
_CUSTOMER_BASE_BREADTH_REQUIREMENT = requires_named_entity_fact(frozenset({"SMALL", "MODERATE", "LARGE"}))


def evaluate_customer_base_breadth(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_CUSTOMER_BASE_BREADTH,
        allowed_labels=("NOT_DISCLOSED", "SMALL", "MODERATE", "LARGE"),
        unscored_label_reasons={"NOT_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        score_lookup=lambda label: _score_for_label(P.CUSTOMER_BASE_BREADTH_LABEL_SCORES, label, stage),
        label_requirement_check=_CUSTOMER_BASE_BREADTH_REQUIREMENT,
        model=model or _DEFAULT_CUSTOMER_BASE_BREADTH_MODEL,
        company_display_names=company_display_names,
    )


# --- 4. Commercial Validation -------------------------------------------------

@dataclass(frozen=True)
class WellBehavedCommercialValidationClassifier:
    """Counts DISTINCT named commercial-commitment claims (one
    representative per independence group), the identical mechanism
    Leadership Composition (Team & Leadership) already established for
    named hires -- a single, explicit "no commercial commitments beyond
    a basic product signup" state is not modeled here (unlike Leadership
    Composition's NONE_BEYOND_FOUNDERS) because the spec gives Commercial
    Validation no equivalent explicit non-penalized-absence label; absence
    is simply NOT_ESTABLISHED (Unscored), the ordinary "no evidence"
    outcome."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        commitments: dict[str, str] = {}
        for item in request.evidence_items:
            if not item.structured_fact or item.structured_fact.get("kind") != "commercial_commitment":
                continue
            commitments.setdefault(item.independence_group_id, item.claim_id)

        distinct = len(commitments)
        if distinct >= P.COMMERCIAL_VALIDATION_SUBSTANTIAL_MIN_COUNT:
            return ClassificationResponse(label="SUBSTANTIAL_VALIDATION", supporting_claim_ids=tuple(commitments.values()))
        if distinct >= P.COMMERCIAL_VALIDATION_SOME_MIN_COUNT:
            return ClassificationResponse(label="SOME_VALIDATION", supporting_claim_ids=tuple(commitments.values()))
        return ClassificationResponse(label="NOT_ESTABLISHED", supporting_claim_ids=())


_DEFAULT_COMMERCIAL_VALIDATION_MODEL = WellBehavedCommercialValidationClassifier()
_COMMERCIAL_VALIDATION_REQUIREMENT = requires_minimum_distinct_facts(
    {
        "SUBSTANTIAL_VALIDATION": P.COMMERCIAL_VALIDATION_SUBSTANTIAL_MIN_COUNT,
        "SOME_VALIDATION": P.COMMERCIAL_VALIDATION_SOME_MIN_COUNT,
    }
)


def evaluate_commercial_validation(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_COMMERCIAL_VALIDATION,
        allowed_labels=("NOT_ESTABLISHED", "SOME_VALIDATION", "SUBSTANTIAL_VALIDATION"),
        unscored_label_reasons={"NOT_ESTABLISHED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        score_lookup=lambda label: _score_for_label(P.COMMERCIAL_VALIDATION_LABEL_SCORES, label, stage),
        label_requirement_check=_COMMERCIAL_VALIDATION_REQUIREMENT,
        model=model or _DEFAULT_COMMERCIAL_VALIDATION_MODEL,
        company_display_names=company_display_names,
    )


# --- 5. Retention / Renewal Signal -------------------------------------------

@dataclass(frozen=True)
class WellBehavedRetentionRenewalClassifier:
    """Reads `structured_fact.value` (WEAK|MODERATE|STRONG) directly --
    never company age, customer logos, reviews, traffic, social activity,
    funding history, customer count, or general popularity (item 8's own
    explicit, non-negotiable exclusion list). None of those signals has
    any code path into this classifier at all: it reads only
    `structured_fact.kind == 'retention_signal'`, which nothing else in
    this pillar ever produces."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        for item in request.evidence_items:
            if not item.structured_fact or item.structured_fact.get("kind") != "retention_signal":
                continue
            value = item.structured_fact.get("value")
            if value in ("WEAK", "MODERATE", "STRONG"):
                return ClassificationResponse(label=value, supporting_claim_ids=(item.claim_id,))
        return ClassificationResponse(label="NONE_DISCLOSED", supporting_claim_ids=())


_DEFAULT_RETENTION_RENEWAL_MODEL = WellBehavedRetentionRenewalClassifier()
_RETENTION_RENEWAL_REQUIREMENT = requires_named_entity_fact(frozenset({"WEAK", "MODERATE", "STRONG"}))


def evaluate_retention_renewal_signal(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_RETENTION_RENEWAL_SIGNAL,
        allowed_labels=("NONE_DISCLOSED", "WEAK", "MODERATE", "STRONG"),
        unscored_label_reasons={"NONE_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        score_lookup=lambda label: P.RETENTION_LABEL_SCORES.get(label),  # flat -- see parameters.py
        label_requirement_check=_RETENTION_RENEWAL_REQUIREMENT,
        model=model or _DEFAULT_RETENTION_RENEWAL_MODEL,
        company_display_names=company_display_names,
    )


# --- Orchestration -----------------------------------------------------------

def evaluate_all(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
    customer_base_breadth_model: ClassificationModel | None = None,
    commercial_validation_model: ClassificationModel | None = None,
    retention_renewal_model: ClassificationModel | None = None,
) -> tuple[DimensionResult, ...]:
    return (
        evaluate_disclosed_scale(ledger, company_ref, as_of, stage, company_display_names),
        evaluate_growth_trajectory(ledger, company_ref, as_of, stage, company_display_names),
        evaluate_customer_base_breadth(
            ledger, company_ref, as_of, stage, company_display_names, customer_base_breadth_model
        ),
        evaluate_commercial_validation(
            ledger, company_ref, as_of, stage, company_display_names, commercial_validation_model
        ),
        evaluate_retention_renewal_signal(
            ledger, company_ref, as_of, stage, company_display_names, retention_renewal_model
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
