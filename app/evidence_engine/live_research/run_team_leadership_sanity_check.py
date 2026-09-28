"""
Task 14, item 10 -- a SMALL Team & Leadership sanity check against real
evidence, not another calibration project. Reuses Stripe (very famous
founders -- the deliberate prestige-vs-evidence test case) and Linear
(a real but far less publicly famous founder) from Tasks 11-13, with a
small amount of additional, genuinely-researched team evidence added to
their live_research data (see each file's own "Task 14 addition").

Run with:
    python -m app.evidence_engine.live_research.run_team_leadership_sanity_check
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.live_research import linear, stripe
from app.evidence_engine.parameters import PARAMETER_VERSION
from app.evidence_engine.pillars.team_leadership import evaluate_pillar_for_company
from app.evidence_engine.scoring import PillarResult
from app.evidence_engine.stage import determine_stage

AS_OF = date(2026, 9, 27)


def _print_pillar(label: str, pillar_result: PillarResult) -> None:
    print(f"\n=== {label} — Team & Leadership ===")
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
        print(f"  - {d.dimension:30s} {d.availability.value:24s} score={score_display}{label_display} cites=[{claims_display}]")


def main() -> None:
    print(f"Task 14 sanity check -- parameter version {PARAMETER_VERSION}")
    print(f"As-of date: {AS_OF.isoformat()}")

    for label, company_ref, claims in [("Stripe", stripe.COMPANY_REF, stripe.CLAIMS), ("Linear", linear.COMPANY_REF, linear.CLAIMS)]:
        ledger = EvidenceLedger.from_list(claims)
        stage = determine_stage(ledger, company_ref, AS_OF)
        result = evaluate_pillar_for_company(ledger, company_ref, AS_OF, stage)
        _print_pillar(label, result)


if __name__ == "__main__":
    main()
