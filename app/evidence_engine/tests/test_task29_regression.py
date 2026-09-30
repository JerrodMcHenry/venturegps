"""
Task 29 item 13 -- the five named Task 28 regression fixtures, reproduced
from the ACTUAL real evidence shapes documented in
`LIVE_EVALUATION_FISH_AUDIO_002.md` / `LIVE_EVALUATION_NOTION_002.md` /
`LIVE_EVALUATION_CONTRACT_VALIDATION_001.md`, run end-to-end through the
real production pipeline function (`extraction.py::_sanitize_assessment_
criteria()` -- the exact function both `extract_with_recovery()` and
`extract_many()`'s batch-capable path call on every accepted candidate).
Also covers item 19.13 (provenance/dedup unregressed).

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_task29_regression
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.acquisition.claim_identity import compute_independence_group_id, finalize_claim
from app.evidence_engine.acquisition.extraction import _sanitize_assessment_criteria
from app.evidence_engine.acquisition.models import ExtractedClaimCandidate, ResearchTopic, RetrievedSource
from app.evidence_engine.acquisition.routing import RoutingStatus
from app.evidence_engine.models import SourceType

AS_OF = date(2026, 9, 30)
CO = "task29regressionco"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _candidate(criteria: list[str], structured_fact: dict, claim_text: str, excerpt: str) -> ExtractedClaimCandidate:
    return ExtractedClaimCandidate(
        source_id="s1", claim_text=claim_text, subject_entity="TestCo", excerpt=excerpt,
        assessment_criteria=criteria, structured_fact=structured_fact,
    )


def _source(url: str) -> RetrievedSource:
    return RetrievedSource.from_url(
        url=url, title="a source", publisher="a source", source_type=SourceType.INDEPENDENT_REPORTING,
        content="irrelevant page content", retrieved_at=AS_OF, published_at=AS_OF,
        discovered_by_query="q", discovered_by_topic=ResearchTopic.TEAM_AND_LEADERSHIP,
    )


# =============================================================================
# Fixture 1: Person ordering (item 13) -- the real Fish Audio 002 shape.
# =============================================================================

def test_fixture_person_ordering_founder_experience_survives_routing() -> None:
    """`LIVE_EVALUATION_FISH_AUDIO_002.md` §5: Shijia Liao's founder_
    experience claim was classifier-ready but `assessment_criteria`
    ended up `[]` because routing ran before person_id backfill.
    Expected (item 13): deterministic identity exists before
    applicability evaluation, and legitimate routing survives."""
    fact = {"kind": "founder_experience", "named_entity": "Shijia Liao", "value": "DIRECT"}
    candidate = _candidate(
        ["founder_relevant_experience"], fact,
        "Fish Audio's co-founder and Chief Scientist Shijia Liao has direct relevant experience as a former NVIDIA video researcher.",
        "Fish Audio began in the bedroom of co-founder and Chief Scientist Shijia Liao, a former NVIDIA video researcher",
    )
    finalized = _sanitize_assessment_criteria(candidate)
    expect(finalized.routing_decision.status == RoutingStatus.ROUTED.value, finalized.routing_decision.status)
    expect(finalized.assessment_criteria == ["founder_relevant_experience"], finalized.assessment_criteria)
    expect(finalized.structured_fact.get("person_id") is not None, "person_id must be canonical before routing")


# =============================================================================
# Fixture 2: Funding amount (item 13) -- the real Fish Audio 002 shape.
# =============================================================================

def test_fixture_funding_amount_dollar_m_becomes_classifier_ready() -> None:
    """`LIVE_EVALUATION_FISH_AUDIO_002.md` §4/§6: financing_type
    conflation already fixed ("equity"), but amount="52M" blocked
    readiness. Expected: canonical numeric amount when unambiguous."""
    fact = {
        "kind": "funding_round", "amount": "52M", "currency": "USD", "financing_type": "equity",
        "round_date": "2026-08-05", "status": "completed",
    }
    candidate = _candidate(
        ["funding_history"], fact,
        "Fish Audio closed a $52 million seed round on August 5, 2026, led by Coreline Ventures and Capital Today.",
        "Fish Audio, the Palo Alto-based AI voice-generation startup, closed a $52 million seed round on Aug 5, 2026",
    )
    finalized = _sanitize_assessment_criteria(candidate)
    expect(finalized.structured_fact["amount"] == "52000000", finalized.structured_fact["amount"])
    expect(finalized.routing_decision.status == RoutingStatus.ROUTED.value, finalized.routing_decision.status)
    expect(finalized.assessment_criteria == ["funding_history"], finalized.assessment_criteria)


# =============================================================================
# Fixture 3: Metric period (item 13) -- real Notion 002 shapes, both
# directions.
# =============================================================================

def test_fixture_metric_period_explicit_date_canonicalizes_and_routes() -> None:
    """A Task-28-shaped metric where the source DOES state an explicit
    date (e.g. from the cited CNBC article's own publish date reused as
    a plausible as-of statement) -- expected: canonical period
    representation, routed."""
    fact = {
        "kind": "traction_metric", "metric": "revenue", "value_type": "actual",
        "amount": "500000000", "currency": "USD", "period_date": "September 18, 2025",
    }
    candidate = _candidate(
        ["disclosed_scale"], fact,
        "Notion has reached $500 million in annualized revenue as of September 18, 2025.",
        "Notion, whose software gives people a way to write out documents, has reached $500 million in annualized revenue.",
    )
    finalized = _sanitize_assessment_criteria(candidate)
    expect(finalized.structured_fact["period_date"] == "2025-09-18", finalized.structured_fact["period_date"])
    expect(finalized.routing_decision.status == RoutingStatus.ROUTED.value, finalized.routing_decision.status)


def test_fixture_metric_period_genuinely_absent_remains_incomplete() -> None:
    """The REAL Notion 002 shape (`LIVE_EVALUATION_NOTION_002.md` §4):
    `period_date` is absent entirely -- the source never states one.
    Expected (item 13): 'if the original source does not actually
    contain the period, expected behavior is incomplete -- do not
    fabricate it.'"""
    fact = {"kind": "traction_metric", "metric": "revenue", "value_type": "actual", "amount": "500000000", "currency": "USD"}
    candidate = _candidate(
        ["disclosed_scale"], fact,
        "Notion has reached $500 million in annualized revenue.",
        "Notion, whose software gives people a way to write out documents, has reached $500 million in annualized revenue.",
    )
    finalized = _sanitize_assessment_criteria(candidate)
    expect("period_date" not in finalized.structured_fact, "must not fabricate a period_date")
    expect(
        finalized.routing_decision.status == RoutingStatus.UNROUTED_INSUFFICIENT_STRUCTURE.value,
        f"must remain correctly unrouted for missing structure, not semantic rejection: {finalized.routing_decision.status}",
    )
    expect(finalized.assessment_criteria == [], finalized.assessment_criteria)


