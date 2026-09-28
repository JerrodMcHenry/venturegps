"""
Task 9, item 3 -- stage determination and stage-sensitive scoring.

Covers: the round-type > founding-age > Undetermined priority order
(spec Part 4.1), most-recent-round tiebreaking, the "most permissive band
when Undetermined" rule (Part 4.3), that identical evidence scores
differently (higher, not lower) at an earlier stage, and -- the task's
own explicit prohibition -- that stage NEVER grants an automatic bonus
that turns genuinely insufficient evidence into a scored dimension.

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_stage_aware_evaluation
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine import parameters as P
from app.evidence_engine.fixtures import auroraflow_fictional, linear, notion, pathlight_fictional
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim, SourceType, SupportStatus
from app.evidence_engine.pillars.product_technology import (
    DIMENSION_DIFFERENTIATION,
    evaluate_differentiation_claim_corroboration,
)
from app.evidence_engine.stage import ALL_TIERS, STAGE_SIGNAL_DIMENSION, Stage, determine_stage, tier_for_stage

AS_OF = date(2026, 9, 27)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _stage_claim(claim_id: str, company_ref: str, kind: str, value: str, retrieved_at: date) -> Claim:
    return Claim(
        claim_id=claim_id, company_ref=company_ref, claim_text=f"stage signal: {kind}={value}",
        subject_entity=company_ref, source_publisher="a source", source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=retrieved_at, support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt="an excerpt",
        assessment_criteria=[STAGE_SIGNAL_DIMENSION], independence_group_id=claim_id,
        structured_fact={"kind": kind, "value": value},
    )


def test_round_type_signal_takes_priority_over_founding_year() -> None:
    claims = [
        _stage_claim("s1", "co", "founding_year", "2010", AS_OF),  # would imply GROWTH by age alone
        _stage_claim("s2", "co", "funding_round_type", "Seed", AS_OF),  # should win
    ]
    stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
    expect(stage == Stage.SEED, f"Round-type signal must win over founding-year, got {stage}")


def test_most_recent_disclosed_round_wins_when_multiple_exist() -> None:
    claims = [
        _stage_claim("s1", "co", "funding_round_type", "Seed", date(2023, 1, 1)),
        _stage_claim("s2", "co", "funding_round_type", "Series A", date(2025, 1, 1)),
    ]
    stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
    expect(stage == Stage.SERIES_A, f"The more recently disclosed round must win, got {stage}")


def test_founding_year_fallback_when_no_round_disclosed() -> None:
    stage = determine_stage(
        EvidenceLedger.from_list(pathlight_fictional.CLAIMS), pathlight_fictional.COMPANY_REF, AS_OF
    )
    expect(stage == Stage.PRE_SEED, f"Expected Pre-Seed from Pathlight's founding-year-only signal, got {stage}")


def test_undetermined_when_no_stage_signal_exists() -> None:
    stage = determine_stage(
        EvidenceLedger.from_list(auroraflow_fictional.CLAIMS), auroraflow_fictional.COMPANY_REF, AS_OF
    )
    expect(stage == Stage.UNDETERMINED, f"Expected Undetermined with zero stage-signal claims, got {stage}")


def test_undetermined_never_silently_defaults_to_a_real_stage() -> None:
    # A company with NO evidence at all (not even a Product & Technology
    # claim) must still resolve to Undetermined, never a silent guess.
    stage = determine_stage(EvidenceLedger.from_list([]), "totally_unknown_co", AS_OF)
    expect(stage == Stage.UNDETERMINED, f"Expected Undetermined for a company with zero claims, got {stage}")


def test_every_stage_tier_table_is_monotonically_non_increasing_early_to_established() -> None:
    # This is the structural property _score_for_label's "Undetermined ->
    # max()" shortcut relies on -- asserted directly, not assumed.
    for table_name, table in [
        ("DIFFERENTIATION", P.DIFFERENTIATION_LABEL_SCORES),
        ("TECHNICAL_DEPTH", P.TECHNICAL_DEPTH_LABEL_SCORES),
        ("DEFENSIBILITY", P.DEFENSIBILITY_LABEL_SCORES),
    ]:
        for label, tier_scores in table.items():
            ordered = [tier_scores[t.value] for t in ALL_TIERS]
            expect(
                ordered == sorted(ordered, reverse=True),
                f"{table_name}[{label}] is not non-increasing early->established: {ordered}",
            )


def test_identical_corroborated_evidence_scores_higher_at_an_earlier_stage() -> None:
    # Pathlight (Pre-Seed / EARLY tier) has one independently-corroborated
    # differentiation claim, structurally identical in kind to Notion's
    # (Growth / ESTABLISHED tier) one. The EARLY-tier score must be
    # strictly higher for the identical CORROBORATED label -- the same
    # evidence is more remarkable, and worth more, earlier, never the
    # reverse ("no automatic bonus to established companies").
    pathlight_ledger = EvidenceLedger.from_list(pathlight_fictional.CLAIMS)
    pathlight_stage = determine_stage(pathlight_ledger, pathlight_fictional.COMPANY_REF, AS_OF)
    pathlight_result = evaluate_differentiation_claim_corroboration(
        pathlight_ledger, pathlight_fictional.COMPANY_REF, AS_OF, pathlight_stage
    )

    notion_ledger = EvidenceLedger.from_list(notion.CLAIMS)
    notion_stage = determine_stage(notion_ledger, notion.COMPANY_REF, AS_OF)
    notion_result = evaluate_differentiation_claim_corroboration(
        notion_ledger, notion.COMPANY_REF, AS_OF, notion_stage
    )

    expect(pathlight_stage == Stage.PRE_SEED, f"Test setup error: expected Pre-Seed, got {pathlight_stage}")
    expect(notion_stage == Stage.GROWTH, f"Test setup error: expected Growth, got {notion_stage}")
    expect(pathlight_result.classification_label == "CORROBORATED", "Test setup error: Pathlight must be CORROBORATED")
    expect(notion_result.classification_label == "CORROBORATED", "Test setup error: Notion must be CORROBORATED")
    expect(
        pathlight_result.score > notion_result.score,
        f"Expected Pathlight's early-stage score ({pathlight_result.score}) to exceed "
        f"Notion's established-stage score ({notion_result.score}) for the identical CORROBORATED label",
    )


def test_undetermined_stage_scores_at_the_most_permissive_tier() -> None:
    ledger = EvidenceLedger.from_list(pathlight_fictional.CLAIMS)
    undetermined_result = evaluate_differentiation_claim_corroboration(
        ledger, pathlight_fictional.COMPANY_REF, AS_OF, Stage.UNDETERMINED
    )
    early_tier_score = P.DIFFERENTIATION_LABEL_SCORES["CORROBORATED"]["early"]
    expect(
        undetermined_result.score == early_tier_score,
        f"Undetermined must score at the most permissive (early) tier ({early_tier_score}), "
        f"got {undetermined_result.score}",
    )


def test_stage_never_grants_an_automatic_bonus_that_scores_insufficient_evidence() -> None:
    # Linear's differentiation evidence is genuinely uncorroborated (only a
    # company_disclosure claim). Re-running it at every possible stage,
    # including a synthetic "established" one, must leave it Unscored --
    # stage changes WHICH SCORE a label maps to, never WHETHER a label is
    # reachable from insufficient evidence.
    ledger = EvidenceLedger.from_list(linear.CLAIMS)
    for stage in (Stage.PRE_SEED, Stage.SEED, Stage.SERIES_A, Stage.SERIES_B_PLUS, Stage.GROWTH, Stage.UNDETERMINED):
        result = evaluate_differentiation_claim_corroboration(ledger, linear.COMPANY_REF, AS_OF, stage)
        expect(
            result.score is None,
            f"Stage {stage.value} must not turn Linear's uncorroborated differentiation claim into a "
            f"scored result (got score={result.score})",
        )
        expect(
            result.classification_label == "UNCORROBORATED",
            f"Stage must not change the classification itself, only the score of an already-scorable "
            f"label -- got {result.classification_label} at stage {stage.value}",
        )


def test_tier_for_stage_is_none_only_for_undetermined() -> None:
    expect(tier_for_stage(Stage.UNDETERMINED) is None, "Undetermined must have no tier")
    for stage in (Stage.IDEA, Stage.PRE_SEED, Stage.SEED, Stage.SERIES_A, Stage.SERIES_B_PLUS, Stage.GROWTH):
        expect(tier_for_stage(stage) is not None, f"{stage.value} must map to a real tier")


TESTS = [
    test_round_type_signal_takes_priority_over_founding_year,
    test_most_recent_disclosed_round_wins_when_multiple_exist,
    test_founding_year_fallback_when_no_round_disclosed,
    test_undetermined_when_no_stage_signal_exists,
    test_undetermined_never_silently_defaults_to_a_real_stage,
    test_every_stage_tier_table_is_monotonically_non_increasing_early_to_established,
    test_identical_corroborated_evidence_scores_higher_at_an_earlier_stage,
    test_undetermined_stage_scores_at_the_most_permissive_tier,
    test_stage_never_grants_an_automatic_bonus_that_scores_insufficient_evidence,
    test_tier_for_stage_is_none_only_for_undetermined,
]


def main() -> None:
    print("\nVentureGPS Evidence Engine -- stage-aware evaluation tests")
    print("-" * 72)
    failures: list[str] = []
    for test in TESTS:
        name = test.__name__
        try:
            test()
        except AssertionError as error:
            print(f"FAIL  {name}\n      {error}")
            failures.append(name)
        else:
            print(f"PASS  {name}")
    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
