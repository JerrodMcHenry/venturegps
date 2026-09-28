"""
Task 13, item 8 -- a SMALL Market Opportunity sanity check against real
evidence, not another full calibration project. Reuses Notion and Linear
from Tasks 11-12, with a small amount of additional, genuine market-level
research added to their live_research data (see the Task 13 addition in
notion.py/linear.py). Kept as its own script, separate from
run_evaluation.py, so that script continues to reproduce exactly the
Task 11/12 Product & Technology results unchanged.

Run with:
    python -m app.evidence_engine.live_research.run_market_opportunity_sanity_check
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.live_research import linear, notion
from app.evidence_engine.parameters import PARAMETER_VERSION
from app.evidence_engine.pillars.market_opportunity import evaluate_pillar_for_company
from app.evidence_engine.scoring import PillarResult
from app.evidence_engine.stage import determine_stage

AS_OF = date(2026, 9, 27)


def _print_pillar(label: str, pillar_result: PillarResult) -> None:
    print(f"\n=== {label} — Market Opportunity ===")
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
        print(f"  - {d.dimension:32s} {d.availability.value:24s} score={score_display}{label_display} cites=[{claims_display}]")


def main() -> None:
    print(f"Task 13 sanity check -- parameter version {PARAMETER_VERSION}")
    print(f"As-of date: {AS_OF.isoformat()}")

    for label, company_ref, claims in [("Notion", notion.COMPANY_REF, notion.CLAIMS), ("Linear", linear.COMPANY_REF, linear.CLAIMS)]:
        ledger = EvidenceLedger.from_list(claims)
        stage = determine_stage(ledger, company_ref, AS_OF)
        result = evaluate_pillar_for_company(ledger, company_ref, AS_OF, stage)
        _print_pillar(label, result)


if __name__ == "__main__":
    main()
