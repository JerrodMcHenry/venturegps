"""
Task 10, item 3 -- exhaustive boundary testing of the two pillar-level
publishability gates (NEW_ENGINE_SPEC.md Part 6.2): the exact 40% coverage
floor and the values immediately above/below it, the two-scored-dimension
minimum tested independently of coverage (including a single, heavily
weighted dimension that clears the coverage floor alone), and a direct
confirmation that missing evidence can never inflate what a pillar
publishes.

Uses synthetic DimensionResult inputs (not the fixture companies) so each
boundary can be constructed exactly, rather than relying on whichever
combination the fixture roster happens to produce.

Run with:
    python -m app.evidence_engine.tests.test_coverage_boundaries
"""

from __future__ import annotations

from app.evidence_engine import parameters as P
from app.evidence_engine.scoring import (
    AvailabilityStatus,
    ConfidenceLevel,
    DimensionCategory,
    DimensionResult,
    PillarGateParameters,
    compute_pillar_coverage_pct,
    compute_pillar_strength,
    evaluate_pillar,
)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _dim(name: str, weight: float, score: float | None, scorable: bool) -> DimensionResult:
    return DimensionResult(
        dimension=name, pillar="Boundary Test Pillar", category=DimensionCategory.CLASSIFIED,
        weight=weight, score=score,
        availability=AvailabilityStatus.SCORABLE if scorable else AvailabilityStatus.UNSCORED_NO_EVIDENCE,
        supporting_claim_ids=("x",) if scorable else (),
        confidence=ConfidenceLevel.MEDIUM,
    )


_GATES = PillarGateParameters(
    min_pillar_coverage_pct=P.MIN_PILLAR_COVERAGE_PCT,
    min_scored_dimensions_per_pillar=P.MIN_SCORED_DIMENSIONS_PER_PILLAR,
)


# --- The exact 40% coverage threshold, and values immediately around it -----

def test_exactly_40_percent_coverage_with_two_scored_dimensions_passes() -> None:
    dims = (
        _dim("a", 0.20, 8.0, True),
        _dim("b", 0.20, 6.0, True),
        _dim("c", 0.30, None, False),
        _dim("d", 0.30, None, False),
    )
    coverage = compute_pillar_coverage_pct(dims)
    expect(coverage == 40.0, f"Test setup error: expected exactly 40.0% coverage, got {coverage}")

    result = evaluate_pillar("Boundary Test Pillar", dims, _GATES)
    expect(result.publishable, f"Exactly 40.0% (the floor itself, not strictly below it) must pass gate 1, got withheld: {result.withhold_reasons}")
    expect(result.strength is not None, "A publishable pillar must expose a real Strength")


def test_just_below_40_percent_coverage_fails_the_gate() -> None:
    dims = (
        _dim("a", 0.199, 8.0, True),
        _dim("b", 0.20, 6.0, True),
        _dim("c", 0.301, None, False),
        _dim("d", 0.30, None, False),
    )
    coverage = compute_pillar_coverage_pct(dims)
    expect(coverage < 40.0, f"Test setup error: expected coverage just below 40.0%, got {coverage}")

    result = evaluate_pillar("Boundary Test Pillar", dims, _GATES)
    expect(not result.publishable, f"Coverage just below the 40% floor must be withheld, got publishable with {coverage}%")
    expect(result.strength is None, "A withheld pillar's Strength must be None")
    expect(
        any("coverage" in reason for reason in result.withhold_reasons),
        f"The withhold reason must name the coverage floor, got {result.withhold_reasons}",
    )


def test_just_above_40_percent_coverage_passes_when_dimension_count_also_clears() -> None:
    dims = (
        _dim("a", 0.201, 8.0, True),
        _dim("b", 0.20, 6.0, True),
        _dim("c", 0.299, None, False),
        _dim("d", 0.30, None, False),
    )
    coverage = compute_pillar_coverage_pct(dims)
    expect(coverage > 40.0, f"Test setup error: expected coverage just above 40.0%, got {coverage}")

    result = evaluate_pillar("Boundary Test Pillar", dims, _GATES)
    expect(result.publishable, f"Coverage just above the floor with 2 scored dimensions must be publishable, got withheld: {result.withhold_reasons}")


# --- The two-scored-dimension minimum, tested independently of coverage -----

def test_two_scored_dimensions_is_the_exact_minimum_that_passes() -> None:
    dims = (
        _dim("a", 0.25, 7.0, True),
        _dim("b", 0.25, 5.0, True),
        _dim("c", 0.25, None, False),
        _dim("d", 0.25, None, False),
    )
    result = evaluate_pillar("Boundary Test Pillar", dims, _GATES)
    expect(result.publishable, f"Exactly 2 scored dimensions (the minimum) with 50% coverage must pass, got: {result.withhold_reasons}")


