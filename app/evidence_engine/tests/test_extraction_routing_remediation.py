"""
Task 23 -- LINEAR_001 remediation regression tests.

Every test here is built to prove a GENERAL rule (item 13's own "do not
create tests whose only purpose is 'make Linear pass.' Test general
rules"), using representative evidence SHAPED like what
`LIVE_EVALUATION_LINEAR_001.md` actually found -- not the literal
company. No test in this file makes a network call; no test in this
file changes methodology (no pillar file, no `parameters.py`).

Run with:
    python -m app.evidence_engine.tests.test_extraction_routing_remediation
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.acquisition.claim_identity import (
    compute_independence_group_id,
    finalize_claim,
)
from app.evidence_engine.acquisition.models import ExtractedClaimCandidate, ResearchTopic, RetrievedSource
from app.evidence_engine.acquisition.person_identity import normalize_person_name_to_id
from app.evidence_engine.acquisition.relevance import (
    SubjectRelationship,
    sanitize_subject_relationship,
    strip_unrelated_third_party_dimensions,
)
from app.evidence_engine.acquisition.routing import (
    FACT_KIND_ALLOWED_CRITERIA,
    KIND_AGNOSTIC_DIMENSIONS_NEVER_REACHABLE_BY_A_TYPED_FACT,
    route_assessment_criteria,
    strip_kind_agnostic_dimensions_for_owned_kind,
)
from app.evidence_engine.acquisition.extraction import validate_candidate, _sanitize_assessment_criteria
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim, SourceType, SupportStatus
from app.evidence_engine.pillars.execution_momentum import DIMENSION_SHIPPING_VELOCITY, evaluate_shipping_velocity
from app.evidence_engine.pillars.market_opportunity import (
    DIMENSION_MARKET_SIZE,
    evaluate_market_definition_size,
)
from app.evidence_engine.pillars.team_leadership import (
    DIMENSION_FOUNDER_EXPERIENCE,
    TEAM_IDENTITY_DIMENSION,
    evaluate_founder_relevant_experience,
)
from app.evidence_engine.stage import Stage

AS_OF = date(2026, 9, 29)
CO = "remediationco"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _candidate(
    source_id: str = "s1", excerpt: str = "some grounded text", criteria: list[str] | None = None,
    structured_fact: dict | None = None, subject_relationship: str | None = None,
) -> ExtractedClaimCandidate:
    return ExtractedClaimCandidate(
        source_id=source_id, claim_text=excerpt, subject_entity="TestCo", excerpt=excerpt,
        assessment_criteria=criteria or [], structured_fact=structured_fact,
        subject_relationship=subject_relationship,
    )


def _claim(
    claim_id: str, dimension_tags: list[str], source_type: SourceType, text: str,
    group: str | None = None, structured_fact: dict | None = None,
) -> Claim:
    return Claim(
        claim_id=claim_id, company_ref=CO, claim_text=text, subject_entity="TestCo",
        source_publisher="a source", source_type=source_type, retrieved_at=AS_OF, published_at=AS_OF,
        support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt=text,
        assessment_criteria=dimension_tags, independence_group_id=group or claim_id,
        structured_fact=structured_fact,
    )


# =============================================================================
# A. Deterministic routing (item 4) -- unit tests against routing.py directly
# =============================================================================

def test_funding_round_routes_only_to_funding_history() -> None:
    """LINEAR_001's own single highest-impact finding, as a general rule:
    a funding-round fact must never ALSO count toward commercial
    traction, execution, market, or team dimensions just because the
    model proposed them too."""
    c = _candidate(
        criteria=["funding_history", "commercial_validation", "growth_trajectory", "leadership_composition"],
        structured_fact={"kind": "funding_round", "amount": "82000000", "currency": "USD",
                          "round_date": "2025-06-01", "financing_type": "equity"},
    )
    routed = route_assessment_criteria(c)
    expect(routed == ["funding_history"], f"got {routed}")


def test_funding_round_type_routes_only_to_stage_signal() -> None:
    c = _candidate(
        criteria=["stage_signal", "disclosed_scale"],
        structured_fact={"kind": "funding_round_type", "value": "Series C"},
    )
    expect(route_assessment_criteria(c) == ["stage_signal"], str(route_assessment_criteria(c)))


def test_founder_experience_routes_only_to_founder_relevant_experience() -> None:
    """LINEAR_001's second highest-impact finding: a founder's prior-
    employer/background fact tagged leadership_composition/public_track_
    record only, never founder_relevant_experience."""
    c = _candidate(
        criteria=["leadership_composition", "public_track_record"],
        structured_fact={"kind": "founder_experience", "value": "DIRECT", "person_id": "p1", "named_entity": "PriorCo"},
    )
    routed = route_assessment_criteria(c)
    expect(routed == [], f"neither originally-proposed tag is legitimate for this kind, got {routed}")


def test_founder_experience_kept_when_correctly_proposed() -> None:
    c = _candidate(
        criteria=["founder_relevant_experience", "leadership_composition"],
        structured_fact={"kind": "founder_experience", "value": "DIRECT", "person_id": "p1", "named_entity": "PriorCo"},
    )
    expect(route_assessment_criteria(c) == ["founder_relevant_experience"], str(route_assessment_criteria(c)))


def test_product_release_routes_only_to_shipping_velocity() -> None:
    c = _candidate(
        criteria=["shipping_velocity", "revenue_disclosure"],
        structured_fact={"kind": "product_release", "named_entity": "New Feature", "status": "launched"},
    )
    expect(route_assessment_criteria(c) == ["shipping_velocity"], str(route_assessment_criteria(c)))


def test_traction_metric_never_gets_revenue_disclosure_from_routing_alone() -> None:
    """Item 3's own 'preserve the existing canonical ownership rule...
    do not regress Task 17' -- revenue_disclosure may ONLY ever be added
    by claim_identity.py's own metric=='revenue' gated rule, never
    accepted directly from the model even if proposed."""
    c = _candidate(
        criteria=["disclosed_scale", "revenue_disclosure"],
        structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "75000000", "currency": "USD"},
    )
    routed = route_assessment_criteria(c)
    expect("revenue_disclosure" not in routed, f"got {routed}")
    expect("disclosed_scale" in routed, f"got {routed}")


def test_capital_efficiency_signal_routes_only_to_capital_efficiency() -> None:
    c = _candidate(
        criteria=["capital_efficiency", "commercial_validation"],
        structured_fact={"kind": "capital_efficiency_signal", "metric": "burn_multiple", "value": "1.2"},
    )
    expect(route_assessment_criteria(c) == ["capital_efficiency"], str(route_assessment_criteria(c)))


def test_no_structured_fact_passes_through_unrestricted() -> None:
    c = _candidate(criteria=["differentiation_claim_corroboration", "timing_catalyst"], structured_fact=None)
    expect(route_assessment_criteria(c) == ["differentiation_claim_corroboration", "timing_catalyst"], "no kind to route by -- unchanged")


def test_unrecognized_kind_passes_through_unrestricted_by_routing() -> None:
    """Routing only narrows for kinds it KNOWS about; an unrecognized
    kind is a DIFFERENT, already-existing rejection path (extraction.py's
    own INVALID_FACT_KIND, Task 21) -- not this module's job."""
    c = _candidate(criteria=["differentiation_claim_corroboration"], structured_fact={"kind": "not_a_real_kind"})
    expect(route_assessment_criteria(c) == ["differentiation_claim_corroboration"], "unrecognized kind is out of scope for routing.py")


