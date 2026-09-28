"""
Task 16, item 15 -- a SMALL Execution & Momentum sanity check against
real evidence, not another calibration project. Reuses Stripe and Linear
from Tasks 11-15, with a small amount of additional, genuinely-researched
Execution & Momentum evidence added to their live_research data (see each
file's own "Task 16 addition").

Run with:
    python -m app.evidence_engine.live_research.run_execution_momentum_sanity_check
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.live_research import linear, stripe
from app.evidence_engine.parameters import PARAMETER_VERSION
from app.evidence_engine.pillars.execution_momentum import evaluate_pillar_for_company
from app.evidence_engine.scoring import PillarResult
from app.evidence_engine.stage import determine_stage

AS_OF = date(2026, 9, 28)


def _print_pillar(label: str, pillar_result: PillarResult) -> None:
    print(f"\n=== {label} — Execution & Momentum ===")
    print(f"Publishable: {pillar_result.publishable}")
    print(f"Strength:    {pillar_result.strength if pillar_result.strength is not None else 'WITHHELD (None)'}")
    print(f"Coverage:    {pillar_result.coverage_pct}%")
    print(f"Confidence:  {pillar_result.confidence.value}")
    if pillar_result.withhold_reasons:
        print("Withheld because:")
        for reason in pillar_result.withhold_reasons:
            print(f"  - {reason}")
    print("Dimensions:")
    for d in pillar_result.dimension_results:
        score_display = d.score if d.score is not None else "Unscored"
        label_display = f" [{d.classification_label}]" if d.classification_label else ""
        claims_display = ", ".join(d.supporting_claim_ids) or "(none)"
        print(f"  - {d.dimension:22s} {d.availability.value:24s} score={score_display}{label_display} cites=[{claims_display}]")
        print(f"      {d.rationale}")


def main() -> None:
    print(f"Task 16 sanity check -- parameter version {PARAMETER_VERSION}")
    print(f"As-of date: {AS_OF.isoformat()}")

    for label, module in [("Stripe", stripe), ("Linear", linear)]:
        ledger = EvidenceLedger.from_list(module.CLAIMS)
        stage = determine_stage(ledger, module.COMPANY_REF, AS_OF)
        print(f"\n(determined stage for {label}: {stage.value})")
        result = evaluate_pillar_for_company(ledger, module.COMPANY_REF, AS_OF, stage)
        _print_pillar(label, result)


if __name__ == "__main__":
    main()
