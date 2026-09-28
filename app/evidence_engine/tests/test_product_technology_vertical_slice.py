"""
VentureGPS Evidence Engine -- Product & Technology vertical slice tests
(Task 8's original slice, updated for Task 9's calibration pass: stage-
aware evaluation and the AI classification interface, both now load-
bearing rather than deferred).

No real LLM/Tavily call anywhere in this file or in the fixtures it
imports -- every "assessment" goes through the default `WellBehaved*`
mock models (app.evidence_engine.pillars.product_technology), which
conform to the same Protocol a real, schema-constrained model call would.

Run with:
    python -m app.evidence_engine.tests.test_product_technology_vertical_slice
"""

from __future__ import annotations

from datetime import date, timedelta

import pydantic

from app.evidence_engine import parameters as P
from app.evidence_engine.fixtures import auroraflow_fictional, linear, notion
from app.evidence_engine.ledger import EvidenceLedger, resolve_dimension_evidence
from app.evidence_engine.models import Claim, SourceType, SupportStatus
from app.evidence_engine.pillars.product_technology import (
    DIMENSION_DEFENSIBILITY,
    DIMENSION_DIFFERENTIATION,
    DIMENSION_PRODUCT_EXISTENCE,
    DIMENSION_TECHNICAL_DEPTH,
    evaluate_all,
    evaluate_pillar_for_company,
    evaluate_product_existence_maturity,
)
from app.evidence_engine.scoring import (
    AvailabilityStatus,
    ConfidenceLevel,
    DimensionCategory,
    DimensionResult,
    PillarGateParameters,
    compute_pillar_confidence,
    compute_pillar_coverage_pct,
    compute_pillar_strength,
    evaluate_pillar,
    verify_traceability,
)
from app.evidence_engine.stage import Stage, determine_stage

AS_OF = date(2026, 9, 27)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------
# 1. The Claim model itself (spec Part 2.1/2.2)
# ---------------------------------------------------------------------------

def test_claim_rejects_missing_excerpt_when_scorable() -> None:
    try:
        Claim(
            claim_id="bad-001", company_ref="x", claim_text="A claim with no excerpt.",
            subject_entity="x", source_publisher="somewhere", source_type=SourceType.INDEPENDENT_REPORTING,
            retrieved_at=AS_OF, support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt=None,
            independence_group_id="g1",
        )
    except pydantic.ValidationError:
        pass
    else:
        raise AssertionError("A directly_supported claim with no excerpt must be rejected at write time")


def test_claim_rejects_blank_source_publisher() -> None:
    try:
        Claim(
            claim_id="bad-002", company_ref="x", claim_text="A claim with a blank publisher.",
            subject_entity="x", source_publisher="   ", source_type=SourceType.INDEPENDENT_REPORTING,
            retrieved_at=AS_OF, support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt="something",
            independence_group_id="g1",
        )
    except pydantic.ValidationError:
        pass
    else:
        raise AssertionError("A claim with a blank source_publisher must be rejected")


def test_disputed_claim_may_omit_excerpt() -> None:
    Claim(
        claim_id="ok-001", company_ref="x", claim_text="A disputed claim pending resolution.",
        subject_entity="x", source_publisher="somewhere", source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=AS_OF, support_status=SupportStatus.DISPUTED, excerpt=None,
        independence_group_id="g1",
    )


# ---------------------------------------------------------------------------
# 2. Notion -- fully scorable, all four dimensions, Growth/established stage
# ---------------------------------------------------------------------------

def _notion_ledger() -> EvidenceLedger:
    return EvidenceLedger.from_list(notion.CLAIMS)


def _notion_stage() -> Stage:
    return determine_stage(_notion_ledger(), notion.COMPANY_REF, AS_OF)


def test_notion_stage_is_determined_as_growth() -> None:
    expect(_notion_stage() == Stage.GROWTH, f"Expected Stage.GROWTH from Notion's stage-signal claim, got {_notion_stage()}")


def test_notion_all_four_dimensions_are_scorable() -> None:
    results = evaluate_all(_notion_ledger(), notion.COMPANY_REF, AS_OF, _notion_stage())
    for r in results:
        expect(
            r.availability == AvailabilityStatus.SCORABLE,
            f"Notion/{r.dimension}: expected SCORABLE, got {r.availability.value} ({r.rationale})",
        )
        expect(r.score is not None, f"Notion/{r.dimension}: SCORABLE but score is None")