# =============================================================================
# Fixture 4: Retention false positive (item 13) -- real Notion 002 shape.
# =============================================================================

def test_fixture_retention_false_positive_rejected_zero_score_effect() -> None:
    """`LIVE_EVALUATION_NOTION_002.md` §5: retention_signal="STRONG" from
    adoption/usage evidence. Expected: semantic interpretation rejected;
    zero retention score effect (assessment_criteria excludes the
    dimension, so `evaluate_retention_renewal_signal()` can never see
    this claim at all)."""
    fact = {"kind": "retention_signal", "named_entity": "Notion", "value": "STRONG"}
    candidate = _candidate(
        ["retention_renewal_signal"], fact,
        "About 90% of Notion's business comes from teams of workers using multiplayer features.",
        "He added that about 90% of the business comes from \"multiplayer usage,\" or teams of workers.",
    )
    finalized = _sanitize_assessment_criteria(candidate)
    expect(
        finalized.routing_decision.status == RoutingStatus.UNROUTED_SEMANTICALLY_UNSUPPORTED.value,
        finalized.routing_decision.status,
    )
    expect("retention_renewal_signal" not in finalized.assessment_criteria, finalized.assessment_criteria)
    expect(finalized.structured_fact == fact, "the grounded fact itself must be preserved, not mutated")


# =============================================================================
# Fixture 5: Competitive-structure false positive (item 13) -- real
# Notion 002 shape.
# =============================================================================

def test_fixture_competitive_structure_false_positive_rejected_zero_score_effect() -> None:
    """`LIVE_EVALUATION_NOTION_002.md` §5: competitive_structure=
    "fragmented" from a bare competitor list. Expected: semantic
    interpretation rejected; zero market-structure score effect."""
    fact = {"kind": "competitive_structure", "value": "fragmented"}
    candidate = _candidate(
        ["competitive_landscape_position"], fact,
        "Notion operates in a competitive segment with competitors including Microsoft, Atlassian, and Airtable.",
        "Notion competitors View the competitive landscape for Notion, featuring companies like Microsoft, Atlassian, and Airtable.",
    )
    finalized = _sanitize_assessment_criteria(candidate)
    expect(
        finalized.routing_decision.status == RoutingStatus.UNROUTED_SEMANTICALLY_UNSUPPORTED.value,
        finalized.routing_decision.status,
    )
    expect("competitive_landscape_position" not in finalized.assessment_criteria, finalized.assessment_criteria)


# =============================================================================
# item 19.13 -- provenance/dedup behavior unregressed by canonicalization.
# =============================================================================

def test_canonicalization_does_not_break_independence_group_matching_for_an_already_matching_pair() -> None:
    """Two real, independently-reported restatements of the SAME Fish
    Audio $52M round (`financing_type`/`round_date` already identical,
    already-ISO) must still compute the same independence_group_id after
    this task's changes -- unchanged behavior for the case that already
    worked."""
    fact_a = {"kind": "funding_round", "amount": "52 million", "currency": "USD", "financing_type": "equity", "round_date": "2026-07-28", "status": "completed"}
    fact_b = {"kind": "funding_round", "amount": "52000000", "currency": "USD", "financing_type": "equity", "round_date": "2026-07-28", "status": "completed"}
    candidate_a = _candidate(["funding_history"], fact_a, "claim a", "excerpt a")
    candidate_b = _candidate(["funding_history"], fact_b, "claim b", "excerpt b")
    group_a = compute_independence_group_id(_sanitize_assessment_criteria(candidate_a), CO)
    group_b = compute_independence_group_id(_sanitize_assessment_criteria(candidate_b), CO)
    expect(group_a == group_b, "two claims about the identical round_date/financing_type must still share a group")


