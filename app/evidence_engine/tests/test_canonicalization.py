"""
Task 29 items 2-5, 19.1-19.5 -- deterministic field canonicalization
(person_id ordering, numeric amount, explicit date) and its invariants.

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_canonicalization
"""

from __future__ import annotations

from app.evidence_engine.acquisition.canonicalization import (
    canonicalize_explicit_date,
    canonicalize_numeric_amount,
    canonicalize_structured_fact,
)
from app.evidence_engine.acquisition.extraction import _sanitize_assessment_criteria
from app.evidence_engine.acquisition.fact_contracts import check_classifier_readiness
from app.evidence_engine.acquisition.models import ExtractedClaimCandidate
from app.evidence_engine.acquisition.person_identity import normalize_person_name_to_id
from app.evidence_engine.acquisition.routing import RoutingStatus


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _candidate(criteria: list[str], structured_fact: dict, claim_text: str = "a claim", excerpt: str = "some grounded text") -> ExtractedClaimCandidate:
    return ExtractedClaimCandidate(
        source_id="s1", claim_text=claim_text, subject_entity="TestCo", excerpt=excerpt,
        assessment_criteria=criteria, structured_fact=structured_fact,
    )


# =============================================================================
# 1. Numeric amount canonicalization (item 4, item 19.3/19.4).
# =============================================================================

def test_dollar_m_suffix_canonicalizes_to_bare_number() -> None:
    expect(canonicalize_numeric_amount("$52M") == "52000000", canonicalize_numeric_amount("$52M"))


def test_bare_m_suffix_canonicalizes_to_bare_number() -> None:
    expect(canonicalize_numeric_amount("52M") == "52000000", canonicalize_numeric_amount("52M"))


def test_word_million_suffix_canonicalizes_to_bare_number() -> None:
    expect(canonicalize_numeric_amount("52 million") == "52000000", canonicalize_numeric_amount("52 million"))


def test_billion_and_thousand_suffixes_canonicalize_correctly() -> None:
    expect(canonicalize_numeric_amount("1.25 billion") == "1250000000", canonicalize_numeric_amount("1.25 billion"))
    expect(canonicalize_numeric_amount("500k") == "500000", canonicalize_numeric_amount("500k"))


def test_comma_separated_bare_number_canonicalizes() -> None:
    expect(canonicalize_numeric_amount("1,250,000") == "1250000", canonicalize_numeric_amount("1,250,000"))


def test_already_bare_number_is_returned_unchanged() -> None:
    """Mathematical value is preserved exactly -- item 19.3 -- and an
    already-canonical string is never needlessly rewritten."""
    for raw in ("52000000", "21", "13.5"):
        expect(canonicalize_numeric_amount(raw) == raw, f"{raw} should be returned unchanged")


def test_ambiguous_range_fails_closed_unchanged() -> None:
    """item 19.4: ambiguous amounts fail closed -- never guessed at."""
    expect(canonicalize_numeric_amount("$50-60M") == "$50-60M", "a range must not be canonicalized")


def test_vague_quantifier_fails_closed_unchanged() -> None:
    expect(canonicalize_numeric_amount("tens of millions") == "tens of millions", "a vague quantifier must not be canonicalized")
    expect(canonicalize_numeric_amount("over $50M") == "over $50M", "an unbounded qualifier must not be canonicalized")
    expect(canonicalize_numeric_amount("approximately 50 million") == "approximately 50 million", "an approximation must not be canonicalized")


def test_none_is_returned_as_none() -> None:
    expect(canonicalize_numeric_amount(None) is None, "None must pass through as None, never a fabricated 0")


def test_currency_field_is_never_touched_by_numeric_canonicalization() -> None:
    """item 4: preserve currency separately; never infer or convert it."""
    fact = {"kind": "funding_round", "financing_type": "equity", "status": "completed", "currency": "USD", "amount": "$52M", "round_date": "2026-08-05"}
    canonical = canonicalize_structured_fact(fact)
    expect(canonical["currency"] == "USD", "currency must be untouched")
    expect(canonical["amount"] == "52000000", canonical["amount"])


def test_missing_currency_is_never_invented() -> None:
    fact = {"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": "$52M", "round_date": "2026-08-05"}
    canonical = canonicalize_structured_fact(fact)
    expect("currency" not in canonical, "a missing currency must never be invented by canonicalization")


def test_funding_amount_canonicalization_makes_the_real_fish_audio_shape_classifier_ready() -> None:
    """The exact real Task 28 Fish Audio 002 shape
    (`LIVE_EVALUATION_FISH_AUDIO_002.md` §4): financing_type already
    fixed to "equity", but amount="52M" blocked readiness."""
    before = {"kind": "funding_round", "financing_type": "equity", "status": "completed", "currency": "USD", "amount": "52M", "round_date": "2026-08-05"}
    expect(not check_classifier_readiness(before), "the real, pre-canonicalization shape must reproduce the documented failure")
    after = canonicalize_structured_fact(before)
    expect(check_classifier_readiness(after), f"canonicalized amount must now be classifier-ready: {after}")
    expect(after["amount"] == "52000000", after["amount"])


