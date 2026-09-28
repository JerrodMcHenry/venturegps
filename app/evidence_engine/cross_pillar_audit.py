"""
Cross-pillar audit (Task 18). Runs AFTER all six pillars have been
independently evaluated against one shared, canonical `EvidenceLedger` --
this module never re-derives a score, never changes a `DimensionResult`
or `PillarResult`, and never feeds back into scoring. It is a read-only,
deterministic verification pass over the six pillars' own already-
computed outputs, re-checking invariants the architecture is SUPPOSED to
already guarantee (a defense-in-depth regression net, per Task 18 item
6's own "prefer structured audit findings over logging-only warnings")
plus one genuinely new cross-pillar-only check no single pillar could
ever perform on its own: detecting when two DIFFERENT claims, cited by
DIFFERENT pillars, independently describe what looks like the SAME
real-world fact with conflicting numbers (spec Part 3.1's own
duplicate-extraction risk, made concrete and checkable).

**Legitimate reuse vs. accidental duplication (item 5).** A single claim
(one `claim_id`) cited by more than one pillar's dimensions is EXPECTED
and legitimate -- the exact mechanism `assessment_criteria` tagging
already provides (Commercial Traction's Disclosed Scale / Financial &
Funding's Revenue Disclosure is the one real, implemented example, Task
17). This is reported as `INFO` severity: visible and auditable, never
treated as a defect. Two DIFFERENT claims describing what is apparently
the same fact, cited by different pillars, with materially different
numbers, and never linked via `contradicts` -- that is the accidental
case, reported as `WARNING`.

Every other check here is a genuine architectural invariant that should
be structurally impossible given the rest of this engine's own design
(disputed-claim exclusion, `verify_traceability()`, the Strength/
Coverage/Confidence firewall, single-stage-resolution). If any of them
ever fires, it indicates a real implementation bug, not a calibration
question -- reported as `ERROR`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from app.evidence_engine import parameters as P
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim, SupportStatus
from app.evidence_engine.scoring import (
    AvailabilityStatus,
    PillarResult,
    compute_pillar_strength,
    verify_traceability,
)


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AuditFindingType(str, Enum):
    CANONICAL_CLAIM_REUSED_ACROSS_PILLARS = "canonical_claim_reused_across_pillars"
    POSSIBLE_DUPLICATE_EXTRACTION_ACROSS_PILLARS = "possible_duplicate_extraction_across_pillars"
    CONTRADICTORY_FACTS_USED_SIMULTANEOUSLY = "contradictory_facts_used_simultaneously"
    DISPUTED_EVIDENCE_USED = "disputed_evidence_used_where_it_should_be_excluded"
    STALE_EVIDENCE_USED = "stale_evidence_used_where_prohibited"
    UNSUPPORTED_DIMENSION_RESULT = "unsupported_dimension_result"
    STRENGTH_INCONSISTENT_WITH_SCORABLE_DIMENSIONS = "strength_inconsistent_with_scorable_dimensions"
    WITHHELD_PILLAR_HAS_NUMERIC_STRENGTH = "withheld_pillar_has_numeric_strength"
    PUBLISHED_PILLAR_MISSING_STRENGTH = "published_pillar_missing_strength"


@dataclass(frozen=True)
class AuditFinding:
    finding_type: AuditFindingType
    severity: AuditSeverity
    description: str
    related_claim_ids: tuple[str, ...] = ()
    related_pillars: tuple[str, ...] = ()
    related_dimensions: tuple[str, ...] = ()


_SEVERITY_ORDER = {AuditSeverity.ERROR: 0, AuditSeverity.WARNING: 1, AuditSeverity.INFO: 2}

# Merged, generic view of every pillar's own dimension-weight and
# staleness tables -- built directly from the same parameters.py values
# each pillar's own evaluator already uses, never re-deriving pillar
# logic (item 3's own "do not copy pillar logic into the orchestrator").
_DIMENSION_TO_PILLAR: dict[str, str] = {
    **{d: "Product & Technology" for d in P.PRODUCT_TECHNOLOGY_DIMENSION_WEIGHTS},
    **{d: "Market Opportunity" for d in P.MARKET_OPPORTUNITY_DIMENSION_WEIGHTS},
    **{d: "Team & Leadership" for d in P.TEAM_LEADERSHIP_DIMENSION_WEIGHTS},
    **{d: "Commercial Traction" for d in P.COMMERCIAL_TRACTION_DIMENSION_WEIGHTS},
    **{d: "Execution & Momentum" for d in P.EXECUTION_MOMENTUM_DIMENSION_WEIGHTS},
    **{d: "Financial & Funding Signals" for d in P.FINANCIAL_FUNDING_DIMENSION_WEIGHTS},
}

_DIMENSION_TO_STALENESS_DAYS: dict[str, int] = {
    **P.PRODUCT_TECHNOLOGY_STALENESS_DAYS,
    **P.MARKET_OPPORTUNITY_STALENESS_DAYS,
    **P.TEAM_LEADERSHIP_STALENESS_DAYS,
    **P.COMMERCIAL_TRACTION_STALENESS_DAYS,
    **P.EXECUTION_MOMENTUM_STALENESS_DAYS,
    **P.FINANCIAL_FUNDING_STALENESS_DAYS,
}

# Dimensions whose own, documented staleness rule is NOT a blanket
# per-claim bound (Commercial Traction's Growth Trajectory, Task 15;
# Execution & Momentum's Strategic Consistency, Task 16; Financial &
# Funding's Funding History, Task 17 -- each has its own, already-tested
# "newer point only" or "no bound at all" resolution). The generic
# staleness check below is skipped for these; each pillar's own
# dedicated regression tests already verify their own correct behavior.
_STALENESS_EXCEPTION_DIMENSIONS = frozenset({"growth_trajectory", "strategic_consistency", "funding_history"})

# Money-metric family used for the duplicate-extraction-across-pillars
# check -- the same `traction_metric` shape Commercial Traction and
# Financial & Funding Signals both read (Task 15/17).
_MONEY_METRICS = frozenset({"revenue", "arr", "gmv", "bookings"})
_DUPLICATE_EXTRACTION_PERIOD_WINDOW_DAYS = 120
_DUPLICATE_EXTRACTION_AMOUNT_TOLERANCE_PCT = 15.0


def _claims_by_id(ledger: EvidenceLedger) -> dict[str, Claim]:
    return {c.claim_id: c for c in ledger.claims}


def _all_cited(pillar_results: tuple[PillarResult, ...]):
    """Yields (pillar_name, dimension, claim_id) for every citation across
    every pillar's every dimension result."""
    for pr in pillar_results:
        for d in pr.dimension_results:
            for cid in d.supporting_claim_ids:
                yield pr.pillar, d.dimension, cid