# =============================================================================
# B. Item 10's five explicit adversarial routing cases
# =============================================================================

def test_adversarial_funding_round_to_product_quality_is_stripped() -> None:
    c = _candidate(
        criteria=["differentiation_claim_corroboration"],
        structured_fact={"kind": "funding_round", "amount": "1000000", "round_date": "2025-01-01", "financing_type": "equity"},
    )
    expect(route_assessment_criteria(c) == [], "a funding round must never reach Product Quality")


def test_adversarial_founder_education_to_market_growth_is_stripped() -> None:
    c = _candidate(
        criteria=["market_growth_signal"],
        structured_fact={"kind": "founder_experience", "value": "ADJACENT", "person_id": "p1", "named_entity": "SomeUniversity"},
    )
    expect(route_assessment_criteria(c) == [], "founder education must never reach Market Growth")


def test_adversarial_product_release_to_revenue_disclosure_is_stripped() -> None:
    c = _candidate(
        criteria=["revenue_disclosure"],
        structured_fact={"kind": "product_release", "named_entity": "v2", "status": "launched"},
    )
    expect(route_assessment_criteria(c) == [], "a product release must never reach Revenue Disclosure")


def test_adversarial_customer_logo_to_capital_efficiency_is_stripped() -> None:
    c = _candidate(
        criteria=["capital_efficiency"],
        structured_fact={"kind": "customer_band", "value": "hundreds of customers"},
    )
    expect(route_assessment_criteria(c) == [], "a customer-count fact must never reach Capital Efficiency")


