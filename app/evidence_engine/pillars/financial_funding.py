"""
Financial & Funding Signals pillar (Task 17; NEW_ENGINE_SPEC.md Part 3.3).
The sixth and final individual pillar implemented in this engine, on the
exact same architecture Product & Technology, Market Opportunity, Team &
Leadership, Commercial Traction, and Execution & Momentum already
validated (Tasks 8-16). No shared scoring philosophy, evidence ledger,
classification system, provenance system, confidence model, stage model,
or publication gate was redesigned to build this.

**Task 17 scope note (a spec conflict surfaced and resolved by the user,
not silently changed).** Task 17's own instructions referenced a
"previously approved decision" that Capital Efficiency was removed from
this pillar. `NEW_ENGINE_SPEC.md` (Part 3.3) still defines it (weight
0.30) and `NEW_ENGINE_CALIBRATION.md` still names specific test companies
around it; no removal is recorded anywhere in either document or in
`NEW_ENGINE_ARCHITECTURE.md`. This conflict was surfaced to the user
before implementation began, per the task's own explicit "stop and
report" instruction; the user confirmed the spec as currently written is
authoritative. This module therefore implements all three dimensions
exactly as `NEW_ENGINE_SPEC.md` defines them.

**The one rule that overrides every other consideration in this module:
funding evidence is not financial-health evidence, and unavailable
private financial information is not evidence of poor financial health.**
Concretely, and non-negotiably:

  - Raising $5M, $50M, or $500M; a prestigious VC round; a high
    valuation; multiple financing rounds -- none of these, by themselves,
    establish profitability, margins, unit economics, burn efficiency,
    runway, or financial sustainability. `Funding History`'s own parser
    (`_parse_funding_round`) recognizes only `structured_fact.kind ==
    "funding_round"`; `Capital Efficiency`'s own classifier recognizes
    only `structured_fact.kind == "capital_efficiency_signal"`. Neither
    has any code path into the other's label or score.
  - Runway is NEVER computed by this engine from `funding_amount /
    guessed_burn` or from `funding_date -> assumed_remaining_runway`
    (item 8's own explicit prohibition). A runway figure is admissible
    evidence for `Capital Efficiency` only when it is itself a
    specifically, voluntarily disclosed statement
    (`structured_fact.metric == "runway"`) -- never derived from any
    other typed fact this engine holds.
  - Unit economics/margins are never inferred from revenue, customer
    count, funding, valuation, product popularity, company maturity, or
    "being a software company." `WellBehavedCapitalEfficiencyClassifier`
    reads only `structured_fact` -- there is no code path from any of
    those signals into a `Capital Efficiency` label.
  - Missing financial evidence affects `coverage`/`confidence` only --
    `Strength` (the shared, unmodified `compute_pillar_strength`) is a
    renormalized average over only the `SCORABLE` dimensions, so an
    Unscored dimension is excluded from the average entirely, never
    averaged in as a low number.

**Revenue Disclosure: reference, not re-extraction (item 5, spec Part
3.1).** This dimension never independently researches or re-extracts a
revenue figure. It reads claims tagged `assessment_criteria` containing
`"revenue_disclosure"` -- the SAME claim objects Commercial Traction's own
`Disclosed Scale` dimension already requires when a disclosed figure is
specifically revenue (`structured_fact.metric == "revenue"`), tagged with
a second `assessment_criteria` entry at claim-authoring time. No direct
Python import or call from this module into `commercial_traction.py`
exists or is needed -- `assessment_criteria` tagging (spec Part 2.1) is
already the generic mechanism that lets one claim serve two dimensions,
and therefore two pillars, without being extracted, and therefore
weighted, twice. If a claim is never tagged `"revenue_disclosure"`, this
dimension is honestly `Unscored` regardless of whether an otherwise-
identical revenue claim exists tagged only for Commercial Traction -- the
reuse is explicit and opt-in, never implicit merely because the metric
type matches, consistent with spec Part 2.1's own "a claim with no mapped
criteria... never enters scoring" rule.

**Funding History's own staleness resolution (item 13 -- do not repeat
the Task 15/16 mistake a third time).** Spec Part 3.3's own staleness
column reads "36 months (a disclosed 2021 round remains a real, permanent
fact)" -- a value and a justification that directly contradict each other
if the 36-month figure were applied as a per-round exclusion bound (a
disclosed 2021 round observed from a 2026 `as_of` date is nearly 60
months old). Unlike Growth Trajectory (Commercial Traction, Task 15) or
Strategic Consistency (Execution & Momentum, Task 16), Funding History has
no "current view" component to anchor a narrower bound to at all -- it is
PURELY cumulative/historical, and every disclosed, completed, admissible
equity round is exactly the kind of "permanent fact" the spec's own
parenthetical describes. Resolved narrowly: NO staleness exclusion is
applied to Funding History's own evidence at all
(`FUNDING_HISTORY_RESOLUTION_STALENESS_DAYS`, parameters.py) --
disputed-exclusion and independence-group dedup still apply.

**Total capital raised, not the latest round alone (item 7/14).**
Funding History sums the disclosed amount of every distinct, completed,
equity-financed, provenance-verified round on record -- never just the
most recent one, and never a raw claim count (`provenance.py::
verify_independence` is called directly here, the same public function
`requires_minimum_distinct_facts` already calls internally, reused
directly in this Computed dimension's own deterministic code since there
is no classification model involved to route the check through). Debt
financing, grants, and tender-offer/secondary-transaction facts remain
admissible (retained in the ledger, visible via `assessment_criteria`)
but are structurally excluded from the summed total -- see
`FUNDING_HISTORY_COUNTED_FINANCING_TYPES` (parameters.py) for the full
documented reasoning.
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
    requires_named_entity_fact,
    to_evidence_items,
)
from app.evidence_engine.confidence import compute_dimension_confidence
from app.evidence_engine.ledger import DimensionEvidence, EvidenceLedger, resolve_dimension_evidence
from app.evidence_engine.models import Claim
from app.evidence_engine.provenance import verify_independence
from app.evidence_engine.scoring import (
    AvailabilityStatus,
    DimensionCategory,
    DimensionResult,
    PillarGateParameters,
    PillarResult,
    evaluate_pillar,
)
from app.evidence_engine.stage import Stage, tier_for_stage

PILLAR = P.FINANCIAL_FUNDING_PILLAR

DIMENSION_FUNDING_HISTORY = "funding_history"
DIMENSION_REVENUE_DISCLOSURE = "revenue_disclosure"
DIMENSION_CAPITAL_EFFICIENCY = "capital_efficiency"


def _company_claims(ledger: EvidenceLedger, company_ref: str) -> EvidenceLedger:
    return EvidenceLedger.from_list([c for c in ledger.claims if c.company_ref == company_ref])


def _reason_for_absence(evidence: DimensionEvidence) -> AvailabilityStatus:
    if evidence.disputed and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_DISPUTED
    if evidence.stale and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_STALE
    return AvailabilityStatus.UNSCORED_NO_EVIDENCE


def _score_for_label(label_table: dict[str, dict[str, float]], label: str, stage: Stage) -> float | None:
    """Same mechanism as every other pillar's own private copy --
    most-permissive-tier fallback when stage is Undetermined (spec Part
    4.3). Duplicated here rather than imported, per this engine's own
    "do not redesign shared infra for ordinary pillar-specific behavior"
    instruction."""
    tier_scores = label_table.get(label)
    if tier_scores is None:
        return None
    if stage == Stage.UNDETERMINED:
        return max(tier_scores.values())
    tier = tier_for_stage(stage)
    if tier is None:
        return max(tier_scores.values())
    return tier_scores[tier.value]


def _money_band(amount: float, small_max: float, moderate_max: float) -> str:
    if amount < small_max:
        return "SMALL"
    if amount < moderate_max:
        return "MODERATE"
    return "LARGE"


# --- 1. Funding History (Computed) -------------------------------------------

@dataclass(frozen=True)
class _FundingRound:
    claim: Claim
    amount: float
    round_date: date


def _parse_funding_round(claim: Claim) -> _FundingRound | None:
    """Returns None (never raises) for any claim that isn't a well-formed,
    completed, equity-financed, USD-denominated round -- fails closed on
    ambiguous input rather than guessing. A claim whose `structured_fact.
    kind` is anything other than "funding_round" (e.g. "valuation",
    "traction_metric", or stage.py's own "funding_round_type" stage-signal
    kind) is structurally invisible here regardless of which dimension's
    `assessment_criteria` it carries -- cross-pillar/cross-kind leakage
    prevented mechanically, not by convention."""
    fact = claim.structured_fact or {}
    if fact.get("kind") != "funding_round":
        return None
    if fact.get("status") != "completed":
        # "Announced" (not yet closed) financing is explicitly distinct
        # (item 7) and never counts toward a completed round's total.
        return None
    if fact.get("financing_type") not in P.FUNDING_HISTORY_COUNTED_FINANCING_TYPES:
        # Debt, grants, and tender-offer/secondary transactions are
        # retained in the ledger but do not carry "equity", so they never
        # reach this point (module docstring).
        return None
    if fact.get("currency") != "USD":
        # No FX normalization exists in this engine (the same documented
        # limitation Commercial Traction's own Disclosed Scale already
        # has, Task 15) -- a non-USD round is retained but not usable here.
        return None
    raw_amount = fact.get("amount")
    raw_date = fact.get("round_date")
    if not raw_amount or not raw_date:
        return None
    try:
        amount = float(raw_amount)
    except ValueError:
        return None
    if amount <= 0:
        return None
    try:
        round_date = date.fromisoformat(raw_date)
    except ValueError:
        return None
    return _FundingRound(claim=claim, amount=amount, round_date=round_date)


def evaluate_funding_history(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
) -> DimensionResult:
    weight = P.FINANCIAL_FUNDING_DIMENSION_WEIGHTS[DIMENSION_FUNDING_HISTORY]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(
        scoped, DIMENSION_FUNDING_HISTORY, as_of, P.FUNDING_HISTORY_RESOLUTION_STALENESS_DAYS
    )

    if not evidence.all_tagged:
        return DimensionResult(
            dimension=DIMENSION_FUNDING_HISTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            rationale="No claim is on record for this dimension.",
        )
    if not evidence.admissible:
        return DimensionResult(
            dimension=DIMENSION_FUNDING_HISTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=_reason_for_absence(evidence),
            rationale="No admissible (non-disputed) claim is on record.",
        )

    candidates = tuple(r for r in (_parse_funding_round(c) for c in evidence.admissible) if r is not None)
    if not candidates:
        return DimensionResult(
            dimension=DIMENSION_FUNDING_HISTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
            rationale=(
                "Admissible evidence exists but none carries a usable, completed, equity, USD-denominated "
                "round with a size and date (only announced/debt/grant/secondary evidence, or an unparseable "
                "figure, is on record)."
            ),
        )

    verified = verify_independence(tuple(r.claim for r in candidates))
    confirmed_ids = {c.claim_id for c in verified.confirmed_independent}
    counted = tuple(r for r in candidates if r.claim.claim_id in confirmed_ids)
    if not counted:
        return DimensionResult(
            dimension=DIMENSION_FUNDING_HISTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
            rationale="Candidate rounds could not be confirmed as provenance-distinct facts (possible restatement/duplicate).",
        )

    total = sum(r.amount for r in counted)
    band = _money_band(total, P.FUNDING_HISTORY_SMALL_MAX_USD, P.FUNDING_HISTORY_MODERATE_MAX_USD)
    score = _score_for_label(P.FUNDING_HISTORY_LABEL_SCORES, band, stage)
    latest = max(counted, key=lambda r: r.round_date)
    return DimensionResult(
        dimension=DIMENSION_FUNDING_HISTORY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
        score=score, availability=AvailabilityStatus.SCORABLE,
        supporting_claim_ids=tuple(r.claim.claim_id for r in counted),
        classification_label=band,
        confidence=compute_dimension_confidence(tuple(r.claim for r in counted)),
        rationale=(
            f"{len(counted)} distinct completed equity round(s) totaling {total:,.0f} USD "
            f"(latest: {latest.amount:,.0f} USD on {latest.round_date.isoformat()}), banded {band}."
        ),
    )


# --- 2. Revenue Disclosure (Computed, cross-referenced) -----------------------
# Reads the SAME claim shape Commercial Traction's Disclosed Scale uses
# (structured_fact.kind == "traction_metric"), but filtered to
# specifically metric == "revenue" (narrower than Commercial Traction's
# own multi-metric acceptance of revenue/arr/gmv/bookings/users/paying_
# customers) and only among claims explicitly tagged for THIS dimension
# (module docstring, "Revenue Disclosure: reference, not re-extraction").

@dataclass(frozen=True)
class _RevenuePoint:
    claim: Claim
    period_date: date
    amount: float


def _parse_revenue_point(claim: Claim) -> _RevenuePoint | None:
    fact = claim.structured_fact or {}
    if fact.get("kind") != "traction_metric":
        return None
    if fact.get("metric") != "revenue":
        # ARR, GMV, bookings, active_users, paying_customers all belong to
        # Commercial Traction's own broader Disclosed Scale; this
        # dimension is deliberately narrower, per spec's own "filtered to
        # specifically-revenue figures" wording.
        return None
    if fact.get("value_type") != "actual":
        return None
    if fact.get("currency") != "USD":
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
    return _RevenuePoint(claim=claim, period_date=period_date, amount=amount)


def evaluate_revenue_disclosure(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
) -> DimensionResult:
    weight = P.FINANCIAL_FUNDING_DIMENSION_WEIGHTS[DIMENSION_REVENUE_DISCLOSURE]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(
        scoped, DIMENSION_REVENUE_DISCLOSURE, as_of, P.FINANCIAL_FUNDING_STALENESS_DAYS[DIMENSION_REVENUE_DISCLOSURE]
    )

    if not evidence.all_tagged:
        return DimensionResult(
            dimension=DIMENSION_REVENUE_DISCLOSURE, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            rationale=(
                "No claim is tagged for this dimension. Revenue Disclosure only ever reuses a claim "
                "Commercial Traction's own Disclosed Scale already requires, explicitly tagged with this "
                "dimension too -- it never re-extracts a figure independently."
            ),
        )
    if not evidence.admissible:
        return DimensionResult(
            dimension=DIMENSION_REVENUE_DISCLOSURE, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=_reason_for_absence(evidence),
            rationale="No admissible (non-stale, non-disputed) claim is on record.",
        )

    points = tuple(p for p in (_parse_revenue_point(c) for c in evidence.admissible) if p is not None)
    if not points:
        return DimensionResult(
            dimension=DIMENSION_REVENUE_DISCLOSURE, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
            rationale=(
                "Admissible evidence exists but none carries a usable, dated, confirmed-actual, "
                "specifically-revenue figure in USD (ARR/GMV/bookings/user-count figures belong to "
                "Commercial Traction's own broader Disclosed Scale, not this narrower dimension)."
            ),
        )

    point = max(points, key=lambda p: p.period_date)
    band = _money_band(point.amount, P.REVENUE_DISCLOSURE_SMALL_MAX_USD, P.REVENUE_DISCLOSURE_MODERATE_MAX_USD)
    score = _score_for_label(P.REVENUE_DISCLOSURE_LABEL_SCORES, band, stage)
    return DimensionResult(
        dimension=DIMENSION_REVENUE_DISCLOSURE, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
        score=score, availability=AvailabilityStatus.SCORABLE,
        supporting_claim_ids=(point.claim.claim_id,),
        classification_label=band,
        confidence=compute_dimension_confidence((point.claim,)),
        rationale=(
            f"Disclosed revenue of {point.amount:,.0f} USD as of {point.period_date.isoformat()}, banded {band} "
            "(referenced from the same claim Commercial Traction's Disclosed Scale already requires)."
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
    weight = P.FINANCIAL_FUNDING_DIMENSION_WEIGHTS[dimension]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(scoped, dimension, as_of, P.FINANCIAL_FUNDING_STALENESS_DAYS[dimension])

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
                f"{P.FINANCIAL_FUNDING_STALENESS_DAYS[dimension]}-day staleness bound; none is currently admissible."
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


# --- 3. Capital Efficiency -----------------------------------------------

@dataclass(frozen=True)
class WellBehavedCapitalEfficiencyClassifier:
    """Reads `structured_fact.value` (WEAK|MODERATE|STRONG) directly --
    never company age, funding amount, headcount, revenue, customer
    count, valuation, or "being a software company" (item 9's own
    explicit, non-negotiable exclusion list). None of those signals has
    any code path into this classifier at all: it reads only
    `structured_fact.kind == 'capital_efficiency_signal'`, which nothing
    else in this pillar (or any other pillar) ever produces."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        for item in request.evidence_items:
            if not item.structured_fact or item.structured_fact.get("kind") != "capital_efficiency_signal":
                continue
            value = item.structured_fact.get("value")
            if value in ("WEAK", "MODERATE", "STRONG"):
                return ClassificationResponse(label=value, supporting_claim_ids=(item.claim_id,))
        return ClassificationResponse(label="NONE_DISCLOSED", supporting_claim_ids=())