def test_canonicalization_improves_matching_for_a_pair_that_only_differed_by_date_format() -> None:
    """A NEW, positive effect of canonicalization: two real restatements
    of the same event differing only in DATE TEXT FORMAT ("Aug 5, 2026"
    vs. "2026-08-05") now correctly compute the SAME independence_group_
    id, where before this task they would have been (incorrectly)
    treated as two different facts by `IDENTITY_KEY_FIELDS["funding_
    round"]`'s own `round_date` sub-field comparison."""
    fact_a = {"kind": "funding_round", "amount": "52000000", "currency": "USD", "financing_type": "equity", "round_date": "Aug 5, 2026", "status": "completed"}
    fact_b = {"kind": "funding_round", "amount": "52000000", "currency": "USD", "financing_type": "equity", "round_date": "2026-08-05", "status": "completed"}
    candidate_a = _candidate(["funding_history"], fact_a, "claim a", "excerpt a")
    candidate_b = _candidate(["funding_history"], fact_b, "claim b", "excerpt b")
    finalized_a = _sanitize_assessment_criteria(candidate_a)
    finalized_b = _sanitize_assessment_criteria(candidate_b)
    expect(finalized_a.structured_fact["round_date"] == "2026-08-05", finalized_a.structured_fact["round_date"])
    group_a = compute_independence_group_id(finalized_a, CO)
    group_b = compute_independence_group_id(finalized_b, CO)
    expect(group_a == group_b, "date-format-only differences must no longer prevent correct grouping")


def test_canonicalization_never_merges_genuinely_different_funding_rounds() -> None:
    """The negative control for the above: two claims about genuinely
    DIFFERENT rounds (different round_date) must still compute different
    groups -- canonicalization narrows FORMAT noise, never merges real
    differences."""
    fact_a = {"kind": "funding_round", "amount": "52000000", "currency": "USD", "financing_type": "equity", "round_date": "2026-08-05", "status": "completed"}
    fact_b = {"kind": "funding_round", "amount": "10000000", "currency": "USD", "financing_type": "equity", "round_date": "2024-01-01", "status": "completed"}
    candidate_a = _candidate(["funding_history"], fact_a, "claim a", "excerpt a")
    candidate_b = _candidate(["funding_history"], fact_b, "claim b", "excerpt b")
    group_a = compute_independence_group_id(_sanitize_assessment_criteria(candidate_a), CO)
    group_b = compute_independence_group_id(_sanitize_assessment_criteria(candidate_b), CO)
    expect(group_a != group_b, "genuinely different rounds must remain distinct groups")


def test_finalize_claim_still_works_end_to_end_after_sanitization_and_canonicalization() -> None:
    """The full real path: `_sanitize_assessment_criteria()` (canonicalize
    + route) followed by `finalize_claim()` (backfill, now a no-op;
    independence grouping; claim_id) -- proving the two functions still
    compose correctly, unchanged from before this task except for the
    ordering fix itself."""
    fact = {"kind": "founder_experience", "named_entity": "Shijia Liao", "value": "DIRECT"}
    candidate = _candidate(
        ["founder_relevant_experience"], fact,
        "Fish Audio's co-founder and Chief Scientist Shijia Liao has direct relevant experience.",
        "co-founder and Chief Scientist Shijia Liao, a former NVIDIA video researcher",
    )
    sanitized = _sanitize_assessment_criteria(candidate)
    claim = finalize_claim(sanitized, _source("https://example.com/fish-audio"), CO)
    expect(claim.assessment_criteria == ["founder_relevant_experience"], claim.assessment_criteria)
    expect(claim.structured_fact.get("person_id") is not None, "finalize_claim's own backfill call must remain a safe no-op, not lose the id")
    expect(claim.claim_id, "a real claim_id must still be computed")
    expect(claim.independence_group_id, "a real independence_group_id must still be computed")


TESTS = [
    test_fixture_person_ordering_founder_experience_survives_routing,
    test_fixture_funding_amount_dollar_m_becomes_classifier_ready,
    test_fixture_metric_period_explicit_date_canonicalizes_and_routes,
    test_fixture_metric_period_genuinely_absent_remains_incomplete,
    test_fixture_retention_false_positive_rejected_zero_score_effect,
    test_fixture_competitive_structure_false_positive_rejected_zero_score_effect,
    test_canonicalization_does_not_break_independence_group_matching_for_an_already_matching_pair,
    test_canonicalization_improves_matching_for_a_pair_that_only_differed_by_date_format,
    test_canonicalization_never_merges_genuinely_different_funding_rounds,
    test_finalize_claim_still_works_end_to_end_after_sanitization_and_canonicalization,
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