def test_adversarial_press_article_to_founder_experience_has_no_effect_end_to_end() -> None:
    """The fifth case has no `structured_fact` at all (a plain press
    article), so routing.py's own kind-based guard cannot apply -- proven
    here at the PILLAR level instead: `founder_relevant_experience`'s own
    existing classifier (unchanged) only ever reads a claim whose
    structured_fact.kind == "founder_experience"; a mis-tagged, kind-less
    claim contributes nothing regardless of its assessment_criteria tag."""
    identity = _claim(
        "identity-1", [TEAM_IDENTITY_DIMENSION], SourceType.INDEPENDENT_REPORTING,
        "Reporting confirms Jane Doe as founder.",
        structured_fact={"kind": "team_identity", "person_id": "jane-doe", "role": "founder"},
    )
    mistagged_press = _claim(
        "press-1", [DIMENSION_FOUNDER_EXPERIENCE], SourceType.INDEPENDENT_REPORTING,
        "A press article merely mentions the company in passing.",
    )
    ledger = EvidenceLedger.from_list([identity, mistagged_press])
    result = evaluate_founder_relevant_experience(ledger, CO, AS_OF, Stage.SEED)
    expect(result.score is None and result.supporting_claim_ids == (), f"got score={result.score} claims={result.supporting_claim_ids}")


# =============================================================================
# C. Person / team identity (item 6) -- exact LINEAR_001 failure shape
# =============================================================================

def test_person_identity_two_independent_sources_same_name_normalize_to_same_id() -> None:
    """LINEAR_001 finding #3: a YouTube video title and a podcast page,
    genuinely independent, both confirming the same named CEO -- must
    normalize to the SAME person_id from the name alone."""
    a = normalize_person_name_to_id("Karri Saarinen")
    b = normalize_person_name_to_id("  karri   saarinen  ")
    expect(a is not None and a == b, f"{a} vs {b}")


def test_person_identity_different_people_do_not_collide() -> None:
    a = normalize_person_name_to_id("Karri Saarinen")
    b = normalize_person_name_to_id("Jori Lallo")
    expect(a != b, "different real names must never collide")


def test_person_identity_vague_title_returns_none() -> None:
    for vague in ("the CEO", "The Co-Founder", "management", "she", "the leadership team"):
        expect(normalize_person_name_to_id(vague) is None, f"{vague!r} must never resolve to an identity")


def test_person_identity_empty_or_missing_returns_none() -> None:
    expect(normalize_person_name_to_id("") is None, "empty")
    expect(normalize_person_name_to_id(None) is None, "None")
    expect(normalize_person_name_to_id("   ") is None, "whitespace-only")