def test_notion_technical_depth_reaches_substantial_band() -> None:
    result = evaluate_all(_notion_ledger(), notion.COMPANY_REF, AS_OF, _notion_stage())[2]
    expect(result.dimension == DIMENSION_TECHNICAL_DEPTH, "dimension index assumption changed")
    expect(
        result.classification_label == "SUBSTANTIAL",
        f"Expected SUBSTANTIAL (3 distinct named technical facts), got {result.classification_label}",
    )
    expect(
        result.score == P.TECHNICAL_DEPTH_LABEL_SCORES["SUBSTANTIAL"]["established"],
        f"Expected the established-tier SUBSTANTIAL score, got {result.score}",
    )


def test_notion_pillar_is_publishable_with_full_strength() -> None:
    pillar_result = evaluate_pillar_for_company(_notion_ledger(), notion.COMPANY_REF, AS_OF, _notion_stage())
    expect(pillar_result.publishable, f"Notion pillar should be publishable, withheld: {pillar_result.withhold_reasons}")
    expect(pillar_result.coverage_pct == 100.0, f"Expected 100% coverage, got {pillar_result.coverage_pct}")
    expect(pillar_result.strength is not None, "Publishable pillar must have a real Strength number")
    expect(len(pillar_result.withhold_reasons) == 0, "A publishable pillar must carry zero withhold reasons")


def test_notion_every_scorable_dimension_traces_to_admissible_evidence() -> None:
    ledger = _notion_ledger()
    claim_ids = frozenset(c.claim_id for c in ledger.claims)
    results = evaluate_all(ledger, notion.COMPANY_REF, AS_OF, _notion_stage())
    for r in results:
        violations = verify_traceability(r, claim_ids)
        expect(not violations, f"Traceability violation(s) for Notion/{r.dimension}: {violations}")
        for claim_id in r.supporting_claim_ids:
            claim = ledger.by_id(claim_id)
            expect(claim is not None, f"supporting_claim_id {claim_id!r} does not resolve to a real Claim")
            expect(
                r.dimension in claim.assessment_criteria,
                f"Claim {claim_id!r} is cited by {r.dimension} but is not tagged with it in assessment_criteria",
            )


# ---------------------------------------------------------------------------
# 3. Linear -- partially scorable, Series B+/growth-tier stage
# ---------------------------------------------------------------------------

def _linear_ledger() -> EvidenceLedger:
    return EvidenceLedger.from_list(linear.CLAIMS)


def _linear_stage() -> Stage:
    return determine_stage(_linear_ledger(), linear.COMPANY_REF, AS_OF)


def test_linear_stage_is_determined_as_series_b_plus() -> None:
    expect(
        _linear_stage() == Stage.SERIES_B_PLUS,
        f"Expected Stage.SERIES_B_PLUS from Linear's stage-signal claim, got {_linear_stage()}",
    )


def test_linear_product_existence_and_technical_depth_are_scorable() -> None:
    results = {r.dimension: r for r in evaluate_all(_linear_ledger(), linear.COMPANY_REF, AS_OF, _linear_stage())}
    expect(
        results[DIMENSION_PRODUCT_EXISTENCE].availability == AvailabilityStatus.SCORABLE,
        "Linear's directly-observable product artifact should score Product Existence & Maturity",
    )
    expect(
        results[DIMENSION_TECHNICAL_DEPTH].availability == AvailabilityStatus.SCORABLE,
        "Linear's one named GitHub integration should reach the SOME band",
    )
    expect(
        results[DIMENSION_TECHNICAL_DEPTH].classification_label == "SOME",
        f"Expected SOME (1 named fact, below SUBSTANTIAL's floor of {P.TECHNICAL_DEPTH_SUBSTANTIAL_MIN_FACTS}), "
        f"got {results[DIMENSION_TECHNICAL_DEPTH].classification_label}",
    )
    expect(
        results[DIMENSION_TECHNICAL_DEPTH].score == P.TECHNICAL_DEPTH_LABEL_SCORES["SOME"]["growth"],
        f"Expected the growth-tier SOME score, got {results[DIMENSION_TECHNICAL_DEPTH].score}",
    )


