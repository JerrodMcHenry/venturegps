"""
Task 25 -- LINEAR_002 remediation: deterministic routing completeness
(eligibility vs. applicability) and relevance/routing observability.

Every test proves a GENERAL rule using representative fixtures shaped
like LINEAR_002's own actual failures, per that task's own "test general
rules" discipline (carried over from Task 23). No test makes a network
call; no test changes methodology (no pillar file, no `parameters.py`).

Run with:
    python -m app.evidence_engine.tests.test_routing_completeness_and_observability
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.acquisition.claim_identity import compute_independence_group_id
from app.evidence_engine.acquisition.extraction import _sanitize_assessment_criteria
from app.evidence_engine.acquisition.fakes import FakeEvidenceExtractor, FakeSearchProvider, FakeSourceRetriever
from app.evidence_engine.acquisition.models import (
    ClaimRoutingRecord,
    CompanyAnalysisInput,
    ExtractedClaimCandidate,
    ResearchTopic,
    RetrievedSource,
    RoutingDecision,
    SearchResult,
)
from app.evidence_engine.acquisition.pipeline import run_acquisition_pipeline
from app.evidence_engine.acquisition.research_plan import _TOPIC_QUERY_TEMPLATES
from app.evidence_engine.acquisition.routing import (
    CONTEXT_ONLY_KINDS,
    FACT_KIND_ALLOWED_CRITERIA,
    RoutingStatus,
    route_candidate,
)
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim, SourceType, SupportStatus
from app.evidence_engine.pillars.team_leadership import evaluate_leadership_composition
from app.evidence_engine.stage import Stage

AS_OF = date(2026, 9, 29)
CO = "routingco"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _candidate(criteria: list[str] | None = None, structured_fact: dict | None = None, subject_relationship: str | None = None) -> ExtractedClaimCandidate:
    return ExtractedClaimCandidate(
        source_id="s1", claim_text="a claim", subject_entity="TestCo", excerpt="some grounded text",
        assessment_criteria=criteria or [], structured_fact=structured_fact, subject_relationship=subject_relationship,
    )


# --- A. Eligibility vs. applicability -----------------------------------------

_GOOD_FUNDING_ROUND = {
    "kind": "funding_round", "amount": "82000000", "currency": "USD",
    "financing_type": "equity", "round_date": "2019-06-10", "status": "completed",
}
_LINEAR_002_FUNDING_ROUND_SHAPE = {  # missing financing_type/round_date; amount unparseable
    "kind": "funding_round", "amount": "$1.25B", "currency": "USD",
    "metric": "valuation", "named_entity": "Linear", "period_date": "June 2025",
}
_GOOD_FOUNDING_YEAR = {"kind": "founding_year", "value": "2019", "named_entity": "TestCo"}
_LINEAR_002_FOUNDING_YEAR_SHAPE = {"kind": "founding_year", "amount": "2019", "named_entity": "TestCo"}


def test_well_structured_funding_round_rescued_despite_wrong_proposal() -> None:
    c = _candidate(criteria=["commercial_validation", "growth_trajectory"], structured_fact=_GOOD_FUNDING_ROUND)
    result = route_candidate(c)
    expect(result.status == RoutingStatus.ROUTED, str(result))
    expect(result.final_criteria == ("funding_history",), str(result.final_criteria))
    expect(result.added_criteria == ("funding_history",), "must be recorded as a deterministic fallback addition")


def test_linear_002_funding_round_shape_is_honestly_unrouted_not_silently_dropped() -> None:
    """The exact real LINEAR_002 shape: even after the fix, this specific
    fact correctly stays unrouted (it genuinely lacks financing_type/
    round_date) -- but it is now EXPLAINED, not silently empty."""
    c = _candidate(criteria=["commercial_validation", "growth_trajectory"], structured_fact=_LINEAR_002_FUNDING_ROUND_SHAPE)
    result = route_candidate(c)
    expect(result.final_criteria == (), "genuinely insufficient structure must still end up unrouted")
    expect(result.status in (RoutingStatus.REJECTED_INVALID_ROUTING, RoutingStatus.UNROUTED_INSUFFICIENT_STRUCTURE), str(result.status))
    expect(len(result.reason) > 0, "the reason must never be empty -- this is the whole point of the fix")


def test_well_structured_funding_round_with_correct_proposal_routes_normally() -> None:
    c = _candidate(criteria=["funding_history"], structured_fact=_GOOD_FUNDING_ROUND)
    result = route_candidate(c)
    expect(result.status == RoutingStatus.ROUTED and result.added_criteria == (), "a correct proposal needs no fallback")


def test_founding_year_with_correct_value_field_routes_to_stage_signal() -> None:
    c = _candidate(criteria=["disclosed_scale"], structured_fact=_GOOD_FOUNDING_YEAR)
    result = route_candidate(c)
    expect(result.status == RoutingStatus.ROUTED and result.final_criteria == ("stage_signal",), str(result))


def test_linear_002_founding_year_shape_is_honestly_unrouted() -> None:
    """The real LINEAR_002 field-name mismatch ('amount' instead of the
    'value' field stage.py actually reads) -- item 5's own investigation
    confirms a real consumer DOES exist (stage.py), so this is
    insufficient-structure, never NO_METHODOLOGY_CONSUMER."""
    c = _candidate(criteria=["disclosed_scale"], structured_fact=_LINEAR_002_FOUNDING_YEAR_SHAPE)
    result = route_candidate(c)
    expect(result.final_criteria == (), str(result))
    expect(result.status != RoutingStatus.UNROUTED_NO_METHODOLOGY_CONSUMER,
           "a real consumer (stage.py) exists for founding_year -- this must never be classified as having none")


def test_funding_round_type_with_recognized_value_routes_to_stage_signal() -> None:
    c = _candidate(criteria=["disclosed_scale"], structured_fact={"kind": "funding_round_type", "value": "Series C"})
    result = route_candidate(c)
    expect(result.status == RoutingStatus.ROUTED and result.final_criteria == ("stage_signal",), str(result))


def test_funding_round_type_with_unrecognized_value_stays_unrouted() -> None:
    c = _candidate(criteria=["stage_signal"], structured_fact={"kind": "funding_round_type", "value": "some vague financing language"})
    result = route_candidate(c)
    expect(result.final_criteria == (), "a value that maps to no real Stage must never be routed")


def test_team_identity_is_always_context_only() -> None:
    c = _candidate(criteria=["team_identity"], structured_fact={"kind": "team_identity", "person_id": "p1", "role": "founder"})
    result = route_candidate(c)
    expect(result.status == RoutingStatus.CONTEXT_ONLY, str(result.status))
    expect(result.final_criteria == ("team_identity",), "context-only criteria pass through unchanged")


def test_strategic_statement_is_always_context_only() -> None:
    c = _candidate(criteria=["strategic_consistency"], structured_fact={"kind": "strategic_statement", "topic": "mission"})
    result = route_candidate(c)
    expect(result.status == RoutingStatus.CONTEXT_ONLY, str(result.status))


def test_no_structured_fact_passes_through_as_routed() -> None:
    c = _candidate(criteria=["differentiation_claim_corroboration"], structured_fact=None)
    result = route_candidate(c)
    expect(result.status == RoutingStatus.ROUTED and result.final_criteria == ("differentiation_claim_corroboration",), str(result))


def test_partial_overlap_keeps_only_the_valid_tag() -> None:
    c = _candidate(criteria=["funding_history", "commercial_validation"], structured_fact=_GOOD_FUNDING_ROUND)
    result = route_candidate(c)
    expect(result.final_criteria == ("funding_history",), str(result.final_criteria))
    expect("commercial_validation" in result.removed_criteria, str(result.removed_criteria))


def test_proposal_targets_eligible_dimension_but_structure_insufficient() -> None:
    """Distinguishes UNROUTED_INSUFFICIENT_STRUCTURE from REJECTED_
    INVALID_ROUTING: here the model's AIM was correct."""
    c = _candidate(criteria=["funding_history"], structured_fact=_LINEAR_002_FUNDING_ROUND_SHAPE)
    result = route_candidate(c)
    expect(result.status == RoutingStatus.UNROUTED_INSUFFICIENT_STRUCTURE, str(result.status))