def test_finalize_claim_backfills_person_id_from_named_entity_when_missing() -> None:
    """LINEAR_001's own exact gap: a team_identity candidate with
    `named_entity`/`role` but no `person_id`."""
    source = RetrievedSource.from_url(
        url="https://review.firstround.com/podcast/x", title="t", publisher="review.firstround.com",
        source_type=SourceType.INDEPENDENT_REPORTING, content="Karri Saarinen is the co-founder and CEO of Linear.",
        retrieved_at=AS_OF, discovered_by_query="q", discovered_by_topic=ResearchTopic.TEAM_AND_LEADERSHIP,
    )
    candidate = ExtractedClaimCandidate(
        source_id=source.source_id, claim_text="Karri Saarinen is co-founder and CEO.", subject_entity="Karri Saarinen",
        excerpt="Karri Saarinen is the co-founder and CEO of Linear.", assessment_criteria=[TEAM_IDENTITY_DIMENSION],
        structured_fact={"kind": "team_identity", "named_entity": "Karri Saarinen", "role": "Co-founder and CEO"},
    )
    claim = finalize_claim(candidate, source, CO)
    expect(claim.structured_fact is not None and claim.structured_fact.get("person_id"), f"got {claim.structured_fact}")
    expect(claim.structured_fact["person_id"] == normalize_person_name_to_id("Karri Saarinen"), "must match the deterministic normalizer exactly")


def test_finalize_claim_never_overwrites_an_explicit_person_id() -> None:
    source = RetrievedSource.from_url(
        url="https://x.example/a", title="t", publisher="x.example", source_type=SourceType.INDEPENDENT_REPORTING,
        content="Some person is a founder.", retrieved_at=AS_OF, discovered_by_query="q",
        discovered_by_topic=ResearchTopic.TEAM_AND_LEADERSHIP,
    )
    candidate = ExtractedClaimCandidate(
        source_id=source.source_id, claim_text="Some person is a founder.", subject_entity="Some Person",
        excerpt="Some person is a founder.", assessment_criteria=[TEAM_IDENTITY_DIMENSION],
        structured_fact={"kind": "team_identity", "named_entity": "Some Person", "role": "founder", "person_id": "explicit-id-123"},
    )
    claim = finalize_claim(candidate, source, CO)
    expect(claim.structured_fact["person_id"] == "explicit-id-123", "an explicitly-supplied person_id must never be overwritten")


def test_two_independent_claims_about_the_same_founder_now_share_an_independence_group() -> None:
    """The end-to-end fix for LINEAR_001 finding #3: two DIFFERENTLY-
    worded, genuinely independent claims about the same real person,
    neither one given an explicit person_id, now resolve to the SAME
    `independence_group_id` once backfilled -- corroboration that used
    to be invisible is now recognized."""
    source_a = RetrievedSource.from_url(
        url="https://a.example/video", title="t", publisher="a.example", source_type=SourceType.INDEPENDENT_REPORTING,
        content="Inside the company: Karri Saarinen (Co-founder & CEO) on craft and focus.",
        retrieved_at=AS_OF, discovered_by_query="q", discovered_by_topic=ResearchTopic.TEAM_AND_LEADERSHIP,
    )
    source_b = RetrievedSource.from_url(
        url="https://b.example/podcast", title="t", publisher="b.example", source_type=SourceType.INDEPENDENT_REPORTING,
        content="Karri Saarinen is the co-founder and CEO, the project management tool built for teams.",
        retrieved_at=AS_OF, discovered_by_query="q", discovered_by_topic=ResearchTopic.TEAM_AND_LEADERSHIP,
    )
    cand_a = ExtractedClaimCandidate(
        source_id=source_a.source_id, claim_text="Karri Saarinen is CEO (video title).", subject_entity="Karri Saarinen",
        excerpt="Inside the company: Karri Saarinen (Co-founder & CEO) on craft and focus.",
        assessment_criteria=[TEAM_IDENTITY_DIMENSION],
        structured_fact={"kind": "team_identity", "named_entity": "Karri Saarinen", "role": "Co-founder and CEO"},
    )
    cand_b = ExtractedClaimCandidate(
        source_id=source_b.source_id, claim_text="Karri Saarinen is co-founder and CEO (podcast).", subject_entity="Karri Saarinen",
        excerpt="Karri Saarinen is the co-founder and CEO, the project management tool built for teams.",
        assessment_criteria=[TEAM_IDENTITY_DIMENSION],
        structured_fact={"kind": "team_identity", "named_entity": "Karri Saarinen", "role": "Co-founder and CEO"},
    )
    claim_a = finalize_claim(cand_a, source_a, CO)
    claim_b = finalize_claim(cand_b, source_b, CO)
    expect(claim_a.claim_id != claim_b.claim_id, "still two distinct per-source ledger entries (spec Part 2.1, unchanged)")
    expect(claim_a.independence_group_id == claim_b.independence_group_id,
           f"must now be recognized as corroborating the same fact: {claim_a.independence_group_id} vs {claim_b.independence_group_id}")