def test_linear_uncorroborated_differentiation_is_unscored_not_a_low_score() -> None:
    results = {r.dimension: r for r in evaluate_all(_linear_ledger(), linear.COMPANY_REF, AS_OF, _linear_stage())}
    diff = results[DIMENSION_DIFFERENTIATION]
    expect(diff.score is None, f"Expected score=None for an uncorroborated claim, got {diff.score}")
    expect(
        diff.availability == AvailabilityStatus.UNSCORED_UNCORROBORATED,
        f"Expected UNSCORED_UNCORROBORATED, got {diff.availability.value}",
    )
    expect(diff.classification_label == "UNCORROBORATED", f"Expected UNCORROBORATED label, got {diff.classification_label}")


def test_linear_defensibility_has_no_evidence_at_all() -> None:
    results = {r.dimension: r for r in evaluate_all(_linear_ledger(), linear.COMPANY_REF, AS_OF, _linear_stage())}
    defensibility = results[DIMENSION_DEFENSIBILITY]
    expect(defensibility.score is None, "No claim was tagged for Defensibility in the Linear fixture -- must be Unscored")
    expect(
        defensibility.availability == AvailabilityStatus.UNSCORED_NO_EVIDENCE,
        f"Expected UNSCORED_NO_EVIDENCE, got {defensibility.availability.value}",
    )


def test_linear_pillar_is_still_publishable_from_two_scored_dimensions() -> None:
    pillar_result = evaluate_pillar_for_company(_linear_ledger(), linear.COMPANY_REF, AS_OF, _linear_stage())
    expect(pillar_result.publishable, f"Linear pillar should be publishable at 50% coverage, withheld: {pillar_result.withhold_reasons}")
    expect(pillar_result.coverage_pct == 50.0, f"Expected 50% coverage, got {pillar_result.coverage_pct}")
    expect(pillar_result.strength is not None, "Publishable pillar must expose a real Strength")


# ---------------------------------------------------------------------------
# 4. "Auroraflow" (fictional) -- insufficient evidence, undetermined stage
# ---------------------------------------------------------------------------

def _auroraflow_ledger() -> EvidenceLedger:
    return EvidenceLedger.from_list(auroraflow_fictional.CLAIMS)


def test_auroraflow_stage_is_undetermined() -> None:
    stage = determine_stage(_auroraflow_ledger(), auroraflow_fictional.COMPANY_REF, AS_OF)
    expect(stage == Stage.UNDETERMINED, f"Expected Stage.UNDETERMINED (no stage-signal claim exists), got {stage}")


def test_auroraflow_product_existence_rejects_unsupported_self_claim() -> None:
    result = evaluate_product_existence_maturity(
        _auroraflow_ledger(), auroraflow_fictional.COMPANY_REF, AS_OF, Stage.UNDETERMINED
    )
    expect(result.score is None, "An uncorroborated company self-claim must not score Product Existence & Maturity")
    expect(
        result.availability == AvailabilityStatus.UNSCORED_UNCORROBORATED,
        f"Expected UNSCORED_UNCORROBORATED, got {result.availability.value}",
    )


def test_auroraflow_contradictory_sources_are_excluded_not_tie_broken() -> None:
    ledger = _auroraflow_ledger()
    evidence = resolve_dimension_evidence(ledger, DIMENSION_TECHNICAL_DEPTH, AS_OF, staleness_days=730)
    expect(len(evidence.admissible) == 0, "Both contradicting claims must be excluded from admissible evidence")
    expect(len(evidence.disputed) == 2, f"Expected both claims marked disputed, got {len(evidence.disputed)}")

    results = {
        r.dimension: r
        for r in evaluate_all(ledger, auroraflow_fictional.COMPANY_REF, AS_OF, Stage.UNDETERMINED)
    }
    technical_depth = results[DIMENSION_TECHNICAL_DEPTH]
    expect(technical_depth.score is None, "A dimension backed only by unresolved conflicting claims must be Unscored")
    expect(
        technical_depth.availability == AvailabilityStatus.UNSCORED_DISPUTED,
        f"Expected UNSCORED_DISPUTED, got {technical_depth.availability.value}",
    )