def test_unrecognized_kind_reports_no_methodology_consumer() -> None:
    """Proves the mechanism itself is complete, even though none of this
    engine's real 18 kinds currently reach this path (all have a real
    consumer by construction) -- a synthetic kind constructed directly
    against route_candidate(), not through the real pipeline (which
    would already reject an unrecognized kind at validate_candidate())."""
    c = _candidate(criteria=["funding_history"], structured_fact={"kind": "a_kind_no_pillar_or_stage_resolver_reads"})
    result = route_candidate(c)
    expect(result.status == RoutingStatus.UNROUTED_NO_METHODOLOGY_CONSUMER, str(result.status))


# --- B. Item 11's invariants ---------------------------------------------------

def test_invalid_model_routing_cannot_broaden_evidence() -> None:
    c = _candidate(criteria=["differentiation_claim_corroboration", "market_growth_signal"], structured_fact=_GOOD_FUNDING_ROUND)
    result = route_candidate(c)
    expect(set(result.final_criteria) <= FACT_KIND_ALLOWED_CRITERIA["funding_round"], str(result.final_criteria))
    expect("differentiation_claim_corroboration" not in result.final_criteria, "must never reach Product Quality")


def test_empty_bad_proposal_does_not_destroy_deterministically_applicable_evidence() -> None:
    c = _candidate(criteria=["strategic_consistency"], structured_fact=_GOOD_FUNDING_ROUND)  # entirely wrong proposal
    result = route_candidate(c)
    expect(result.status == RoutingStatus.ROUTED and result.final_criteria == ("funding_history",),
           "a sufficiently-structured fact must still reach its real dimension even from a totally wrong proposal")