# =============================================================================
# 2. Explicit date canonicalization (item 5, item 19.5).
# =============================================================================

def test_explicit_month_name_date_canonicalizes_to_iso() -> None:
    expect(canonicalize_explicit_date("August 5, 2026") == "2026-08-05", canonicalize_explicit_date("August 5, 2026"))
    expect(canonicalize_explicit_date("Aug 5, 2026") == "2026-08-05", canonicalize_explicit_date("Aug 5, 2026"))
    expect(canonicalize_explicit_date("July 28 2026") == "2026-07-28", canonicalize_explicit_date("July 28 2026"))


def test_already_iso_date_is_returned_unchanged() -> None:
    expect(canonicalize_explicit_date("2026-08-05") == "2026-08-05", "already-ISO date must be unchanged")


def test_slash_ymd_date_canonicalizes_to_iso() -> None:
    expect(canonicalize_explicit_date("2026/07/28") == "2026-07-28", canonicalize_explicit_date("2026/07/28"))


def test_bare_year_remains_incomplete_never_fabricated() -> None:
    """item 5's own closing instruction: 'if no qualifying period exists,
    remain incomplete' -- a bare year never becomes a fabricated Jan 1."""
    expect(canonicalize_explicit_date("2026") == "2026", "a bare year must never be expanded to a full date")


def test_year_month_only_remains_incomplete() -> None:
    expect(canonicalize_explicit_date("2026-07") == "2026-07", "a year-month must never be expanded with a fabricated day")


def test_vague_quarter_or_season_remains_incomplete() -> None:
    expect(canonicalize_explicit_date("Q3 2026") == "Q3 2026", "a vague quarter must remain unchanged")
    expect(canonicalize_explicit_date("early 2026") == "early 2026", "a vague season must remain unchanged")


def test_none_date_is_returned_as_none() -> None:
    expect(canonicalize_explicit_date(None) is None, "None must pass through as None")


def test_metric_period_canonicalization_matches_a_real_task_28_notion_shape() -> None:
    """Item 13's own 'metric period' fixture requirement: a Task 28
    metric where the source explicitly contains a period/date must
    canonicalize; where it genuinely does not, it must remain
    incomplete -- both proven here against the real contract."""
    explicit = {"kind": "traction_metric", "metric": "revenue", "value_type": "actual", "amount": "500000000", "currency": "USD", "period_date": "September 18, 2025"}
    canonical = canonicalize_structured_fact(explicit)
    expect(canonical["period_date"] == "2025-09-18", canonical["period_date"])
    expect(check_classifier_readiness(canonical), "an explicit, now-canonical period_date must make this classifier-ready")

    # The REAL Notion 002 shape: period_date is absent entirely (the
    # source genuinely never stated an as-of date the model captured) --
    # canonicalization must not invent one, and readiness correctly
    # remains False.
    missing = {"kind": "traction_metric", "metric": "revenue", "value_type": "actual", "amount": "500000000", "currency": "USD"}
    canonical_missing = canonicalize_structured_fact(missing)
    expect("period_date" not in canonical_missing, "a genuinely absent period must never be fabricated")
    expect(not check_classifier_readiness(canonical_missing), "must remain correctly incomplete")


# =============================================================================
# 3. Person-identity ordering fix (item 2, item 19.1, item 13's "person
# ordering" fixture) -- the central Task 29 regression.
# =============================================================================

def test_person_id_is_canonical_before_routing_applicability_runs() -> None:
    """Reproduces the exact Task 28 shape
    (`LIVE_EVALUATION_FISH_AUDIO_002.md` §5): a founder_experience
    candidate with an explicit named_entity but NO person_id. Before this
    fix, `route_candidate()` saw the pre-backfill fact and permanently
    stripped `founder_relevant_experience`. After this fix, canonicalize-
    before-route means person_id is already present when applicability
    is checked, and the legitimate dimension survives."""
    fact = {"kind": "founder_experience", "named_entity": "Shijia Liao", "value": "DIRECT"}
    expect(fact.get("person_id") is None, "fixture precondition: person_id must start absent, exactly like the real model output")

    candidate = _candidate(["founder_relevant_experience"], fact)
    finalized = _sanitize_assessment_criteria(candidate)

    expect(finalized.structured_fact.get("person_id") is not None, "person_id must be canonical (backfilled) before this function returns")
    expected_id = normalize_person_name_to_id("Shijia Liao")
    expect(finalized.structured_fact["person_id"] == expected_id, "backfilled person_id must match the deterministic derivation")
    expect(
        finalized.assessment_criteria == ["founder_relevant_experience"],
        f"legitimate routing must survive: {finalized.assessment_criteria}",
    )
    expect(
        finalized.routing_decision.status == RoutingStatus.ROUTED.value,
        f"routing status must be ROUTED, not insufficient-structure: {finalized.routing_decision.status}",
    )