def test_auroraflow_all_four_dimensions_are_unscored() -> None:
    results = evaluate_all(_auroraflow_ledger(), auroraflow_fictional.COMPANY_REF, AS_OF, Stage.UNDETERMINED)
    for r in results:
        expect(
            r.availability != AvailabilityStatus.SCORABLE,
            f"Auroraflow/{r.dimension}: expected Unscored, got SCORABLE (score={r.score})",
        )
        expect(r.score is None, f"Auroraflow/{r.dimension}: availability is not SCORABLE but score is {r.score!r}, not None")


def test_auroraflow_pillar_is_withheld_by_both_gates() -> None:
    pillar_result = evaluate_pillar_for_company(
        _auroraflow_ledger(), auroraflow_fictional.COMPANY_REF, AS_OF, Stage.UNDETERMINED
    )
    expect(not pillar_result.publishable, "Auroraflow pillar must be withheld -- zero scorable dimensions")
    expect(pillar_result.strength is None, "A withheld pillar's Strength must be None, never a number")
    expect(pillar_result.coverage_pct == 0.0, f"Expected 0% coverage, got {pillar_result.coverage_pct}")
    expect(
        len(pillar_result.withhold_reasons) == 2,
        f"Expected both the coverage-floor and the min-dimension-count reasons, got {pillar_result.withhold_reasons}",
    )
    expect(
        any("coverage" in reason for reason in pillar_result.withhold_reasons),
        "One withhold reason must name the coverage floor",
    )
    expect(
        any("scored dimension" in reason for reason in pillar_result.withhold_reasons),
        "One withhold reason must name the minimum-scored-dimensions floor",
    )


def test_auroraflow_traceability_has_zero_violations_because_zero_scores_exist() -> None:
    ledger = _auroraflow_ledger()
    claim_ids = frozenset(c.claim_id for c in ledger.claims)
    for r in evaluate_all(ledger, auroraflow_fictional.COMPANY_REF, AS_OF, Stage.UNDETERMINED):
        violations = verify_traceability(r, claim_ids)
        expect(not violations, f"Unexpected traceability violation for Auroraflow/{r.dimension}: {violations}")


# ---------------------------------------------------------------------------
# 5. Staleness (spec Part 2.4)
# ---------------------------------------------------------------------------

def test_stale_evidence_is_excluded_from_scoring() -> None:
    stale_date = AS_OF - timedelta(days=P.PRODUCT_TECHNOLOGY_STALENESS_DAYS[DIMENSION_PRODUCT_EXISTENCE] + 30)
    stale_claim = Claim(
        claim_id="stale-001", company_ref="stale_co", claim_text="A product artifact observed long ago.",
        subject_entity="stale_co", source_publisher="an independent source", source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=stale_date, support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt="observed long ago",
        assessment_criteria=[DIMENSION_PRODUCT_EXISTENCE], independence_group_id="stale-group",
    )
    ledger = EvidenceLedger.from_list([stale_claim])
    result = evaluate_product_existence_maturity(ledger, "stale_co", AS_OF, Stage.UNDETERMINED)
    expect(result.score is None, "A claim older than its dimension's staleness bound must not score")
    expect(
        result.availability == AvailabilityStatus.UNSCORED_STALE,
        f"Expected UNSCORED_STALE, got {result.availability.value}",
    )


# ---------------------------------------------------------------------------
# 6. Deterministic Scoring core: firewall property, gates, reproducibility
# ---------------------------------------------------------------------------

def _fake_dimension(name: str, weight: float, score: float | None, availability: AvailabilityStatus, confidence: ConfidenceLevel) -> DimensionResult:
    return DimensionResult(
        dimension=name, pillar="Test Pillar", category=DimensionCategory.CLASSIFIED,
        weight=weight, score=score, availability=availability,
        supporting_claim_ids=("x",) if availability == AvailabilityStatus.SCORABLE else (),
        confidence=confidence,
    )


def test_firewall_strength_is_unaffected_by_confidence_alone() -> None:
    low = (_fake_dimension("d1", 0.5, 7.0, AvailabilityStatus.SCORABLE, ConfidenceLevel.LOW),
           _fake_dimension("d2", 0.5, 5.0, AvailabilityStatus.SCORABLE, ConfidenceLevel.LOW))
    high = (_fake_dimension("d1", 0.5, 7.0, AvailabilityStatus.SCORABLE, ConfidenceLevel.HIGH),
            _fake_dimension("d2", 0.5, 5.0, AvailabilityStatus.SCORABLE, ConfidenceLevel.HIGH))
    expect(
        compute_pillar_strength(low) == compute_pillar_strength(high),
        "Strength must be identical regardless of confidence -- compute_pillar_strength must not read confidence",
    )
    expect(
        compute_pillar_confidence(low) != compute_pillar_confidence(high),
        "Sanity check: confidence itself must actually differ between the two synthetic inputs",
    )