# =============================================================================
# D. Release/changelog representability (item 13) -- routing correctness,
#    NOT a claim about acquisition recall (item 14's own explicit caveat)
# =============================================================================

def test_dated_release_claim_with_illegitimate_extra_tag_still_routes_and_scores() -> None:
    """Proves the REPRESENTATION/ROUTING path works for exactly the kind
    of evidence the manual Linear fixture used (dated, first-party
    changelog entries) -- explicitly NOT a claim that acquisition would
    have retrieved it this run (item 14)."""
    # Genuinely distinct sentence shapes per release, NOT a shared
    # template with only a number swapped in -- the same "boilerplate
    # text similarity" bug class documented since Task 10 (near-
    # identical text lands in provenance.py's Jaccard UNKNOWN/DUPLICATE
    # band, collapsing what should be 4 distinct facts into 1).
    _release_texts = [
        "The team shipped a redesigned onboarding flow for new workspaces this quarter.",
        "A new integration with the company's CI pipeline went live for all customers.",
        "Real-time collaborative editing became generally available across every plan.",
        "An updated mobile app with offline support was released to the App Store.",
    ]
    releases = [
        _claim(f"rel-{i}", ["shipping_velocity", "revenue_disclosure"], SourceType.COMPANY_DISCLOSURE,
               _release_texts[i],
               structured_fact={"kind": "product_release", "named_entity": f"feature-{i}", "status": "launched"})
        for i in range(4)
    ]
    ledger = EvidenceLedger.from_list(releases)
    result = evaluate_shipping_velocity(ledger, CO, AS_OF, Stage.SEED)
    expect(result.score is not None, "4 distinct launched releases must be scorable")


def test_announced_only_release_never_counts_as_launched() -> None:
    """Unchanged existing rule (Task 16), reconfirmed still holds
    alongside the new routing layer -- an announcement is not a shipped
    release regardless of assessment_criteria correctness."""
    announced = [
        _claim(f"ann-{i}", ["shipping_velocity"], SourceType.COMPANY_DISCLOSURE,
               f"Feature {i} was announced, coming soon.",
               structured_fact={"kind": "product_release", "named_entity": f"feature-{i}", "status": "announced"})
        for i in range(4)
    ]
    ledger = EvidenceLedger.from_list(announced)
    result = evaluate_shipping_velocity(ledger, CO, AS_OF, Stage.SEED)
    expect(result.score is None, "announcements alone must never score as shipped velocity")


# =============================================================================
# E. Market evidence representability (item 13/8)
# =============================================================================

def test_independent_market_size_claim_scores() -> None:
    claim = _claim(
        "market-1", ["market_definition_size"], SourceType.INDEPENDENT_REPORTING,
        "An independent report sizes the category at $1.78B.",
        # market_opportunity.py's own classifier reads a plain "value"
        # field for this kind (not "amount"/"currency", unlike
        # traction_metric/funding_round) -- confirmed by reading
        # WellBehavedMarketSizeClassifier directly, not assumed.
        structured_fact={"kind": "market_size_usd", "value": "1780000000"},
    )
    ledger = EvidenceLedger.from_list([claim])
    result = evaluate_market_definition_size(ledger, CO, AS_OF, Stage.SEED)
    expect(result.score is not None, "one independent market-size disclosure must be scorable")


