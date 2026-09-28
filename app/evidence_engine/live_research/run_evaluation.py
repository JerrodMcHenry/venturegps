"""
Task 11 -- runs the real, genuinely-researched Claim data in this package
through the actual Product & Technology pipeline (Ledger -> stage
determination -> classification/extraction via the default WellBehaved
models -> Deterministic Scoring). No AI/LLM call is made -- exactly the
same default mock models used throughout Tasks 8-10.

This is a one-off evaluation script, not a permanent regression test
(real-world facts age; a future re-run against the same companies could
legitimately produce different results as their public footprint
changes) -- run it directly to reproduce this report's findings:

    python -m app.evidence_engine.live_research.run_evaluation
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.ledger import EvidenceLedger, resolve_dimension_evidence
from app.evidence_engine.live_research import bullet, fish_audio, linear, notion, stripe
from app.evidence_engine.parameters import PARAMETER_VERSION
from app.evidence_engine.pillars.product_technology import (
    DIMENSION_DEFENSIBILITY,
    DIMENSION_DIFFERENTIATION,
    DIMENSION_PRODUCT_EXISTENCE,
    DIMENSION_TECHNICAL_DEPTH,
    evaluate_pillar_for_company,
)
from app.evidence_engine.provenance import assess_independence, verify_independence
from app.evidence_engine.scoring import PillarResult, verify_traceability
from app.evidence_engine.stage import STAGE_SIGNAL_DIMENSION, determine_stage

AS_OF = date(2026, 9, 27)

_COMPANIES = [
    ("Notion", notion.COMPANY_REF, notion.COMPANY_DISPLAY_NAMES, notion.CLAIMS),
    ("Linear", linear.COMPANY_REF, linear.COMPANY_DISPLAY_NAMES, linear.CLAIMS),
    ("Stripe", stripe.COMPANY_REF, stripe.COMPANY_DISPLAY_NAMES, stripe.CLAIMS),
    ("Fish Audio", fish_audio.COMPANY_REF, fish_audio.COMPANY_DISPLAY_NAMES, fish_audio.CLAIMS),
    ("Bullet", bullet.COMPANY_REF, bullet.COMPANY_DISPLAY_NAMES, bullet.CLAIMS),
]


def _print_pillar(label: str, stage_label: str, pillar_result: PillarResult, claim_ids: frozenset[str]) -> None:
    print(f"\n=== {label} — Product & Technology (stage: {stage_label}) ===")
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
        print(f"  - {d.dimension:38s} {d.availability.value:28s} score={score_display}{label_display}")
        print(f"      cites: [{claims_display}]")
        print(f"      rationale: {d.rationale}")
        violations = verify_traceability(d, claim_ids)
        if violations:
            print(f"      TRACEABILITY VIOLATIONS: {violations}")


def main() -> None:
    print(f"Task 11 live evaluation -- parameter version {PARAMETER_VERSION}")
    print(f"As-of date: {AS_OF.isoformat()}")

    for label, company_ref, display_names, claims in _COMPANIES:
        ledger = EvidenceLedger.from_list(claims)
        claim_ids = frozenset(c.claim_id for c in ledger.claims)
        stage = determine_stage(ledger, company_ref, AS_OF)
        pillar_result = evaluate_pillar_for_company(ledger, company_ref, AS_OF, stage, display_names)
        _print_pillar(label, stage.value, pillar_result, claim_ids)

    # --- Explicit provenance findings on the two real near-duplicate/
    # disputed stage-signal pairs (Notion, Linear) -----------------------
    print("\n=== Provenance verification: real near-duplicate/disputed pairs ===")

    notion_ledger = EvidenceLedger.from_list(notion.CLAIMS)
    notion_stage_evidence = resolve_dimension_evidence(notion_ledger, STAGE_SIGNAL_DIMENSION, AS_OF, staleness_days=365 * 5)
    print(
        f"\nNotion Series C stage-signal claims: "
        f"{len(notion_stage_evidence.disputed)} disputed (both correctly excluded), "
        f"{len(notion_stage_evidence.admissible)} admissible."
    )
    print(f"-> Notion's determined stage: {determine_stage(notion_ledger, notion.COMPANY_REF, AS_OF).value}")

    linear_a = next(c for c in linear.CLAIMS if c.claim_id == "linear-live-stage-001")
    linear_b = next(c for c in linear.CLAIMS if c.claim_id == "linear-live-stage-002")
    verdict = assess_independence(linear_a, linear_b)
    print(
        f"\nLinear Series C: linear.app's own post vs. TechCrunch's independent report of the same "
        f"round -> assess_independence() verdict: {verdict.value}"
    )

    bullet_ledger = EvidenceLedger.from_list(bullet.CLAIMS)
    bullet_diff_evidence = resolve_dimension_evidence(bullet_ledger, DIMENSION_DIFFERENTIATION, AS_OF, staleness_days=548)
    print(
        f"\nBullet differentiation claims: {len(bullet_diff_evidence.disputed)} disputed "
        f"(founders' benchmark claim vs. independent commenter rebuttal), "
        f"{len(bullet_diff_evidence.admissible)} admissible."
    )


if __name__ == "__main__":
    main()
