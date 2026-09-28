"""
Task 18, item 12/14 -- the full six-pillar engine, assembled and run
against a deliberately diverse 7-company cohort. Produces the evaluation
matrix and cross-pillar audit summary documented in full in
`docs/methodology/NEW_ENGINE_FULL_EVALUATION.md`.

Cohort (real companies reuse their existing live_research/ evidence
unchanged; two fictional companies were added specifically to cover
categories no real-evidence fixture in this session happened to
exercise -- see each fixture module's own docstring):

  - Stripe          -- established private company, evidence-rich (5/6 pillars)
  - Notion          -- growth-stage private company, evidence-rich in Market+Product
  - Linear           -- growth-stage private company, evidence-rich in Team+Execution+Product
  - Fish Audio       -- evidence-sparse company (Product & Technology only)
  - Bullet           -- evidence-sparse company WITH a real, disputed evidence pair
  - Beacon Analytics -- FICTIONAL pre-seed startup, deliberately sparse
  - Meridian Ops     -- FICTIONAL growth-stage startup, deliberately engineered
                        cross-pillar contradictions (duplicate revenue extraction,
                        disputed customer-adoption evidence)

Method note, identical to Tasks 11-17: no paid API call was made or
required; this script performs no research of its own -- it only
assembles evidence already gathered and committed to live_research/ and
fixtures/ in prior tasks.

Run with:
    python -m app.evidence_engine.live_research.run_full_engine_cohort_evaluation
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.fixtures import beacon_analytics_fictional, meridian_ops_fictional
from app.evidence_engine.full_analysis import FullCompanyAnalysis, assemble_full_analysis
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.live_research import bullet, fish_audio, linear, notion, stripe
from app.evidence_engine.parameters import PARAMETER_VERSION

AS_OF = date(2026, 9, 28)

_COHORT = (
    ("Stripe", stripe),
    ("Notion", notion),
    ("Linear", linear),
    ("Fish Audio", fish_audio),
    ("Bullet", bullet),
    ("Beacon Analytics [fictional]", beacon_analytics_fictional),
    ("Meridian Ops [fictional]", meridian_ops_fictional),
)


def _print_matrix_row(company_label: str, analysis: FullCompanyAnalysis) -> None:
    print(f"\n=== {company_label} (stage: {analysis.stage.value}) ===")
    conf_display = analysis.company_confidence.value if analysis.company_confidence else "--"
    print(
        f"  COMPANY-LEVEL: publishable={analysis.company_publishable}  "
        f"coverage={analysis.company_coverage_pct:5.1f}%  confidence={conf_display}"
    )
    if not analysis.company_publishable:
        print(f"      withheld because: {'; '.join(analysis.company_withhold_reasons)}")
    for pr in analysis.pillar_results:
        scored = sum(1 for d in pr.dimension_results if d.score is not None)
        unscored = len(pr.dimension_results) - scored
        status = "PUBLISHED" if pr.publishable else "WITHHELD "
        strength_display = f"{pr.strength:.2f}" if pr.strength is not None else "  --  "
        disputed = [d.dimension for d in pr.dimension_results if d.availability.value == "unscored_disputed"]
        disputed_note = f" | disputed: {disputed}" if disputed else ""
        print(
            f"  {pr.pillar:28s} {status}  strength={strength_display}  coverage={pr.coverage_pct:5.1f}%  "
            f"conf={pr.confidence.value:6s}  scored={scored} unscored={unscored}{disputed_note}"
        )
        if not pr.publishable and pr.withhold_reasons:
            print(f"      withheld because: {'; '.join(pr.withhold_reasons)}")


def _print_audit_summary(analysis: FullCompanyAnalysis) -> None:
    if not analysis.cross_pillar_audit:
        print("  Cross-pillar audit: no findings.")
        return
    print(f"  Cross-pillar audit: {len(analysis.cross_pillar_audit)} finding(s)")
    for f in analysis.cross_pillar_audit:
        print(f"    [{f.severity.value.upper():7s}] {f.finding_type.value}: {f.description}")


def main() -> None:
    print(f"Task 18 full-engine cohort evaluation -- parameter version {PARAMETER_VERSION}")
    print(f"As-of date: {AS_OF.isoformat()}")
    print(f"Cohort size: {len(_COHORT)} companies")

    total_errors = 0
    total_warnings = 0
    total_info = 0

    for label, module in _COHORT:
        ledger = EvidenceLedger.from_list(module.CLAIMS)
        analysis = assemble_full_analysis(
            ledger, module.COMPANY_REF, AS_OF, module.COMPANY_DISPLAY_NAMES,
        )
        _print_matrix_row(label, analysis)
        _print_audit_summary(analysis)
        total_errors += len(analysis.audit_errors)
        total_warnings += len(analysis.audit_warnings)
        total_info += len(analysis.cross_pillar_audit) - len(analysis.audit_errors) - len(analysis.audit_warnings)

    print("\n" + "=" * 74)
    print(f"Cohort-wide audit totals: {total_errors} ERROR, {total_warnings} WARNING, {total_info} INFO")
    if total_errors:
        print("*** ERROR-severity findings indicate a genuine implementation defect -- see the report. ***")


if __name__ == "__main__":
    main()