def test_context_remains_context_never_counted_by_a_real_classifier() -> None:
    """End-to-end through the REAL pillar evaluator: a team_identity
    claim additionally (incorrectly) tagged leadership_composition still
    contributes NOTHING to that dimension, because the downstream
    classifier's own kind check (unchanged) never matches team_identity."""
    claim = Claim(
        claim_id="c1", company_ref=CO, claim_text="team identity claim", subject_entity="TestCo",
        source_publisher="a source", source_type=SourceType.COMPANY_DISCLOSURE, retrieved_at=AS_OF, published_at=AS_OF,
        support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt="x",
        assessment_criteria=["team_identity", "leadership_composition"], independence_group_id="g1",
        structured_fact={"kind": "team_identity", "person_id": "p1", "role": "founder"},
    )
    ledger = EvidenceLedger.from_list([claim])
    result = evaluate_leadership_composition(ledger, CO, AS_OF, Stage.SEED)
    expect(result.score is None and result.supporting_claim_ids == (), f"context-only evidence must never score, got {result}")


def test_removing_routing_cannot_increase_strength() -> None:
    """A claim that fails to route (insufficient structure) contributes
    strictly less than an otherwise-identical, sufficiently-structured
    one -- never more."""
    unrouted = route_candidate(_candidate(criteria=["funding_history"], structured_fact=_LINEAR_002_FUNDING_ROUND_SHAPE))
    routed = route_candidate(_candidate(criteria=["funding_history"], structured_fact=_GOOD_FUNDING_ROUND))
    expect(len(unrouted.final_criteria) <= len(routed.final_criteria), "unrouted must never end up MORE routed than a valid equivalent")


def test_company_identity_invariance_for_routing() -> None:
    a = _candidate(criteria=["commercial_validation"], structured_fact=_GOOD_FUNDING_ROUND).model_copy(update={"subject_entity": "FamousCo"})
    b = _candidate(criteria=["commercial_validation"], structured_fact=_GOOD_FUNDING_ROUND).model_copy(update={"subject_entity": "ObscureCo"})
    ra, rb = route_candidate(a), route_candidate(b)
    expect(ra.status == rb.status and ra.final_criteria == rb.final_criteria, "routing must never depend on company/subject identity")


def test_duplicate_evidence_remains_duplicate_regardless_of_routing_outcome() -> None:
    """independence_group_id computation (claim_identity.py, unchanged)
    is untouched by whether routing rescued a claim or not."""
    c1 = _candidate(criteria=["commercial_validation"], structured_fact=_GOOD_FUNDING_ROUND)
    c2 = _candidate(criteria=["funding_history"], structured_fact=_GOOD_FUNDING_ROUND)
    expect(compute_independence_group_id(c1, CO) == compute_independence_group_id(c2, CO),
           "the SAME underlying fact must still group identically no matter how assessment_criteria was proposed")


def test_missing_structure_remains_missing_never_fabricated() -> None:
    fact_before = dict(_LINEAR_002_FUNDING_ROUND_SHAPE)
    c = _candidate(criteria=["funding_history"], structured_fact=fact_before)
    route_candidate(c)
    expect(c.structured_fact == fact_before, "route_candidate() must never mutate or backfill a fact's own fields")


# --- C. Regression fixtures from LINEAR_002 (item 12) --------------------------