def test_one_scored_dimension_fails_the_count_gate_even_with_generous_coverage() -> None:
    # A single dimension weighted well above the 40% floor alone --
    # isolates gate 2 from gate 1 (coverage is not the limiting factor
    # here at all).
    dims = (
        _dim("big", 0.70, 9.0, True),
        _dim("small_a", 0.15, None, False),
        _dim("small_b", 0.15, None, False),
    )
    coverage = compute_pillar_coverage_pct(dims)
    expect(coverage >= P.MIN_PILLAR_COVERAGE_PCT, f"Test setup error: expected coverage to clear the floor alone, got {coverage}")

    result = evaluate_pillar("Boundary Test Pillar", dims, _GATES)
    expect(not result.publishable, "A single scored dimension must be withheld by the count gate regardless of how much coverage it alone provides")
    expect(result.strength is None, "A withheld pillar must never expose its raw single-dimension value as Strength")
    expect(
        len(result.withhold_reasons) == 1 and "scored dimension" in result.withhold_reasons[0],
        f"Expected exactly one reason, naming only the count gate (coverage already clears its own floor), got {result.withhold_reasons}",
    )


def test_heavily_weighted_single_dimension_case_is_re_verified_at_exactly_the_coverage_floor() -> None:
    # A single dimension whose weight is EXACTLY the coverage floor
    # (40.0%) -- both the most literal version of "clears the coverage
    # threshold alone" and a second confirmation that gate 1 passing at
    # the exact boundary does not, by itself, satisfy gate 2.
    dims = (
        _dim("big", 0.40, 9.0, True),
        _dim("rest", 0.60, None, False),
    )
    coverage = compute_pillar_coverage_pct(dims)
    expect(coverage == 40.0, f"Test setup error: expected exactly 40.0%, got {coverage}")

    result = evaluate_pillar("Boundary Test Pillar", dims, _GATES)
    expect(not result.publishable, "A single dimension exactly at the coverage floor must still fail the count gate")
    expect(
        not any("coverage" in reason for reason in result.withhold_reasons),
        f"Coverage itself is not the failing gate here (it exactly clears its own floor) -- "
        f"only the count gate should be named, got {result.withhold_reasons}",
    )


# --- Missing evidence must never inflate what is published ------------------

def test_missing_evidence_for_the_weak_dimensions_cannot_surface_the_strong_one_alone() -> None:
    # The exact abuse case this whole gate mechanism exists to prevent
    # (spec Part 6.2, restated as a top-level Design Principle): if a
    # pillar's three weaker dimensions are missing/unavailable, the one
    # remaining strong dimension's raw value (9.0) must never be shown as
    # if it were the pillar's real Strength.
    dims = (
        _dim("strong", 0.25, 9.0, True),
        _dim("weak_1_missing", 0.25, None, False),
        _dim("weak_2_missing", 0.25, None, False),
        _dim("weak_3_missing", 0.25, None, False),
    )
    result = evaluate_pillar("Boundary Test Pillar", dims, _GATES)
    raw_single_dimension_value = compute_pillar_strength(dims)
    expect(raw_single_dimension_value == 9.0, "Test setup error: the raw renormalized value should equal the lone scored dimension")
    expect(not result.publishable, "3 of 4 dimensions missing (25% coverage) must be withheld")
    expect(
        result.strength is None,
        f"The pillar must never publish the raw single-dimension value ({raw_single_dimension_value}) as its Strength",
    )


def test_missing_evidence_does_not_change_the_shown_strength_when_the_pillar_still_publishes() -> None:
    # When enough evidence remains to clear both gates, the shown Strength
    # must reflect ONLY the present dimensions -- not be nudged by the
    # fact that other dimensions are missing (renormalization excludes
    # them entirely, neither as a zero nor as an implicit average).
    with_two_scored = (
        _dim("a", 0.25, 4.0, True),
        _dim("b", 0.25, 6.0, True),
        _dim("c_missing", 0.25, None, False),
        _dim("d_missing", 0.25, None, False),
    )
    result = evaluate_pillar("Boundary Test Pillar", with_two_scored, _GATES)
    expect(result.publishable, f"2 of 4 scored (50% coverage) must publish, got: {result.withhold_reasons}")
    expect(result.strength == 5.0, f"Strength must be exactly the average of the 2 present dimensions (4.0, 6.0), got {result.strength}")


TESTS = [
    test_exactly_40_percent_coverage_with_two_scored_dimensions_passes,
    test_just_below_40_percent_coverage_fails_the_gate,
    test_just_above_40_percent_coverage_passes_when_dimension_count_also_clears,
    test_two_scored_dimensions_is_the_exact_minimum_that_passes,
    test_one_scored_dimension_fails_the_count_gate_even_with_generous_coverage,
    test_heavily_weighted_single_dimension_case_is_re_verified_at_exactly_the_coverage_floor,
    test_missing_evidence_for_the_weak_dimensions_cannot_surface_the_strong_one_alone,
    test_missing_evidence_does_not_change_the_shown_strength_when_the_pillar_still_publishes,
]


def main() -> None:
    print("\nVentureGPS Evidence Engine -- coverage/gate boundary tests")
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
