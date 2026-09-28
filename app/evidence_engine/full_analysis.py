"""
Full-engine assembly (Task 18). The narrowest orchestration layer that
runs one canonical `EvidenceLedger` through all six independently-built
pillar evaluators and returns one coherent, typed, auditable result --
`FullCompanyAnalysis`. This module contains NO scoring logic of its own:
every dimension result, every pillar Strength/Coverage/Confidence, and
every publication decision is produced entirely by the six pillars'
own, already-validated `evaluate_pillar_for_company()` functions
(Tasks 8-17), called here exactly as every pillar's own sanity-check
script has already called them individually since Task 13. This module's
only two responsibilities are (1) resolving stage ONCE, shared by
construction across all six pillars, and (2) running the read-only
cross-pillar audit (`cross_pillar_audit.py`) over the six results.

**Single-stage resolution (item 10).** `determine_stage()` is called
exactly once per analysis; the resulting `Stage` value is passed by
value to all six pillar evaluators. There is no code path in this module
through which two pillars could ever see a different `Stage` for the
same analysis -- this is a structural guarantee of the call shape below,
not a runtime check (though `test_full_analysis.py` still verifies it
directly, since a structural guarantee is only as good as the code that
actually implements it).

**Company-level aggregation (Task 19).** `FullCompanyAnalysis` carries all
six `PillarResult` objects exactly as each pillar produced them -- a
pillar that is withheld stays withheld; no pillar `Strength` is invented,
averaged, or defaulted for it. On top of that, this module now computes
three company-level values, all pure functions of the six `PillarResult`s
(the same firewall discipline spec Part 6.6 already requires at pillar
level, extended one level up):

  - **`company_coverage_pct`** -- a `PILLAR_WEIGHTS`-weighted average of
    every pillar's own `coverage_pct` (published or withheld -- a
    withheld pillar's own partial coverage still contributes; Task 19
    item 10's own "a withheld pillar still contains information about
    what was assessable"). Always computed, never gated, never depends on
    Strength.
  - **`company_confidence`** -- a `PILLAR_WEIGHTS`-weighted-ordinal
    average of only the PUBLISHED pillars' own Confidence (never a
    withheld pillar's default-Low placeholder, which would conflate "no
    evidence" with "unreliable evidence" -- two different concepts).
    `None` when zero pillars are published -- there is no evidence whose
    reliability could be assessed at all.
  - **`company_publishable`** / **`company_withhold_reasons`** -- the
    same two-gate shape spec Part 6.5 already describes
    (`MIN_OVERALL_COVERAGE_PCT`, `MIN_PUBLISHABLE_PILLARS`), scaled up
    from the identical, already-proven pillar-level gate 1/gate 2 pattern
    (spec Part 6.2). Governs only whether the company-level Coverage/
    Confidence picture is considered adequate to present as coherent --
    it does NOT gate access to the numbers themselves, which are always
    visible (spec Design Principle 9: never collapse to a blank result).

**Deliberately NO overall 0-100 Strength.** Task 19's own explicit
question ("should VentureGPS expose a single overall score") was analyzed
and answered **no, not yet** -- see
`docs/methodology/NEW_ENGINE_CALIBRATION_RESULTS.md` §8 for the full
reasoning (in short: `PILLAR_WEIGHTS` remain exactly as CALIBRATION
REQUIRED as every other number in this engine, and the real cohort's own
thinness -- only one company reaches even 5 of 6 published pillars --
does not yet support the added precision, and therefore the added risk of
misreading, a single aggregated number would carry). This is an accepted,
documented Task 19 outcome, not a placeholder for a number this module
merely hasn't gotten around to computing yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.evidence_engine import parameters as P
from app.evidence_engine.cross_pillar_audit import AuditFinding, AuditSeverity, run_cross_pillar_audit
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.pillars import (
    commercial_traction,
    execution_momentum,
    financial_funding,
    market_opportunity,
    product_technology,
    team_leadership,
)
from app.evidence_engine.scoring import ConfidenceLevel, PillarResult
from app.evidence_engine.stage import Stage, determine_stage

# Company-level confidence ordinal mapping -- a pillar-local (here,
# orchestrator-local) copy of the identical pattern `scoring.py::
# compute_pillar_confidence` already uses internally, duplicated rather
# than imported per this engine's own "pillar-local duplication over
# cross-module coupling" discipline (the same reason every pillar keeps
# its own private `_score_for_label` rather than importing a shared one).
_CONFIDENCE_ORDER = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MEDIUM: 1, ConfidenceLevel.HIGH: 2}
_ORDER_TO_CONFIDENCE = {v: k for k, v in _CONFIDENCE_ORDER.items()}

# Order matches spec Part 3.3's own table order -- not otherwise
# significant (each pillar is evaluated against the identical ledger and
# stage regardless of order; `test_full_analysis.py` confirms result
# order does not affect any individual pillar's own outcome).
_PILLAR_MODULES = (
    market_opportunity,
    product_technology,
    team_leadership,
    commercial_traction,
    execution_momentum,
    financial_funding,
)


@dataclass(frozen=True)
class FullCompanyAnalysis:
    """One complete, coherent, auditable six-pillar analysis of a single
    company from one canonical evidence ledger. Deliberately carries NO
    overall 0-100 score, letter grade, ranking, or pass/fail verdict --
    see the module docstring."""

    company_ref: str
    company_display_names: tuple[str, ...]

    # Resolved ONCE (module docstring), shared by every pillar below.
    # `Stage.UNDETERMINED` is preserved and reported as such -- never
    # silently defaulted to any single real stage (spec Part 4.1).
    stage: Stage

    # `as_of`: the evidence-cutoff reference date used for every
    # staleness calculation across all six pillars (identical to what
    # every pillar's own sanity-check script has always passed).
    # `generated_at`: the wall-clock date this FullCompanyAnalysis object
    # was actually assembled -- a genuinely distinct concept (an old
    # `as_of` can be re-run today to reproduce a historical view).
    as_of: date
    generated_at: date

    parameter_version: str

    # Company-scoped claim count in the ledger passed to this analysis
    # -- a summary, not a substitute for the full ledger itself.
    total_claims_in_ledger: int

    # Exactly six results, one per pillar, each self-identifying via its
    # own `.pillar` field (the same nested-tuple convention every
    # `PillarResult.dimension_results` already uses for its own
    # dimensions) -- a withheld pillar's own `PillarResult` is included
    # exactly as produced (`strength=None`, `publishable=False`,
    # `withhold_reasons` populated), never omitted.
    pillar_results: tuple[PillarResult, ...]

    # Read-only, deterministic cross-pillar verification findings
    # (cross_pillar_audit.py) -- never fed back into any pillar's score.
    cross_pillar_audit: tuple[AuditFinding, ...]

    # A materialized, top-level convenience view for quick auditability
    # -- every claim_id cited by ANY dimension result in ANY pillar,
    # computed once at assembly time directly from the six PillarResults
    # above (never an independent source of truth that could drift).
    all_cited_claim_ids: frozenset[str] = field(default_factory=frozenset)

    # --- Company-level aggregation (Task 19; module docstring) -----------
    # Always computed, never depends on any pillar's own Strength (the
    # firewall property, extended one level up). See `compute_company_
    # coverage_pct()` / `compute_company_confidence()` /
    # `evaluate_company_publishability()` below for the exact formulas.
    company_coverage_pct: float = 0.0
    company_confidence: ConfidenceLevel | None = None
    company_publishable: bool = False
    company_withhold_reasons: tuple[str, ...] = field(default_factory=tuple)

    def pillar(self, pillar_name: str) -> PillarResult | None:
        """Look up one pillar's own result by its exact `PILLAR` name
        (e.g. "Product & Technology"). Returns None if no such pillar
        name exists among the six (a caller error, not a withheld
        pillar -- a withheld pillar's own PillarResult is still present
        here, just with publishable=False)."""
        for pr in self.pillar_results:
            if pr.pillar == pillar_name:
                return pr
        return None

    @property
    def published_pillars(self) -> tuple[PillarResult, ...]:
        return tuple(pr for pr in self.pillar_results if pr.publishable)

    @property
    def withheld_pillars(self) -> tuple[PillarResult, ...]:
        return tuple(pr for pr in self.pillar_results if not pr.publishable)

    @property
    def audit_errors(self) -> tuple[AuditFinding, ...]:
        return tuple(f for f in self.cross_pillar_audit if f.severity == AuditSeverity.ERROR)

    @property
    def audit_warnings(self) -> tuple[AuditFinding, ...]:
        return tuple(f for f in self.cross_pillar_audit if f.severity == AuditSeverity.WARNING)


def compute_company_coverage_pct(pillar_results: tuple[PillarResult, ...]) -> float:
    """`PILLAR_WEIGHTS`-weighted average of every pillar's own
    `coverage_pct` -- published or withheld, a withheld pillar's own
    partial coverage still contributes (module docstring). Never reads
    any pillar's own Strength or Confidence (firewall property, spec
    Part 6.6, extended one level up) -- a pure function of coverage_pct
    values and the fixed PILLAR_WEIGHTS only."""
    total = sum(P.PILLAR_WEIGHTS.get(pr.pillar, 0.0) * pr.coverage_pct for pr in pillar_results)
    return round(total, 1)


def compute_company_confidence(pillar_results: tuple[PillarResult, ...]) -> ConfidenceLevel | None:
    """`PILLAR_WEIGHTS`-weighted-ordinal average of only the PUBLISHED
    pillars' own Confidence (module docstring -- a withheld pillar's
    default-Low placeholder is deliberately excluded, since "no evidence"
    and "unreliable evidence" are different concepts and company
    Confidence must answer only the second). `None` when zero pillars
    are published. Never reads any pillar's own Strength or
    coverage_pct (firewall property)."""
    published = [pr for pr in pillar_results if pr.publishable]
    if not published:
        return None
    total_weight = sum(P.PILLAR_WEIGHTS.get(pr.pillar, 0.0) for pr in published)
    if total_weight <= 0:
        return None
    weighted_ordinal = sum(
        _CONFIDENCE_ORDER[pr.confidence] * P.PILLAR_WEIGHTS.get(pr.pillar, 0.0) for pr in published
    ) / total_weight
    rounded = max(0, min(2, round(weighted_ordinal)))
    return _ORDER_TO_CONFIDENCE[rounded]


def evaluate_company_publishability(
    pillar_results: tuple[PillarResult, ...], company_coverage_pct: float,
) -> tuple[bool, tuple[str, ...]]:
    """The company-level analogue of `scoring.py::evaluate_pillar()`'s own
    two-gate shape (spec Part 6.2), scaled up per spec Part 6.5's own
    already-described structure. Gate 1: weighted company coverage clears
    `MIN_OVERALL_COVERAGE_PCT`. Gate 2: at least `MIN_PUBLISHABLE_PILLARS`
    pillars independently cleared their OWN pillar-level gates already --
    this is what specifically prevents "two convenient pillars, four
    silently unavailable" (Task 19 item 12); a company cannot reach this
    gate through coverage weight alone if too few pillars actually
    published. A known, accepted edge case this combination does not
    fully close (two maximally-weighted, maximally-covered pillars alone
    could mathematically approach the coverage floor while still only
    reaching MIN_PUBLISHABLE_PILLARS) is documented in the calibration
    results report, not silently ignored."""
    published_count = sum(1 for pr in pillar_results if pr.publishable)
    reasons: list[str] = []
    if company_coverage_pct < P.MIN_OVERALL_COVERAGE_PCT:
        reasons.append(
            f"company-level weighted coverage {company_coverage_pct}% < floor {P.MIN_OVERALL_COVERAGE_PCT}%"
        )
    if published_count < P.MIN_PUBLISHABLE_PILLARS:
        reasons.append(
            f"only {published_count} published pillar(s) < floor {P.MIN_PUBLISHABLE_PILLARS}"
        )
    return (not reasons, tuple(reasons))


def assemble_full_analysis(
    ledger: EvidenceLedger,
    company_ref: str,
    as_of: date,
    company_display_names: tuple[str, ...] = (),
    generated_at: date | None = None,
    pillar_model_overrides: dict[str, dict[str, object]] | None = None,
) -> FullCompanyAnalysis:
    """The one orchestration entry point. `pillar_model_overrides`, keyed
    by exact pillar name, is an escape hatch for tests that need to
    inject a specific mock/adversarial classification model into one
    pillar's own dimension evaluator (e.g. to prove the orchestrator
    withholds gracefully when one pillar's classifier crashes) -- never
    used in ordinary cohort evaluation, where every pillar uses its own
    default `WellBehaved*` models exactly as every prior task's sanity
    checks already have."""
    overrides = pillar_model_overrides or {}

    # Resolved exactly once (module docstring, "Single-stage resolution").
    stage = determine_stage(ledger, company_ref, as_of)

    pillar_results = tuple(
        module.evaluate_pillar_for_company(
            ledger, company_ref, as_of, stage, company_display_names,
            **overrides.get(module.PILLAR, {}),
        )
        for module in _PILLAR_MODULES
    )

    all_cited = frozenset(
        cid
        for pr in pillar_results
        for d in pr.dimension_results
        for cid in d.supporting_claim_ids
    )

    audit = run_cross_pillar_audit(ledger, pillar_results, as_of)

    total_claims = sum(1 for c in ledger.claims if c.company_ref == company_ref)

    company_coverage_pct = compute_company_coverage_pct(pillar_results)
    company_confidence = compute_company_confidence(pillar_results)
    company_publishable, company_withhold_reasons = evaluate_company_publishability(
        pillar_results, company_coverage_pct
    )

    return FullCompanyAnalysis(
        company_ref=company_ref,
        company_display_names=company_display_names,
        stage=stage,
        as_of=as_of,
        generated_at=generated_at or date.today(),
        parameter_version=P.PARAMETER_VERSION,
        total_claims_in_ledger=total_claims,
        pillar_results=pillar_results,
        cross_pillar_audit=audit,
        all_cited_claim_ids=all_cited,
        company_coverage_pct=company_coverage_pct,
        company_confidence=company_confidence,
        company_publishable=company_publishable,
        company_withhold_reasons=company_withhold_reasons,
    )