def test_founder_background_task_23_behavior_unaffected() -> None:
    """Updated by Task 27: `founder_experience` now has a verified
    `fact_contracts.py` applicability check (it did not yet under Task 25
    alone), so a FULLY well-structured fact (value/person_id/named_entity
    all present) is now correctly rescued by the deterministic fallback
    even from a wrong proposal -- Task 25's own routing MECHANISM is
    unchanged (this is the exact same fallback branch its own tests
    already prove), only the COVERAGE grew, exactly as intended."""
    c = _candidate(
        criteria=["leadership_composition", "public_track_record"],
        structured_fact={"kind": "founder_experience", "value": "DIRECT", "person_id": "p1", "named_entity": "PriorCo"},
    )
    result = route_candidate(c)
    expect(result.final_criteria == ("founder_relevant_experience",),
           f"Task 27: a fully-structured founder_experience fact must now be rescued, got {result.final_criteria}")
    expect(result.added_criteria == ("founder_relevant_experience",), str(result.added_criteria))

    sanitized = _sanitize_assessment_criteria(_candidate(
        criteria=["founder_relevant_experience"],
        structured_fact={"kind": "founder_experience", "value": "DIRECT", "person_id": "p1", "named_entity": "PriorCo"},
    ))
    expect(sanitized.assessment_criteria == ["founder_relevant_experience"], str(sanitized.assessment_criteria))


def test_person_identity_regression_still_correct() -> None:
    from app.evidence_engine.acquisition.claim_identity import finalize_claim
    src = RetrievedSource.from_url(
        url="https://a.example/x", title="t", publisher="a.example", source_type=SourceType.INDEPENDENT_REPORTING,
        content="Jane Doe is the co-founder and CEO.", retrieved_at=AS_OF, discovered_by_query="q",
        discovered_by_topic=ResearchTopic.TEAM_AND_LEADERSHIP,
    )
    cand = ExtractedClaimCandidate(
        source_id=src.source_id, claim_text="Jane Doe is CEO", subject_entity="Jane Doe", excerpt="Jane Doe is the co-founder and CEO.",
        assessment_criteria=["team_identity"], structured_fact={"kind": "team_identity", "named_entity": "Jane Doe", "role": "Co-founder and CEO"},
    )
    claim = finalize_claim(cand, src, CO)
    expect(claim.structured_fact.get("person_id") is not None, "Task 23's person-identity backfill must still work")


def test_relevance_disposition_now_inspectable() -> None:
    """LINEAR_002's own observability gap, closed: subject_relationship
    before/after and what it removed are now on routing_decision."""
    c = _candidate(criteria=["differentiation_claim_corroboration", "timing_catalyst"], subject_relationship="unrelated_third_party")
    sanitized = _sanitize_assessment_criteria(c)
    d = sanitized.routing_decision
    expect(d is not None, "routing_decision must always be attached once sanitization has run")
    expect(d.proposed_subject_relationship == "unrelated_third_party", str(d.proposed_subject_relationship))
    expect(d.final_subject_relationship == "unrelated_third_party", str(d.final_subject_relationship))
    expect("differentiation_claim_corroboration" in d.relevance_removed_criteria, str(d.relevance_removed_criteria))
    expect(sanitized.assessment_criteria == ["timing_catalyst"], str(sanitized.assessment_criteria))


# --- D. Telemetry / observability (items 8-9) ----------------------------------

def test_routing_decision_lives_on_candidate_not_on_claim() -> None:
    """Item 8's own 'rather than polluting core scoring models' --
    structural check that Claim itself never gained this field."""
    import app.evidence_engine.models as core_models
    expect("routing_decision" not in Claim.model_fields, "Claim (the canonical, methodology-facing model) must never carry this")
    expect("routing_decision" in ExtractedClaimCandidate.model_fields, "the acquisition-layer candidate is where it belongs")