def _check_claim_reuse(pillar_results: tuple[PillarResult, ...]) -> list[AuditFinding]:
    by_claim: dict[str, set[str]] = {}
    for pillar, _dimension, cid in _all_cited(pillar_results):
        by_claim.setdefault(cid, set()).add(pillar)

    findings: list[AuditFinding] = []
    for claim_id, pillars in by_claim.items():
        if len(pillars) > 1:
            findings.append(AuditFinding(
                finding_type=AuditFindingType.CANONICAL_CLAIM_REUSED_ACROSS_PILLARS,
                severity=AuditSeverity.INFO,
                description=(
                    f"Claim {claim_id!r} is cited by {len(pillars)} different pillars "
                    f"({', '.join(sorted(pillars))}) -- legitimate canonical evidence reuse "
                    "via assessment_criteria tagging, not a duplicate extraction."
                ),
                related_claim_ids=(claim_id,),
                related_pillars=tuple(sorted(pillars)),
            ))
    return findings


def _parse_money_point(claim: Claim) -> tuple[str, float, date] | None:
    fact = claim.structured_fact or {}
    if fact.get("kind") != "traction_metric":
        return None
    metric = fact.get("metric")
    if metric not in _MONEY_METRICS:
        return None
    try:
        amount = float(fact.get("amount", ""))
        period = date.fromisoformat(fact.get("period_date", ""))
    except (TypeError, ValueError):
        return None
    return metric, amount, period


