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

**No new scoring, no new gates, no overall score (Task 18's own explicit
scope).** `FullCompanyAnalysis` carries all six `PillarResult` objects
exactly as each pillar produced them -- a pillar that is withheld stays
withheld; no `Strength` is invented, averaged, or defaulted for it. Spec
Part 6.5's own "Overall Startup Power" gates (`MIN_OVERALL_COVERAGE_PCT`,
`MIN_PUBLISHABLE_PILLARS`, overall Confidence) are explicitly NOT
implemented here -- that is the next task's own scope, not this one's.
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
from app.evidence_engine.scoring import PillarResult
from app.evidence_engine.stage import Stage, determine_stage

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
    )
