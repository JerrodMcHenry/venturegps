"""
Execution & Momentum pillar (Task 16; NEW_ENGINE_SPEC.md Part 3.3). The
fifth pillar implemented in this engine, on the exact same architecture
Product & Technology, Market Opportunity, Team & Leadership, and
Commercial Traction already validated (Tasks 8-15). No shared scoring
philosophy, evidence ledger, classification system, provenance system,
confidence model, stage model, or publication gate was redesigned to
build this.

**The one rule that overrides every other consideration in this module:
activity is not execution, and execution is not commercial traction.** A
press release, a blog post, a social-media announcement, a funding round,
an employee hire, a job posting, conference attendance, a partnership
announcement, or a roadmap promise is never, by itself, execution
evidence. Concretely, and non-negotiably:

  - No dimension in this pillar scores from a company's own stated
    intentions ("plans to," "coming soon," "expects to," "will launch").
    Shipping Velocity's own classifier reads only `structured_fact.status
    == "launched"` -- "announced" and "beta" carry no code path to a
    score at all (see `_resolve_current_release_status` below).
  - Funding is never execution evidence. A claim whose `structured_fact.
    kind` is anything other than this pillar's own recognized kinds
    (`product_release` for Shipping Velocity, `gtm_evidence` for
    Go-to-Market Motion Evidence) is structurally invisible to this
    pillar's parsers, regardless of which dimension's `assessment_
    criteria` it was mistakenly tagged with -- the same mechanical
    cross-pillar-leakage prevention Commercial Traction's own report
    already documented (Task 15 §1.3), extended here to funding/
    valuation facts specifically.
  - General headcount or engineering hiring is never GTM evidence. Only a
    claim explicitly tagged `structured_fact.gtm_type == "hire"` (a
    SALES/GTM-function hire specifically, per spec Part 3.3's own
    "disclosed sales/GTM hiring" wording) is recognized -- an
    engineering-hire claim carries no such fact and is invisible to
    `WellBehavedGTMMotionClassifier` regardless of the hire's own
    prestige (a "former Google VP of Engineering" hire reads identically
    to an obscure one unless it is specifically a GTM-function hire).
  - Commercial traction (revenue, customer counts, retention) is never
    execution evidence, and a shipped release is never, by itself,
    Commercial Traction evidence -- these are different facts about
    different questions ("did the company ship" vs. "was it adopted"),
    enforced by the same `assessment_criteria`-tagging mechanism every
    pillar boundary in this engine already relies on, tested directly in
    `tests/test_execution_momentum.py`'s dedicated cross-pillar-leakage
    section.

**Preserving announced -> launched -> available (Task 16 item 3).**
"Adopted" is deliberately out of scope for this pillar entirely (that is
Commercial Traction's own job) -- so only two meaningful states matter
here: a release has SHIPPED (`status == "launched"`, covering what a
reader would recognize as "generally available") or it has NOT
(`"announced"` or `"beta"`, an explicitly partial/incomplete state that
never counts toward Shipping Velocity's cadence). No dimension in this
module ever upgrades one state into another.

**Supersession, not silent overwriting (item 12).** A single named release
may be described by multiple claims over time (announced, then later
launched; or announced, then later delayed/cancelled). Per spec Part
2.3's own "a more recently published figure... outranks an older one for
the SAME reporting period" principle -- and mirroring `stage.py`'s own
"most recent disclosed round wins" precedent, applied here to a named
release's current status rather than a company's funding stage --
`_resolve_current_release_status()` groups admissible, non-disputed
`product_release` claims by `structured_fact.named_entity` (the release's
own identifying name) and takes the MOST RECENT (by `published_at`, or
`retrieved_at` when absent) claim as authoritative for that release's
CURRENT status. A release that was announced and later shipped counts
once, as launched; a release that was announced and later delayed or
cancelled never counts as launched at all. This is separate from, and
applied in addition to, the ledger's own existing `independence_group_id`
dedup (Task 16 item 14 / item 4's "a cluster of articles covering the
same launch is one underlying event, not repeated execution") -- five
restatements of ONE announcement collapse to one representative claim
via the shared admissibility gate before supersession is even
considered; supersession then separately handles multiple DIFFERENT,
dated reports about the SAME named release evolving over time. A genuine
factual disagreement about the same release (e.g. two sources giving
different launch dates for what is supposedly one event) is a different
case entirely and is handled the ordinary way every other dimension in
this engine handles it -- tagged `disputed`/`contradicts` by whoever
authors the claims, excluded from `admissible` by the shared gate before
supersession ever runs.

**Strategic Consistency's own architectural wrinkle.** Every other
dimension in this engine treats `disputed` evidence as something to
EXCLUDE (spec Part 2.3's fail-closed default). Strategic Consistency's
entire job is the opposite: detecting whether the company's own disclosed
statements over time conflict is the dimension's actual output, not a
reason to discard evidence. This dimension therefore reads BOTH fields
`resolve_dimension_evidence()` already computes (`evidence.disputed` and
`evidence.admissible`) directly, rather than only the latter -- the one,
narrow, documented place in this pillar where "disputed" is a positive
signal rather than an exclusion reason. No new shared-layer code was
needed for this: both fields already existed for exactly this reuse.
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

PILLAR = P.EXECUTION_MOMENTUM_PILLAR

DIMENSION_SHIPPING_VELOCITY = "shipping_velocity"
DIMENSION_GTM_MOTION_EVIDENCE = "gtm_motion_evidence"
DIMENSION_STRATEGIC_CONSISTENCY = "strategic_consistency"


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
    evidence_filter=None,  # Callable[[tuple[Claim, ...]], tuple[Claim, ...]] | None -- e.g. supersession resolution
) -> DimensionResult:
    weight = P.EXECUTION_MOMENTUM_DIMENSION_WEIGHTS[dimension]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(scoped, dimension, as_of, P.EXECUTION_MOMENTUM_STALENESS_DAYS[dimension])

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
                f"{P.EXECUTION_MOMENTUM_STALENESS_DAYS[dimension]}-day staleness bound; none is currently admissible."
            ),
        )

    if not evidence.admissible:
        return DimensionResult(
            dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            rationale="No claim is on record for this dimension.",
        )

    usable_claims = evidence.admissible
    if evidence_filter is not None:
        usable_claims = evidence_filter(evidence.admissible)
        if evidence.admissible and not usable_claims:
            return DimensionResult(
                dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
                score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
                rationale=(
                    "Admissible evidence exists but none currently represents a completed, launched event "
                    "(only announced/beta/cancelled/superseded status, or evidence outside this dimension's "
                    "recognized kind) -- announcements and plans never count as execution."
                ),
            )

    request = ClassificationRequest(
        dimension=dimension, allowed_labels=allowed_labels,
        evidence_items=to_evidence_items(usable_claims, company_display_names),
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

    cited = tuple(c for c in usable_claims if c.claim_id in response.supporting_claim_ids)
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


# --- 1. Shipping Velocity ------------------------------------------------

def _resolve_current_release_status(claims: tuple[Claim, ...]) -> dict[str, Claim]:
    """Groups product_release claims by their release's own named_entity
    and keeps only the MOST RECENT (by published_at, falling back to
    retrieved_at) claim per group as authoritative for that release's
    CURRENT status -- the supersession rule (module docstring). Returns
    {named_entity: the winning claim}, for every release regardless of
    its resolved status (callers filter to "launched" themselves)."""
    by_release: dict[str, Claim] = {}
    for c in claims:
        fact = c.structured_fact or {}
        if fact.get("kind") != "product_release":
            continue
        name = fact.get("named_entity")
        if not name:
            continue
        reference = c.published_at or c.retrieved_at
        existing = by_release.get(name)
        if existing is None:
            by_release[name] = c
            continue
        existing_reference = existing.published_at or existing.retrieved_at
        if reference > existing_reference:
            by_release[name] = c
    return by_release


def _launched_releases(claims: tuple[Claim, ...]) -> tuple[Claim, ...]:
    current = _resolve_current_release_status(claims)
    return tuple(
        c for c in current.values()
        if (c.structured_fact or {}).get("status") == "launched"
    )


@dataclass(frozen=True)
class WellBehavedShippingVelocityClassifier:
    """Counts DISTINCT launched-release claims (one representative per
    independence group -- the ledger's own dedup already collapsed
    restatements of one announcement before this classifier ever runs;
    see the module docstring's "Supersession, not silent overwriting").
    Reads only `structured_fact` -- never claim text, never a release's
    own name for anything beyond grouping/counting."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        releases: dict[str, str] = {}
        for item in request.evidence_items:
            if not item.structured_fact or item.structured_fact.get("kind") != "product_release":
                continue
            if item.structured_fact.get("status") != "launched":
                continue
            releases.setdefault(item.independence_group_id, item.claim_id)

        distinct = len(releases)
        if distinct >= P.SHIPPING_VELOCITY_RAPID_MIN_COUNT:
            return ClassificationResponse(label="RAPID", supporting_claim_ids=tuple(releases.values()))
        if distinct >= P.SHIPPING_VELOCITY_STEADY_MIN_COUNT:
            return ClassificationResponse(label="STEADY", supporting_claim_ids=tuple(releases.values()))
        return ClassificationResponse(label="INSUFFICIENT", supporting_claim_ids=())


_DEFAULT_SHIPPING_VELOCITY_MODEL = WellBehavedShippingVelocityClassifier()
_SHIPPING_VELOCITY_REQUIREMENT = requires_minimum_distinct_facts(
    {"RAPID": P.SHIPPING_VELOCITY_RAPID_MIN_COUNT, "STEADY": P.SHIPPING_VELOCITY_STEADY_MIN_COUNT}
)


def evaluate_shipping_velocity(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_SHIPPING_VELOCITY,
        allowed_labels=("INSUFFICIENT", "STEADY", "RAPID"),
        unscored_label_reasons={"INSUFFICIENT": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        score_lookup=lambda label: _score_for_label(P.SHIPPING_VELOCITY_LABEL_SCORES, label, stage),
        label_requirement_check=_SHIPPING_VELOCITY_REQUIREMENT,
        model=model or _DEFAULT_SHIPPING_VELOCITY_MODEL,
        company_display_names=company_display_names,
        evidence_filter=_launched_releases,
    )


# --- 2. Go-to-Market Motion Evidence ------------------------------------------

@dataclass(frozen=True)
class WellBehavedGTMMotionClassifier:
    """Reads `structured_fact.kind == 'gtm_evidence'` directly -- a named
    acquisition channel, a named GTM/distribution partnership, or a
    disclosed SALES/GTM-function hire (never general headcount or
    engineering hiring, which carries no such fact at all -- item 8's own
    explicit exclusion, enforced structurally, not by convention)."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        for item in request.evidence_items:
            if not item.structured_fact or item.structured_fact.get("kind") != "gtm_evidence":
                continue
            return ClassificationResponse(label="GTM_FACT_PRESENT", supporting_claim_ids=(item.claim_id,))
        return ClassificationResponse(label="NOT_ESTABLISHED", supporting_claim_ids=())


_DEFAULT_GTM_MOTION_MODEL = WellBehavedGTMMotionClassifier()
_GTM_MOTION_REQUIREMENT = requires_named_entity_fact(frozenset({"GTM_FACT_PRESENT"}))


def evaluate_gtm_motion_evidence(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_GTM_MOTION_EVIDENCE,
        allowed_labels=("NOT_ESTABLISHED", "GTM_FACT_PRESENT"),
        unscored_label_reasons={"NOT_ESTABLISHED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        score_lookup=lambda label: _score_for_label(P.GTM_MOTION_LABEL_SCORES, label, stage),
        label_requirement_check=_GTM_MOTION_REQUIREMENT,
        model=model or _DEFAULT_GTM_MOTION_MODEL,
        company_display_names=company_display_names,
    )


# --- 3. Strategic Consistency (Computed, rule-based) -----------------------
# Pure deterministic function of the ledger's OWN existing disputed/
# admissible split -- no classification model call at all, matching
# Commercial Traction's own precedent for Computed dimensions (Task 15
# §1.1) and spec Part 6.1's "no AI call" framing taken literally. See the
# module docstring's "Strategic Consistency's own architectural wrinkle"
# for why `evidence.disputed` is read as a POSITIVE signal here, uniquely
# among every dimension in this engine.
#
# Staleness (parameters.py's own comment on `strategic_consistency` /
# `STRATEGIC_CONSISTENCY_RESOLUTION_STALENESS_DAYS`): resolved with no
# ceiling at the raw-resolution layer, then the real 24-month bound is
# applied explicitly, only to the MOST RECENT statement on record -- a
# real, older statement is exactly what a "compared... over time" check
# needs, not evidence to discard, the same principle Growth Trajectory
# (Commercial Traction, Task 15) already established for its own "newer
# point only" staleness rule.

def evaluate_strategic_consistency(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
) -> DimensionResult:
    weight = P.EXECUTION_MOMENTUM_DIMENSION_WEIGHTS[DIMENSION_STRATEGIC_CONSISTENCY]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(
        scoped, DIMENSION_STRATEGIC_CONSISTENCY, as_of, P.STRATEGIC_CONSISTENCY_RESOLUTION_STALENESS_DAYS
    )

    if not evidence.all_tagged:
        return DimensionResult(
            dimension=DIMENSION_STRATEGIC_CONSISTENCY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=AvailabilityStatus.UNSCORED_NO_EVIDENCE,
            rationale="No dated public statement is on record for this dimension.",
        )

    # The real staleness rule: the MOST RECENT admissible-or-disputed
    # statement must itself be current, so the assessment is grounded in
    # reasonably current information -- older statements being compared
    # against it are never penalized for their own age.
    reference_claims = evidence.admissible + evidence.disputed
    if reference_claims:
        newest_reference = max(c.published_at or c.retrieved_at for c in reference_claims)
        if (as_of - newest_reference).days > P.EXECUTION_MOMENTUM_STALENESS_DAYS[DIMENSION_STRATEGIC_CONSISTENCY]:
            return DimensionResult(
                dimension=DIMENSION_STRATEGIC_CONSISTENCY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
                score=None, availability=AvailabilityStatus.UNSCORED_STALE,
                rationale=(
                    "The most recent dated public statement on record is older than the "
                    f"{P.EXECUTION_MOMENTUM_STALENESS_DAYS[DIMENSION_STRATEGIC_CONSISTENCY]}-day staleness bound -- "
                    "this assessment would not be grounded in current information."
                ),
            )

    # A detected, unresolved contradiction is the dimension's own real,
    # scored output -- not something to exclude. This is the one place in
    # this pillar (and, structurally, in this entire engine) `disputed`
    # evidence is read as a positive signal rather than an exclusion
    # reason (module docstring).
    if evidence.disputed:
        cited = tuple(c.claim_id for c in evidence.disputed)
        return DimensionResult(
            dimension=DIMENSION_STRATEGIC_CONSISTENCY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=P.STRATEGIC_CONSISTENCY_LABEL_SCORES["CONTAINS_CONTRADICTION"],
            availability=AvailabilityStatus.SCORABLE,
            supporting_claim_ids=cited,
            classification_label="CONTAINS_CONTRADICTION",
            confidence=compute_dimension_confidence(evidence.disputed),
            rationale="At least one pair of the company's own disclosed public statements materially conflicts.",
        )

    if len(evidence.admissible) >= 2:
        cited = tuple(c.claim_id for c in evidence.admissible)
        return DimensionResult(
            dimension=DIMENSION_STRATEGIC_CONSISTENCY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=P.STRATEGIC_CONSISTENCY_LABEL_SCORES["CONSISTENT"],
            availability=AvailabilityStatus.SCORABLE,
            supporting_claim_ids=cited,
            classification_label="CONSISTENT",
            confidence=compute_dimension_confidence(evidence.admissible),
            rationale=(
                f"{len(evidence.admissible)} distinct dated public statements are on record and none "
                "materially conflict."
            ),
        )

    if not evidence.admissible:
        return DimensionResult(
            dimension=DIMENSION_STRATEGIC_CONSISTENCY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
            score=None, availability=_reason_for_absence(evidence),
            rationale="No admissible (non-stale, non-disputed) dated public statement is on record.",
        )

    # Exactly one admissible statement -- real evidence, but spec Part
    # 3.3 explicitly requires >=2 dated statements "to compare"; a single
    # statement has nothing to be consistent or inconsistent WITH yet.
    return DimensionResult(
        dimension=DIMENSION_STRATEGIC_CONSISTENCY, pillar=PILLAR, category=DimensionCategory.COMPUTED, weight=weight,
        score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
        rationale="Only one dated public statement is on record; at least two are required to compare (insufficient history).",
    )


# --- Orchestration -----------------------------------------------------------

def evaluate_all(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
    shipping_velocity_model: ClassificationModel | None = None,
    gtm_motion_model: ClassificationModel | None = None,
) -> tuple[DimensionResult, ...]:
    return (
        evaluate_shipping_velocity(ledger, company_ref, as_of, stage, company_display_names, shipping_velocity_model),
        evaluate_gtm_motion_evidence(ledger, company_ref, as_of, stage, company_display_names, gtm_motion_model),
        evaluate_strategic_consistency(ledger, company_ref, as_of, stage, company_display_names),
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