def _check_possible_duplicate_extraction(ledger: EvidenceLedger, pillar_results: tuple[PillarResult, ...]) -> list[AuditFinding]:
    """The one genuinely cross-pillar-only check: two DIFFERENT cited
    claims, from DIFFERENT pillars, describing the same metric for
    overlapping periods with materially different amounts, never linked
    via `contradicts`. Each pillar only ever sees its own claims, so only
    an audit layer spanning all six can catch this (module docstring)."""
    claims_by_id = _claims_by_id(ledger)
    cited_by_pillar: dict[str, list[tuple[str, str, Claim]]] = {}
    for pillar, dimension, cid in _all_cited(pillar_results):
        claim = claims_by_id.get(cid)
        if claim is None:
            continue
        point = _parse_money_point(claim)
        if point is None:
            continue
        cited_by_pillar.setdefault(pillar, []).append((dimension, cid, claim))

    findings: list[AuditFinding] = []
    seen_pairs: set[frozenset[str]] = set()
    pillars = sorted(cited_by_pillar)
    for i, pillar_a in enumerate(pillars):
        for pillar_b in pillars[i + 1:]:
            for dim_a, cid_a, claim_a in cited_by_pillar[pillar_a]:
                point_a = _parse_money_point(claim_a)
                for dim_b, cid_b, claim_b in cited_by_pillar[pillar_b]:
                    if cid_a == cid_b:
                        continue  # the SAME claim cited by both -- legitimate reuse, handled above
                    point_b = _parse_money_point(claim_b)
                    if point_a is None or point_b is None:
                        continue
                    metric_a, amount_a, period_a = point_a
                    metric_b, amount_b, period_b = point_b
                    if metric_a != metric_b:
                        continue
                    if abs((period_a - period_b).days) > _DUPLICATE_EXTRACTION_PERIOD_WINDOW_DAYS:
                        continue
                    # Already properly linked as a disputed conflict --
                    # that is the CORRECT, existing mechanism working,
                    # not an unnoticed duplicate.
                    if cid_b in claim_a.contradicts or cid_a in claim_b.contradicts:
                        continue
                    larger, smaller = max(amount_a, amount_b), min(amount_a, amount_b)
                    if smaller <= 0:
                        continue
                    pct_diff = ((larger - smaller) / smaller) * 100
                    if pct_diff < _DUPLICATE_EXTRACTION_AMOUNT_TOLERANCE_PCT:
                        continue
                    pair_key = frozenset({cid_a, cid_b})
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    findings.append(AuditFinding(
                        finding_type=AuditFindingType.POSSIBLE_DUPLICATE_EXTRACTION_ACROSS_PILLARS,
                        severity=AuditSeverity.WARNING,
                        description=(
                            f"Claims {cid_a!r} ({pillar_a}/{dim_a}, {metric_a}={amount_a:,.0f}) and "
                            f"{cid_b!r} ({pillar_b}/{dim_b}, {metric_b}={amount_b:,.0f}) describe the same "
                            f"metric for overlapping periods ({pct_diff:.0f}% apart) but are neither the same "
                            "claim (legitimate reuse) nor linked via `contradicts` (a recognized conflict) -- "
                            "possible unnoticed duplicate extraction of the same underlying fact."
                        ),
                        related_claim_ids=(cid_a, cid_b),
                        related_pillars=(pillar_a, pillar_b),
                        related_dimensions=(dim_a, dim_b),
                    ))
    return findings