def test_two_gates_are_both_independently_required() -> None:
    dims = (
        _fake_dimension("big", 0.45, 9.0, AvailabilityStatus.SCORABLE, ConfidenceLevel.HIGH),
        _fake_dimension("small_a", 0.30, None, AvailabilityStatus.UNSCORED_NO_EVIDENCE, ConfidenceLevel.LOW),
        _fake_dimension("small_b", 0.25, None, AvailabilityStatus.UNSCORED_NO_EVIDENCE, ConfidenceLevel.LOW),
    )
    coverage = compute_pillar_coverage_pct(dims)
    expect(coverage >= P.MIN_PILLAR_COVERAGE_PCT, f"Test setup error: expected coverage >= floor, got {coverage}")

    gate_params = PillarGateParameters(
        min_pillar_coverage_pct=P.MIN_PILLAR_COVERAGE_PCT,
        min_scored_dimensions_per_pillar=P.MIN_SCORED_DIMENSIONS_PER_PILLAR,
    )
    result = evaluate_pillar("Synthetic Pillar", dims, gate_params)
    expect(
        not result.publishable,
        "A single 0.45-weight dimension clearing the coverage floor alone must still be withheld by gate 2",
    )
    expect(result.strength is None, "A withheld pillar must never expose a Strength number")
    expect(
        len(result.withhold_reasons) == 1 and "scored dimension" in result.withhold_reasons[0],
        f"Expected exactly one reason naming the dimension-count floor, got {result.withhold_reasons}",
    )


def test_scoring_is_perfectly_reproducible_given_identical_inputs() -> None:
    ledger = _notion_ledger()
    stage = _notion_stage()
    first = evaluate_pillar_for_company(ledger, notion.COMPANY_REF, AS_OF, stage)
    second = evaluate_pillar_for_company(ledger, notion.COMPANY_REF, AS_OF, stage)
    expect(first.strength == second.strength, "Strength must be bit-for-bit identical across repeated runs on identical input")
    expect(first.coverage_pct == second.coverage_pct, "Coverage must be identical across repeated runs")
    expect(first.confidence == second.confidence, "Confidence must be identical across repeated runs")
    expect(
        tuple((d.dimension, d.score, d.availability) for d in first.dimension_results)
        == tuple((d.dimension, d.score, d.availability) for d in second.dimension_results),
        "Per-dimension results must be identical across repeated runs",
    )


TESTS = [
    test_claim_rejects_missing_excerpt_when_scorable,
    test_claim_rejects_blank_source_publisher,
    test_disputed_claim_may_omit_excerpt,
    test_notion_stage_is_determined_as_growth,
    test_notion_all_four_dimensions_are_scorable,
    test_notion_technical_depth_reaches_substantial_band,
    test_notion_pillar_is_publishable_with_full_strength,
    test_notion_every_scorable_dimension_traces_to_admissible_evidence,
    test_linear_stage_is_determined_as_series_b_plus,
    test_linear_product_existence_and_technical_depth_are_scorable,
    test_linear_uncorroborated_differentiation_is_unscored_not_a_low_score,
    test_linear_defensibility_has_no_evidence_at_all,
    test_linear_pillar_is_still_publishable_from_two_scored_dimensions,
    test_auroraflow_stage_is_undetermined,
    test_auroraflow_product_existence_rejects_unsupported_self_claim,
    test_auroraflow_contradictory_sources_are_excluded_not_tie_broken,
    test_auroraflow_all_four_dimensions_are_unscored,
    test_auroraflow_pillar_is_withheld_by_both_gates,
    test_auroraflow_traceability_has_zero_violations_because_zero_scores_exist,
    test_stale_evidence_is_excluded_from_scoring,
    test_firewall_strength_is_unaffected_by_confidence_alone,
    test_two_gates_are_both_independently_required,
    test_scoring_is_perfectly_reproducible_given_identical_inputs,
]


def main() -> None:
    print("\nVentureGPS Evidence Engine -- Product & Technology vertical slice tests")
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