_DEFAULT_CAPITAL_EFFICIENCY_MODEL = WellBehavedCapitalEfficiencyClassifier()
_CAPITAL_EFFICIENCY_REQUIREMENT = requires_named_entity_fact(frozenset({"WEAK", "MODERATE", "STRONG"}))


def evaluate_capital_efficiency(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_CAPITAL_EFFICIENCY,
        allowed_labels=("NONE_DISCLOSED", "WEAK", "MODERATE", "STRONG"),
        unscored_label_reasons={"NONE_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        score_lookup=lambda label: P.CAPITAL_EFFICIENCY_LABEL_SCORES.get(label),  # flat -- see parameters.py
        label_requirement_check=_CAPITAL_EFFICIENCY_REQUIREMENT,
        model=model or _DEFAULT_CAPITAL_EFFICIENCY_MODEL,
        company_display_names=company_display_names,
    )


# --- Orchestration -----------------------------------------------------------

def evaluate_all(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
    capital_efficiency_model: ClassificationModel | None = None,
) -> tuple[DimensionResult, ...]:
    return (
        evaluate_funding_history(ledger, company_ref, as_of, stage, company_display_names),
        evaluate_revenue_disclosure(ledger, company_ref, as_of, stage, company_display_names),
        evaluate_capital_efficiency(ledger, company_ref, as_of, stage, company_display_names, capital_efficiency_model),
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