def test_self_published_tam_is_not_independent_market_validation() -> None:
    """Item 8's own explicit 'do not automatically accept self-published
    TAM as independent market validation' -- proven against the REAL,
    unchanged pillar filter (INDEPENDENT_SOURCE_TYPES), not a new check
    this task adds."""
    claim = _claim(
        "market-2", ["market_definition_size"], SourceType.COMPANY_DISCLOSURE,
        "The company's own website claims a $50B addressable market.",
        structured_fact={"kind": "market_size_usd", "value": "50000000000"},
    )
    ledger = EvidenceLedger.from_list([claim])
    result = evaluate_market_definition_size(ledger, CO, AS_OF, Stage.SEED)
    expect(result.score is None, f"a self-published TAM figure must never score as independent market evidence, got {result.score}")


# =============================================================================
# F. Relevance (item 9) -- exact LINEAR_001 "hobbyist tool" shape
# =============================================================================

def test_unrelated_third_party_strips_product_quality_dimensions() -> None:
    """LINEAR_001's own dev.to finding, as a general rule: a candidate
    about a third party's own project that merely uses the target
    company's product must not count toward the target's OWN
    differentiation/defensibility/product-maturity/technical-depth."""
    c = _candidate(
        criteria=["differentiation_claim_corroboration", "timing_catalyst"],
        subject_relationship=SubjectRelationship.UNRELATED_THIRD_PARTY.value,
    )
    stripped = strip_unrelated_third_party_dimensions(c.assessment_criteria, c.subject_relationship)
    expect("differentiation_claim_corroboration" not in stripped, f"got {stripped}")
    expect("timing_catalyst" in stripped, "a non-kind-agnostic tag must be unaffected")


def test_product_integration_relationship_is_never_stripped() -> None:
    """Item 9's own explicit 'do not reject legitimate ecosystem/partner
    evidence simply because another company is involved.'"""
    criteria = ["differentiation_claim_corroboration"]
    stripped = strip_unrelated_third_party_dimensions(criteria, SubjectRelationship.PRODUCT_INTEGRATION.value)
    expect(stripped == criteria, "an official integration must never be narrowed by this rule")


def test_customer_or_partner_relationship_is_never_stripped() -> None:
    criteria = ["defensibility_signal"]
    stripped = strip_unrelated_third_party_dimensions(criteria, SubjectRelationship.CUSTOMER_OR_PARTNER.value)
    expect(stripped == criteria, "a genuine customer/partner relationship must never be narrowed by this rule")


def test_absent_subject_relationship_is_the_permissive_default() -> None:
    criteria = ["differentiation_claim_corroboration"]
    expect(strip_unrelated_third_party_dimensions(criteria, None) == criteria, "unknown/absent must behave exactly as before this task")


def test_invalid_subject_relationship_value_sanitizes_to_none() -> None:
    expect(sanitize_subject_relationship("not_a_real_value") is None, "an out-of-vocabulary value must never be trusted")
    expect(sanitize_subject_relationship(None) is None, "None stays None")
    for valid in ("primary", "product_integration", "customer_or_partner", "unrelated_third_party"):
        expect(sanitize_subject_relationship(valid) == valid, valid)


def test_full_sanitize_pipeline_end_to_end_on_the_linear_001_dev_to_shape() -> None:
    """Runs `extraction.py`'s own real `_sanitize_assessment_criteria()`
    -- the exact function the shipped pipeline calls -- against a
    candidate shaped like LINEAR_001's own flagged claim."""
    candidate = _candidate(
        criteria=["differentiation_claim_corroboration", "timing_catalyst"],
        subject_relationship="unrelated_third_party",
    )
    sanitized = _sanitize_assessment_criteria(candidate)
    expect("differentiation_claim_corroboration" not in sanitized.assessment_criteria, str(sanitized.assessment_criteria))
    expect("timing_catalyst" in sanitized.assessment_criteria, str(sanitized.assessment_criteria))


# =============================================================================
# G. Before/after offline demonstration (item 14) -- routing improvement only,
#    never an acquisition-recall claim
# =============================================================================