def test_pipeline_populates_claim_routing_telemetry_end_to_end() -> None:
    """The real, unmodified pipeline, a fake extractor proposing the
    WRONG criteria for a well-structured funding_round fact -- proves
    the fix works through the actual shipped call path, not only via
    route_candidate() in isolation."""
    topic = ResearchTopic.FUNDING_AND_FINANCIALS
    query_text = _TOPIC_QUERY_TEMPLATES[topic][0][0].format(company="TestCo")
    url = "https://x.example/funding"
    sr = SearchResult(url=url, title=url, snippet="...", query_text=query_text, topic=topic)
    src = RetrievedSource.from_url(
        url=url, title=url, publisher="x.example", source_type=SourceType.INDEPENDENT_REPORTING,
        content="TestCo raised $82M in a completed equity round on 2019-06-10.", retrieved_at=AS_OF,
        discovered_by_query=query_text, discovered_by_topic=topic,
    )
    cand = ExtractedClaimCandidate(
        source_id=src.source_id, claim_text="TestCo raised $82M", subject_entity="TestCo",
        excerpt="TestCo raised $82M in a completed equity round on 2019-06-10.",
        assessment_criteria=["commercial_validation"],  # deliberately wrong
        structured_fact=_GOOD_FUNDING_ROUND,
    )
    search = FakeSearchProvider(results_by_query={query_text: (sr,)})
    retriever = FakeSourceRetriever(sources_by_url={url: src})
    extractor = FakeEvidenceExtractor(candidates_by_source_id={src.source_id: (cand,)})
    result = run_acquisition_pipeline(
        CompanyAnalysisInput(company_name="TestCo", website_url="https://testco.example", as_of=AS_OF),
        search, retriever, extractor,
    )
    expect(len(result.ledger.claims) == 1 and result.ledger.claims[0].assessment_criteria == ["funding_history"],
           f"got {[(c.claim_id, c.assessment_criteria) for c in result.ledger.claims]}")
    expect(len(result.telemetry.claim_routing) == 1, str(result.telemetry.claim_routing))
    record = result.telemetry.claim_routing[0]
    expect(record.claim_id == result.ledger.claims[0].claim_id, "the routing record must be keyed by the real, finalized claim_id")
    expect(record.decision.status == RoutingStatus.ROUTED.value, str(record.decision.status))
    expect(record.decision.added_criteria == ["funding_history"], str(record.decision.added_criteria))


def test_ai_cannot_invent_a_methodology_criterion_via_the_full_sanitize_pipeline() -> None:
    c = _candidate(criteria=["overall_score", "funding_history"], structured_fact=_GOOD_FUNDING_ROUND)
    sanitized = _sanitize_assessment_criteria(c)
    expect(sanitized.assessment_criteria == ["funding_history"], str(sanitized.assessment_criteria))


def test_ai_cannot_broaden_allowed_routing_even_via_the_fallback_path() -> None:
    """The deterministic fallback only ever fills in what the FACT
    justifies -- never anything merely eligible-in-general that the AI
    might have wished for instead."""
    c = _candidate(criteria=["timing_catalyst"], structured_fact=_GOOD_FUNDING_ROUND)
    result = route_candidate(c)
    expect(result.final_criteria == ("funding_history",), "the fallback must add only what THIS fact's own kind justifies, nothing else")


TESTS = [
    test_well_structured_funding_round_rescued_despite_wrong_proposal,
    test_linear_002_funding_round_shape_is_honestly_unrouted_not_silently_dropped,
    test_well_structured_funding_round_with_correct_proposal_routes_normally,
    test_founding_year_with_correct_value_field_routes_to_stage_signal,
    test_linear_002_founding_year_shape_is_honestly_unrouted,
    test_funding_round_type_with_recognized_value_routes_to_stage_signal,
    test_funding_round_type_with_unrecognized_value_stays_unrouted,
    test_team_identity_is_always_context_only,
    test_strategic_statement_is_always_context_only,
    test_no_structured_fact_passes_through_as_routed,
    test_partial_overlap_keeps_only_the_valid_tag,
    test_proposal_targets_eligible_dimension_but_structure_insufficient,
    test_unrecognized_kind_reports_no_methodology_consumer,
    test_invalid_model_routing_cannot_broaden_evidence,
    test_empty_bad_proposal_does_not_destroy_deterministically_applicable_evidence,
    test_context_remains_context_never_counted_by_a_real_classifier,
    test_removing_routing_cannot_increase_strength,
    test_company_identity_invariance_for_routing,
    test_duplicate_evidence_remains_duplicate_regardless_of_routing_outcome,
    test_missing_structure_remains_missing_never_fabricated,
    test_founder_background_task_23_behavior_unaffected,
    test_person_identity_regression_still_correct,
    test_relevance_disposition_now_inspectable,
    test_routing_decision_lives_on_candidate_not_on_claim,
    test_pipeline_populates_claim_routing_telemetry_end_to_end,
    test_ai_cannot_invent_a_methodology_criterion_via_the_full_sanitize_pipeline,
    test_ai_cannot_broaden_allowed_routing_even_via_the_fallback_path,
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