def _check_contradictory_facts_used_simultaneously(ledger: EvidenceLedger, pillar_results: tuple[PillarResult, ...]) -> list[AuditFinding]:
    claims_by_id = _claims_by_id(ledger)
    cited_ids = {cid for _p, _d, cid in _all_cited(pillar_results)}
    findings: list[AuditFinding] = []
    checked: set[frozenset[str]] = set()
    for cid in cited_ids:
        claim = claims_by_id.get(cid)
        if claim is None or not claim.contradicts:
            continue
        for other_id in claim.contradicts:
            if other_id in cited_ids:
                pair_key = frozenset({cid, other_id})
                if pair_key in checked:
                    continue
                checked.add(pair_key)
                findings.append(AuditFinding(
                    finding_type=AuditFindingType.CONTRADICTORY_FACTS_USED_SIMULTANEOUSLY,
                    severity=AuditSeverity.ERROR,
                    description=(
                        f"Claims {cid!r} and {other_id!r} are marked as mutually contradicting, but both "
                        "were used as scoring evidence in this analysis -- should be structurally impossible "
                        "given disputed-claim exclusion."
                    ),
                    related_claim_ids=(cid, other_id),
                ))
    return findings


def _check_disputed_evidence_used(ledger: EvidenceLedger, pillar_results: tuple[PillarResult, ...]) -> list[AuditFinding]:
    claims_by_id = _claims_by_id(ledger)
    findings: list[AuditFinding] = []
    for pr in pillar_results:
        for d in pr.dimension_results:
            # The one documented, deliberate exception (module docstring
            # / execution_momentum.py's own): Strategic Consistency's
            # CONTAINS_CONTRADICTION verdict legitimately cites disputed
            # claims as its own positive evidence.
            if d.dimension == "strategic_consistency" and d.classification_label == "CONTAINS_CONTRADICTION":
                continue
            for cid in d.supporting_claim_ids:
                claim = claims_by_id.get(cid)
                if claim is not None and claim.support_status == SupportStatus.DISPUTED:
                    findings.append(AuditFinding(
                        finding_type=AuditFindingType.DISPUTED_EVIDENCE_USED,
                        severity=AuditSeverity.ERROR,
                        description=(
                            f"{pr.pillar}/{d.dimension} cites disputed claim {cid!r} as scoring evidence -- "
                            "disputed claims should always be excluded from admissible evidence."
                        ),
                        related_claim_ids=(cid,), related_pillars=(pr.pillar,), related_dimensions=(d.dimension,),
                    ))
    return findings


def _check_stale_evidence_used(ledger: EvidenceLedger, pillar_results: tuple[PillarResult, ...], as_of: date) -> list[AuditFinding]:
    claims_by_id = _claims_by_id(ledger)
    findings: list[AuditFinding] = []
    for pr in pillar_results:
        for d in pr.dimension_results:
            if d.availability != AvailabilityStatus.SCORABLE:
                continue
            if d.dimension in _STALENESS_EXCEPTION_DIMENSIONS:
                continue
            bound = _DIMENSION_TO_STALENESS_DAYS.get(d.dimension)
            if bound is None:
                continue
            for cid in d.supporting_claim_ids:
                claim = claims_by_id.get(cid)
                if claim is None:
                    continue
                reference = claim.published_at or claim.retrieved_at
                age_days = (as_of - reference).days
                if age_days > bound:
                    findings.append(AuditFinding(
                        finding_type=AuditFindingType.STALE_EVIDENCE_USED,
                        severity=AuditSeverity.ERROR,
                        description=(
                            f"{pr.pillar}/{d.dimension} cites claim {cid!r}, which is {age_days} days old, "
                            f"beyond this dimension's own {bound}-day staleness bound."
                        ),
                        related_claim_ids=(cid,), related_pillars=(pr.pillar,), related_dimensions=(d.dimension,),
                    ))
    return findings


