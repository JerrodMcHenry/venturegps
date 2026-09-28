"""
Team & Leadership pillar (Task 14; NEW_ENGINE_SPEC.md Part 3.3). The
third pillar implemented in this engine, on the exact same architecture
Product & Technology and Market Opportunity already validated (Tasks
8-13). No shared scoring philosophy, evidence ledger, classification
system, provenance system, confidence model, stage model, or
publication gate was redesigned to build this.

**The one rule that overrides every other consideration in this module:
evaluate documented, checkable team evidence, never personality,
prestige, charisma, perceived intelligence, or subjective "founder
quality."** Concretely, and non-negotiably:

  - No dimension, label, or rationale anywhere in this file scores or
    represents founder intelligence, charisma, ambition, grit, vision,
    "leadership quality," founder "strength," likelihood of success,
    personality, reputation, or perceived competence. There is no code
    path that could produce such a judgment -- the label sets below
    contain no such concept to select.
  - A prestigious employer, university, accelerator, investor, award, or
    social-media following is NEVER, by itself, evidence for any label
    here. "Former Google engineer" is admissible evidence of a specific,
    checkable prior role (Founder Relevant Experience) -- it is not
    evidence that the founder is "strong," and nothing in this module's
    scoring reads "Google" as a name that itself carries weight. The
    deterministic label->score tables (parameters.py) map only
    ADJACENT/DIRECT (a relevance classification) or
    PRIOR_VENTURE_ROLE/PRIOR_EXIT (a track-record classification) to a
    score -- never a company or institution name to a score.
  - YC participation, investment by a well-known VC, or a famous prior
    employer, standing alone with no OTHER team evidence, is
    structurally incapable of producing a score above `NONE_DISCLOSED`'s
    Unscored floor -- see `requires_named_entity_fact`
    (classification.py) and this module's own per-dimension checks,
    which require a specific, checkable, topically-connected fact, not a
    prestige signal by itself.

**Pillar boundary.** Team & Leadership measures documented facts about
the people and leadership structure of the company -- never product
quality (Product & Technology), market conditions (Market Opportunity),
or anything about revenue/customers/execution (not yet built).

**Identity resolution (spec ambiguity, Task 14 item 6 -- documented,
narrow decision).** The approved spec does not describe a mechanism for
distinguishing two different real people who happen to share a name.
This module adds one: a claim about a specific person's PRIOR
experience or track record is only usable if the ledger separately,
explicitly confirms that person's identifier (`structured_fact.
person_id`, the same deterministic stand-in for "the AI resolved this
to a specific entity" this engine already uses everywhere) as actually
affiliated with the company being assessed -- via a claim tagged
`TEAM_IDENTITY_DIMENSION`. A claim whose person cannot be confirmed
this way is never used, regardless of how well the name matches --
FAILING CLOSED on identity ambiguity, per item 6's own explicit
instruction, rather than merging on name-string similarity alone.
Leadership Composition does not need this check: a hire announcement
("X joined as CTO") names, roles, and affiliates a person in one
self-sufficient fact, unlike a separately-sourced PRIOR-history claim.

**Stage independence, per dimension (Task 14 item 8's own instruction to
document this explicitly).** Founder Relevant Experience and Public
Track Record are documented, ALREADY-HAPPENED biographical facts -- a
prior exit or a specific prior domain role means the same thing
regardless of this company's current stage, so both are flat,
stage-independent tables (the same reasoning Market Opportunity already
used, applied here to a person's past rather than the external market).
Leadership Composition is the one dimension the approved spec's own
wording legitimately supports stage sensitivity for (explicit
confirmation the founder(s) are the only leadership is a real, scorable,
non-penalized state, spec Part 3.3) -- but even there, `NONE_BEYOND_
FOUNDERS` itself is pinned to an IDENTICAL score across every stage
tier (never rewarded for smallness, never punished for a bench that
would be unreasonable at that stage); only the genuinely evidence-
bearing hire-count labels vary by tier, in the same direction Product &
Technology already established (the same fact is more remarkable, and
scores higher, at an earlier stage where it is less expected).
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
from app.evidence_engine.stage import ALL_TIERS, Stage, tier_for_stage

PILLAR = P.TEAM_LEADERSHIP_PILLAR

DIMENSION_FOUNDER_EXPERIENCE = "founder_relevant_experience"
DIMENSION_LEADERSHIP_COMPOSITION = "leadership_composition"
DIMENSION_PUBLIC_TRACK_RECORD = "public_track_record"

# Not itself one of the three scored dimensions -- a pseudo-dimension tag
# for claims that establish "this person_id is a confirmed founder/
# leadership member of this company." See module docstring, "Identity
# resolution."
TEAM_IDENTITY_DIMENSION = "team_identity"
TEAM_IDENTITY_STALENESS_DAYS = 1095  # 36 months, matching the biographical staleness bound


def _company_claims(ledger: EvidenceLedger, company_ref: str) -> EvidenceLedger:
    return EvidenceLedger.from_list([c for c in ledger.claims if c.company_ref == company_ref])


def _reason_for_absence(evidence: DimensionEvidence) -> AvailabilityStatus:
    if evidence.disputed and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_DISPUTED
    if evidence.stale and not evidence.admissible:
        return AvailabilityStatus.UNSCORED_STALE
    return AvailabilityStatus.UNSCORED_NO_EVIDENCE


def _confirmed_person_ids(ledger: EvidenceLedger, company_ref: str, as_of: date, role: str | None = None) -> frozenset[str]:
    """Resolves which person_ids are confirmed, admissible, company-
    affiliated identities as of `as_of` -- fails closed by construction:
    a person_id with no admissible team_identity claim is simply absent
    from the returned set, and every caller in this module treats
    "not in this set" identically to "identity could not be established."
    """
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(scoped, TEAM_IDENTITY_DIMENSION, as_of, TEAM_IDENTITY_STALENESS_DAYS)
    confirmed: set[str] = set()
    for claim in evidence.admissible:
        fact = claim.structured_fact or {}
        person_id = fact.get("person_id")
        if not person_id:
            continue
        if role is not None and fact.get("role") != role:
            continue
        confirmed.add(person_id)
    return frozenset(confirmed)


def _filter_to_confirmed_identity(claims: tuple[Claim, ...], confirmed_person_ids: frozenset[str]) -> tuple[Claim, ...]:
    return tuple(
        c for c in claims
        if c.structured_fact and c.structured_fact.get("person_id") in confirmed_person_ids
    )


def _score_for_label(label_table: dict[str, dict[str, float]], label: str, stage: Stage) -> float | None:
    """Same mechanism as pillars/product_technology.py's own
    _score_for_label -- most-permissive-tier fallback when stage is
    Undetermined (spec Part 4.3). Duplicated here rather than imported
    (this pillar's own private copy of an established pattern), per Task
    13/14's own "do not redesign shared infra for ordinary pillar-
    specific behavior" instruction -- flagged as a candidate for a
    future shared extraction once a fourth pillar makes the pattern's
    stability clearer, not decided here."""
    tier_scores = label_table.get(label)
    if tier_scores is None:
        return None
    if stage == Stage.UNDETERMINED:
        return max(tier_scores.values())
    tier = tier_for_stage(stage)
    if tier is None:
        return max(tier_scores.values())
    return tier_scores[tier.value]


# --- Shared per-dimension evaluation harness (pillar-local, see docstring
# --- above on why this is duplicated rather than extracted) -----------------

def _evaluate_classified_dimension(
    *,
    ledger: EvidenceLedger,
    company_ref: str,
    as_of: date,
    stage: Stage,
    dimension: str,
    allowed_labels: tuple[str, ...],
    unscored_label_reasons: dict[str, AvailabilityStatus],
    score_lookup,  # Callable[[str], float | None] -- flat or stage-aware, dimension's own choice
    label_requirement_check,
    model: ClassificationModel,
    company_display_names: tuple[str, ...],
    identity_filter=None,  # Callable[[tuple[Claim, ...]], tuple[Claim, ...]] | None
) -> DimensionResult:
    weight = P.TEAM_LEADERSHIP_DIMENSION_WEIGHTS[dimension]
    scoped = _company_claims(ledger, company_ref)
    evidence = resolve_dimension_evidence(scoped, dimension, as_of, P.TEAM_LEADERSHIP_STALENESS_DAYS[dimension])

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
                f"{P.TEAM_LEADERSHIP_STALENESS_DAYS[dimension]}-day staleness bound; none is currently admissible."
            ),
        )

    usable_claims = evidence.admissible
    if identity_filter is not None:
        identity_confirmed = identity_filter(evidence.admissible)
        if evidence.admissible and not identity_confirmed:
            return DimensionResult(
                dimension=dimension, pillar=PILLAR, category=DimensionCategory.CLASSIFIED, weight=weight,
                score=None, availability=AvailabilityStatus.UNSCORED_UNCORROBORATED,
                rationale=(
                    "Admissible evidence references a person whose affiliation with this company "
                    "could not be confirmed -- failing closed rather than matching on name alone."
                ),
            )
        usable_claims = identity_confirmed

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


# --- 1. Founder Relevant Experience ------------------------------------------

@dataclass(frozen=True)
class WellBehavedFounderExperienceClassifier:
    """Reads `structured_fact.value` (ADJACENT|DIRECT) from the identity-
    confirmed evidence it was given -- never text content, never a
    company/institution name's own prestige. The first (stable-order)
    qualifying candidate is used; this mock does not attempt to reconcile
    multiple differing claims about the same person (the documented
    "first admissible candidate wins" convention already used throughout
    this engine since Task 10)."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        for item in request.evidence_items:
            if not item.structured_fact or item.structured_fact.get("kind") != "founder_experience":
                continue
            value = item.structured_fact.get("value")
            if value in ("ADJACENT", "DIRECT"):
                return ClassificationResponse(label=value, supporting_claim_ids=(item.claim_id,))
        return ClassificationResponse(label="NONE_DISCLOSED", supporting_claim_ids=())


_DEFAULT_FOUNDER_EXPERIENCE_MODEL = WellBehavedFounderExperienceClassifier()
_FOUNDER_EXPERIENCE_REQUIREMENT = requires_named_entity_fact(frozenset({"ADJACENT", "DIRECT"}))


def evaluate_founder_relevant_experience(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    confirmed_founders = _confirmed_person_ids(ledger, company_ref, as_of, role="founder")
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_FOUNDER_EXPERIENCE,
        allowed_labels=("NONE_DISCLOSED", "ADJACENT", "DIRECT"),
        unscored_label_reasons={"NONE_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        score_lookup=lambda label: P.FOUNDER_EXPERIENCE_LABEL_SCORES.get(label),
        label_requirement_check=_FOUNDER_EXPERIENCE_REQUIREMENT,
        model=model or _DEFAULT_FOUNDER_EXPERIENCE_MODEL,
        company_display_names=company_display_names,
        identity_filter=lambda claims: _filter_to_confirmed_identity(claims, confirmed_founders),
    )


# --- 2. Leadership Composition -----------------------------------------------

@dataclass(frozen=True)
class WellBehavedLeadershipCompositionClassifier:
    """Counts DISTINCT named leadership-hire claims (one representative
    per independence group, mirroring Technical Depth Signal's own
    dedup-aware counting). A single, explicit "founders are the only
    leadership" claim is its own real, scorable outcome
    (NONE_BEYOND_FOUNDERS), never confused with "no evidence was ever
    gathered about leadership composition at all" (NOT_ESTABLISHED)."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        hires: dict[str, str] = {}
        founders_only_confirmed = False
        for item in request.evidence_items:
            if not item.structured_fact:
                continue
            kind = item.structured_fact.get("kind")
            if kind == "leadership_hire":
                hires.setdefault(item.independence_group_id, item.claim_id)
            elif kind == "founders_only_confirmed":
                founders_only_confirmed = True

        distinct = len(hires)
        if distinct >= P.LEADERSHIP_SUBSTANTIAL_HIRES_MIN_COUNT:
            return ClassificationResponse(label="SUBSTANTIAL_HIRES", supporting_claim_ids=tuple(hires.values()))
        if distinct >= P.LEADERSHIP_SOME_HIRES_MIN_COUNT:
            return ClassificationResponse(label="SOME_HIRES", supporting_claim_ids=tuple(hires.values()))
        if founders_only_confirmed:
            confirming = next(
                item.claim_id for item in request.evidence_items
                if item.structured_fact and item.structured_fact.get("kind") == "founders_only_confirmed"
            )
            return ClassificationResponse(label="NONE_BEYOND_FOUNDERS", supporting_claim_ids=(confirming,))
        return ClassificationResponse(label="NOT_ESTABLISHED", supporting_claim_ids=())


_DEFAULT_LEADERSHIP_COMPOSITION_MODEL = WellBehavedLeadershipCompositionClassifier()
_LEADERSHIP_COMPOSITION_REQUIREMENT = requires_minimum_distinct_facts(
    {"SUBSTANTIAL_HIRES": P.LEADERSHIP_SUBSTANTIAL_HIRES_MIN_COUNT, "SOME_HIRES": P.LEADERSHIP_SOME_HIRES_MIN_COUNT}
)


def evaluate_leadership_composition(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_LEADERSHIP_COMPOSITION,
        allowed_labels=("NOT_ESTABLISHED", "NONE_BEYOND_FOUNDERS", "SOME_HIRES", "SUBSTANTIAL_HIRES"),
        unscored_label_reasons={"NOT_ESTABLISHED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        score_lookup=lambda label: _score_for_label(P.LEADERSHIP_COMPOSITION_LABEL_SCORES, label, stage),
        label_requirement_check=_LEADERSHIP_COMPOSITION_REQUIREMENT,
        model=model or _DEFAULT_LEADERSHIP_COMPOSITION_MODEL,
        company_display_names=company_display_names,
        # No identity_filter: a hire announcement is self-sufficient (see
        # module docstring, "Identity resolution").
    )


# --- 3. Public Track Record ---------------------------------------------------

@dataclass(frozen=True)
class WellBehavedPublicTrackRecordClassifier:
    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        role_claim: str | None = None
        for item in request.evidence_items:
            if not item.structured_fact or item.structured_fact.get("kind") != "track_record":
                continue
            value = item.structured_fact.get("value")
            if value == "PRIOR_EXIT":
                return ClassificationResponse(label="PRIOR_EXIT", supporting_claim_ids=(item.claim_id,))
            if value == "PRIOR_VENTURE_ROLE" and role_claim is None:
                role_claim = item.claim_id
        if role_claim is not None:
            return ClassificationResponse(label="PRIOR_VENTURE_ROLE", supporting_claim_ids=(role_claim,))
        return ClassificationResponse(label="NONE_DISCLOSED", supporting_claim_ids=())


_DEFAULT_PUBLIC_TRACK_RECORD_MODEL = WellBehavedPublicTrackRecordClassifier()
_PUBLIC_TRACK_RECORD_REQUIREMENT = requires_named_entity_fact(frozenset({"PRIOR_VENTURE_ROLE", "PRIOR_EXIT"}))


def evaluate_public_track_record(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (), model: ClassificationModel | None = None,
) -> DimensionResult:
    confirmed_team = _confirmed_person_ids(ledger, company_ref, as_of, role=None)
    return _evaluate_classified_dimension(
        ledger=ledger, company_ref=company_ref, as_of=as_of, stage=stage,
        dimension=DIMENSION_PUBLIC_TRACK_RECORD,
        allowed_labels=("NONE_DISCLOSED", "PRIOR_VENTURE_ROLE", "PRIOR_EXIT"),
        unscored_label_reasons={"NONE_DISCLOSED": AvailabilityStatus.UNSCORED_NO_EVIDENCE},
        score_lookup=lambda label: P.PUBLIC_TRACK_RECORD_LABEL_SCORES.get(label),
        label_requirement_check=_PUBLIC_TRACK_RECORD_REQUIREMENT,
        model=model or _DEFAULT_PUBLIC_TRACK_RECORD_MODEL,
        company_display_names=company_display_names,
        identity_filter=lambda claims: _filter_to_confirmed_identity(claims, confirmed_team),
    )


# --- Orchestration -----------------------------------------------------------

def evaluate_all(
    ledger: EvidenceLedger, company_ref: str, as_of: date, stage: Stage,
    company_display_names: tuple[str, ...] = (),
    founder_experience_model: ClassificationModel | None = None,
    leadership_composition_model: ClassificationModel | None = None,
    public_track_record_model: ClassificationModel | None = None,
) -> tuple[DimensionResult, ...]:
    return (
        evaluate_founder_relevant_experience(
            ledger, company_ref, as_of, stage, company_display_names, founder_experience_model
        ),
        evaluate_leadership_composition(
            ledger, company_ref, as_of, stage, company_display_names, leadership_composition_model
        ),
        evaluate_public_track_record(
            ledger, company_ref, as_of, stage, company_display_names, public_track_record_model
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