def test_track_record_person_id_ordering_is_also_fixed() -> None:
    """Same defect class, the other person_id-requiring kind."""
    fact = {"kind": "track_record", "named_entity": "Ada Example", "value": "PRIOR_EXIT"}
    candidate = _candidate(["public_track_record"], fact)
    finalized = _sanitize_assessment_criteria(candidate)
    expect(finalized.structured_fact.get("person_id") is not None, "person_id must be backfilled before routing")
    expect(finalized.assessment_criteria == ["public_track_record"], finalized.assessment_criteria)


def test_a_model_supplied_person_id_is_never_overwritten() -> None:
    """item 3's own 'do not overwrite explicit conflicting identities' --
    canonicalization only ever FILLS an absence, never replaces a value
    the model itself already supplied."""
    fact = {"kind": "founder_experience", "named_entity": "Shijia Liao", "value": "DIRECT", "person_id": "model_supplied_id_123"}
    canonical = canonicalize_structured_fact(fact)
    expect(canonical["person_id"] == "model_supplied_id_123", "an existing person_id must never be overwritten")


def test_canonicalization_never_invents_a_person_id_from_a_vague_title() -> None:
    """item 3: do not infer a person from a vague title."""
    fact = {"kind": "founder_experience", "named_entity": "the CEO", "value": "DIRECT"}
    canonical = canonicalize_structured_fact(fact)
    expect(canonical.get("person_id") is None, "a vague title must never resolve to a person_id")


def test_two_independent_claims_about_the_same_named_person_resolve_consistently() -> None:
    """item 3's own explicit proof requirement."""
    fact_a = {"kind": "founder_experience", "named_entity": "Shijia Liao", "value": "DIRECT"}
    fact_b = {"kind": "track_record", "named_entity": "Shijia Liao", "value": "PRIOR_EXIT"}
    canonical_a = canonicalize_structured_fact(fact_a)
    canonical_b = canonicalize_structured_fact(fact_b)
    expect(
        canonical_a["person_id"] == canonical_b["person_id"],
        "two independent claims naming the same real person must resolve to the same deterministic person_id",
    )


def test_canonicalization_cannot_invent_unsupported_fields() -> None:
    """item 19.2: canonicalization only ever fills fields deterministically
    derivable from what is ALREADY present (person_id from named_entity,
    a representation change to amount/date) -- it never adds a field with
    no basis in the candidate's own existing data."""
    fact = {"kind": "founder_experience", "value": "DIRECT"}  # no named_entity at all
    canonical = canonicalize_structured_fact(fact)
    expect("person_id" not in canonical, "no named_entity means no basis for a person_id -- none must be invented")
    expect(set(canonical.keys()) == {"kind", "value"}, f"no new, unrelated field may appear: {canonical}")


def test_canonicalize_structured_fact_is_none_safe() -> None:
    expect(canonicalize_structured_fact(None) is None, "None must pass through as None")


def test_canonicalize_structured_fact_leaves_unrecognized_kind_untouched() -> None:
    fact = {"kind": "not_a_real_kind", "amount": "$52M"}
    expect(canonicalize_structured_fact(fact) == fact, "an unrecognized kind has no contract to canonicalize against")


TESTS = [
    test_dollar_m_suffix_canonicalizes_to_bare_number,
    test_bare_m_suffix_canonicalizes_to_bare_number,
    test_word_million_suffix_canonicalizes_to_bare_number,
    test_billion_and_thousand_suffixes_canonicalize_correctly,
    test_comma_separated_bare_number_canonicalizes,
    test_already_bare_number_is_returned_unchanged,
    test_ambiguous_range_fails_closed_unchanged,
    test_vague_quantifier_fails_closed_unchanged,
    test_none_is_returned_as_none,
    test_currency_field_is_never_touched_by_numeric_canonicalization,
    test_missing_currency_is_never_invented,
    test_funding_amount_canonicalization_makes_the_real_fish_audio_shape_classifier_ready,
    test_explicit_month_name_date_canonicalizes_to_iso,
    test_already_iso_date_is_returned_unchanged,
    test_slash_ymd_date_canonicalizes_to_iso,
    test_bare_year_remains_incomplete_never_fabricated,
    test_year_month_only_remains_incomplete,
    test_vague_quarter_or_season_remains_incomplete,
    test_none_date_is_returned_as_none,
    test_metric_period_canonicalization_matches_a_real_task_28_notion_shape,
    test_person_id_is_canonical_before_routing_applicability_runs,
    test_track_record_person_id_ordering_is_also_fixed,
    test_a_model_supplied_person_id_is_never_overwritten,
    test_canonicalization_never_invents_a_person_id_from_a_vague_title,
    test_two_independent_claims_about_the_same_named_person_resolve_consistently,
    test_canonicalization_cannot_invent_unsupported_fields,
    test_canonicalize_structured_fact_is_none_safe,
    test_canonicalize_structured_fact_leaves_unrecognized_kind_untouched,
]


def main() -> None:
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {test.__name__}: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {test.__name__}: {exc!r}")
            failed += 1
    print("-" * 74)
    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