def _check_traceability(ledger: EvidenceLedger, pillar_results: tuple[PillarResult, ...]) -> list[AuditFinding]:
    claim_ids = frozenset(c.claim_id for c in ledger.claims)
    findings: list[AuditFinding] = []
    for pr in pillar_results:
        for d in pr.dimension_results:
            violations = verify_traceability(d, claim_ids)
            for v in violations:
                findings.append(AuditFinding(
                    finding_type=AuditFindingType.UNSUPPORTED_DIMENSION_RESULT,
                    severity=AuditSeverity.ERROR,
                    description=f"{pr.pillar}/{d.dimension}: {v}",
                    related_pillars=(pr.pillar,), related_dimensions=(d.dimension,),
                ))
    return findings


def _check_strength_and_publication_invariants(pillar_results: tuple[PillarResult, ...]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for pr in pillar_results:
        # compute_pillar_strength() is deliberately GATE-BLIND (spec Part
        # 6.6's own firewall property -- it is a pure weighted average of
        # whatever IS scorable, with no knowledge of the two publication
        # gates). A withheld pillar's own `strength` is correctly forced
        # to None by `evaluate_pillar()` even when compute_pillar_
        # strength() alone would return a real number from a single
        # scorable dimension that simply didn't clear gate 2 -- so this
        # recomputation is only a meaningful check when the pillar
        # actually published; the withheld case is checked separately
        # below (WITHHELD_PILLAR_HAS_NUMERIC_STRENGTH).
        if pr.publishable:
            recomputed = compute_pillar_strength(pr.dimension_results)
            if recomputed != pr.strength:
                findings.append(AuditFinding(
                    finding_type=AuditFindingType.STRENGTH_INCONSISTENT_WITH_SCORABLE_DIMENSIONS,
                    severity=AuditSeverity.ERROR,
                    description=(
                        f"{pr.pillar}'s own reported Strength ({pr.strength}) does not match an independent "
                        f"recomputation from its own scorable dimensions alone ({recomputed})."
                    ),
                    related_pillars=(pr.pillar,),
                ))
        if not pr.publishable and pr.strength is not None:
            findings.append(AuditFinding(
                finding_type=AuditFindingType.WITHHELD_PILLAR_HAS_NUMERIC_STRENGTH,
                severity=AuditSeverity.ERROR,
                description=f"{pr.pillar} is withheld (publishable=False) but reports a numeric Strength ({pr.strength}).",
                related_pillars=(pr.pillar,),
            ))
        if pr.publishable and pr.strength is None:
            findings.append(AuditFinding(
                finding_type=AuditFindingType.PUBLISHED_PILLAR_MISSING_STRENGTH,
                severity=AuditSeverity.ERROR,
                description=f"{pr.pillar} is published (publishable=True) but has no numeric Strength.",
                related_pillars=(pr.pillar,),
            ))
    return findings


def run_cross_pillar_audit(
    ledger: EvidenceLedger, pillar_results: tuple[PillarResult, ...], as_of: date,
) -> tuple[AuditFinding, ...]:
    """The one entry point. Read-only over the ledger and the six
    already-computed pillar results -- never mutates either, never feeds
    back into scoring."""
    findings: list[AuditFinding] = []
    findings.extend(_check_claim_reuse(pillar_results))
    findings.extend(_check_possible_duplicate_extraction(ledger, pillar_results))
    findings.extend(_check_contradictory_facts_used_simultaneously(ledger, pillar_results))
    findings.extend(_check_disputed_evidence_used(ledger, pillar_results))
    findings.extend(_check_stale_evidence_used(ledger, pillar_results, as_of))
    findings.extend(_check_traceability(ledger, pillar_results))
    findings.extend(_check_strength_and_publication_invariants(pillar_results))
    findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], f.finding_type.value, f.related_claim_ids))
    return tuple(findings)
