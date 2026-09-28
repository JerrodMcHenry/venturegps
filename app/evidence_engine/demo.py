"""
Prints a human-readable Product & Technology pillar summary for each of
this engine's offline fixtures. No AI call, no network access, no
database -- pure demonstration of Ledger -> Assessment(-stand-in) ->
Scoring, now stage-aware and routed through the AI classification
interface's default (well-behaved) mock models.

Run with:
    python -m app.evidence_engine.demo
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.fixtures import auroraflow_fictional, duplico_fictional, linear, notion, pathlight_fictional
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.parameters import PARAMETER_VERSION
from app.evidence_engine.pillars.product_technology import evaluate_pillar_for_company
from app.evidence_engine.scoring import PillarResult
from app.evidence_engine.stage import Stage, determine_stage

AS_OF = date(2026, 9, 27)


def _print_pillar(label: str, stage: Stage, pillar_result: PillarResult) -> None:
    print(f"\n=== {label} — Product & Technology (stage: {stage.value}) ===")
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
        print(
            f"  - {d.dimension:38s} {d.availability.value:28s} score={score_display}{label_display} "
            f"claims=[{claims_display}]"
        )


def _run(label: str, company_ref: str, claims: list) -> None:
    ledger = EvidenceLedger.from_list(claims)
    stage = determine_stage(ledger, company_ref, AS_OF)
    _print_pillar(label, stage, evaluate_pillar_for_company(ledger, company_ref, AS_OF, stage))


def main() -> None:
    print(f"Methodology parameter version: {PARAMETER_VERSION}")
    print(f"As-of date: {AS_OF.isoformat()}")

    _run("Notion", notion.COMPANY_REF, notion.CLAIMS)
    _run("Linear", linear.COMPANY_REF, linear.CLAIMS)
    _run("Pathlight (fictional)", pathlight_fictional.COMPANY_REF, pathlight_fictional.CLAIMS)
    _run("DupliCo (fictional)", duplico_fictional.COMPANY_REF, duplico_fictional.CLAIMS)
    _run("Auroraflow (fictional)", auroraflow_fictional.COMPANY_REF, auroraflow_fictional.CLAIMS)
    print()


if __name__ == "__main__":
    main()