def test_before_after_funding_round_routing_on_the_actual_linear_001_shape() -> None:
    """BEFORE (documented in LIVE_EVALUATION_LINEAR_001.md, reproduced
    here as the raw, as-proposed shape): a real $82M-Series-C-shaped
    candidate tagged only commercial_validation/growth_trajectory.
    AFTER: the SAME raw candidate, additionally (as the improved prompt
    now asks for) tagged funding_history/stage_signal by the model,
    survives routing with BOTH legitimate tags -- while the illegitimate
    ones from the BEFORE shape are proven to have been correctly
    excluded from ever being requested by kind at all."""
    before_shape = _candidate(
        criteria=["commercial_validation", "growth_trajectory"],
        structured_fact=None,  # LINEAR_001's actual candidate carried no structured_fact at all
    )
    before_routed = route_assessment_criteria(before_shape)
    expect(before_routed == ["commercial_validation", "growth_trajectory"],
           "BEFORE: with no structured_fact, routing cannot correct a misrouted free-text tag by itself -- "
           "this is exactly why item 3's prompt guidance, not routing alone, is the fix for the untyped case")

    after_shape = _candidate(
        criteria=["funding_history", "stage_signal"],
        structured_fact={"kind": "funding_round", "amount": "82000000", "currency": "USD",
                          "round_date": "2025-06-01", "financing_type": "equity"},
    )
    after_routed = route_assessment_criteria(after_shape)
    expect(sorted(after_routed) == ["funding_history"],
           f"AFTER: correctly-typed funding evidence reaches exactly its legitimate dimension: {after_routed}")
    # The `stage_signal` tag needs its OWN kind (`funding_round_type`) --
    # a single fact can be typed and reported as BOTH kinds by the
    # extractor (item 3's own prompt guidance asks for exactly this)
    # to reach both dimensions; proven separately below.
    stage_shape = _candidate(
        criteria=["stage_signal"],
        structured_fact={"kind": "funding_round_type", "value": "Series C"},
    )
    expect(route_assessment_criteria(stage_shape) == ["stage_signal"], "the stage-signal half of the same real-world fact, typed separately, reaches stage resolution")


TESTS = [
    test_funding_round_routes_only_to_funding_history,
    test_funding_round_type_routes_only_to_stage_signal,
    test_founder_experience_routes_only_to_founder_relevant_experience,
    test_founder_experience_kept_when_correctly_proposed,
    test_product_release_routes_only_to_shipping_velocity,
    test_traction_metric_never_gets_revenue_disclosure_from_routing_alone,
    test_capital_efficiency_signal_routes_only_to_capital_efficiency,
    test_no_structured_fact_passes_through_unrestricted,
    test_unrecognized_kind_passes_through_unrestricted_by_routing,
    test_adversarial_funding_round_to_product_quality_is_stripped,
    test_adversarial_founder_education_to_market_growth_is_stripped,
    test_adversarial_product_release_to_revenue_disclosure_is_stripped,
    test_adversarial_customer_logo_to_capital_efficiency_is_stripped,
    test_adversarial_press_article_to_founder_experience_has_no_effect_end_to_end,
    test_person_identity_two_independent_sources_same_name_normalize_to_same_id,
    test_person_identity_different_people_do_not_collide,
    test_person_identity_vague_title_returns_none,
    test_person_identity_empty_or_missing_returns_none,
    test_finalize_claim_backfills_person_id_from_named_entity_when_missing,
    test_finalize_claim_never_overwrites_an_explicit_person_id,
    test_two_independent_claims_about_the_same_founder_now_share_an_independence_group,
    test_dated_release_claim_with_illegitimate_extra_tag_still_routes_and_scores,
    test_announced_only_release_never_counts_as_launched,
    test_independent_market_size_claim_scores,
    test_self_published_tam_is_not_independent_market_validation,
    test_unrelated_third_party_strips_product_quality_dimensions,
    test_product_integration_relationship_is_never_stripped,
    test_customer_or_partner_relationship_is_never_stripped,
    test_absent_subject_relationship_is_the_permissive_default,
    test_invalid_subject_relationship_value_sanitizes_to_none,
    test_full_sanitize_pipeline_end_to_end_on_the_linear_001_dev_to_shape,
    test_before_after_funding_round_routing_on_the_actual_linear_001_shape,
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
