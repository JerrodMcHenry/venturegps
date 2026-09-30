"""
Task 29 items 6-11, 14, 19.6-19.12 -- deterministic semantic-fit
validation: retention/competitive-structure rules, positive controls,
company-name invariance, and the routing invariants item 19 requires.

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_semantic_fit
"""

from __future__ import annotations

from app.evidence_engine.acquisition.extraction import _sanitize_assessment_criteria
from app.evidence_engine.acquisition.fact_contracts import check_classifier_readiness
from app.evidence_engine.acquisition.models import ExtractedClaimCandidate
from app.evidence_engine.acquisition.routing import RoutingStatus, route_candidate
from app.evidence_engine.acquisition.semantic_fit import (
    SemanticFitStatus,
    check_methodology_readiness,
    check_semantic_fit,
)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _candidate(
    criteria: list[str], structured_fact: dict, claim_text: str, excerpt: str,
) -> ExtractedClaimCandidate:
    return ExtractedClaimCandidate(
        source_id="s1", claim_text=claim_text, subject_entity="TestCo", excerpt=excerpt,
        assessment_criteria=criteria, structured_fact=structured_fact,
    )


# =============================================================================
# 1. Retention rule (item 7) -- the real Task 28 Notion false positive.
# =============================================================================

def test_retention_false_positive_adoption_usage_is_rejected() -> None:
    """The EXACT real, cited excerpt from `LIVE_EVALUATION_NOTION_002.md`
    §5: '~90% of the business comes from multiplayer usage' -- an
    adoption/usage statistic, not retention evidence."""
    fact = {"kind": "retention_signal", "named_entity": "Notion", "value": "STRONG"}
    claim_text = "About 90% of Notion's business comes from teams of workers using multiplayer features."
    excerpt = "He added that about 90% of the business comes from \"multiplayer usage,\" or teams of workers."
    result = check_semantic_fit(fact, claim_text, excerpt)
    expect(result.status == SemanticFitStatus.UNSUPPORTED, f"adoption/usage must not support retention: {result}")


def test_retention_rejects_bare_customer_count() -> None:
    fact = {"kind": "retention_signal", "value": "STRONG"}
    result = check_semantic_fit(fact, "Notion has 100 million users.", "over 100 million users")
    expect(result.status == SemanticFitStatus.UNSUPPORTED, str(result))


def test_retention_rejects_logos_testimonials_longevity_growth_popularity() -> None:
    cases = [
        ("Trusted by Fortune 500 logos.", "Trusted by Fortune 500 companies including Acme and Globex."),
        ("Customers love the product.", "\"This tool changed how our team works,\" said one customer."),
        ("The company has been around for a decade.", "Founded in 2013, the company has operated for over a decade."),
        ("Revenue grew 40% year over year.", "Annual revenue grew 40% year over year."),
        ("The product is extremely popular among startups.", "The product has become extremely popular among startups."),
    ]
    for claim_text, excerpt in cases:
        fact = {"kind": "retention_signal", "value": "STRONG"}
        result = check_semantic_fit(fact, claim_text, excerpt)
        expect(result.status == SemanticFitStatus.UNSUPPORTED, f"{excerpt!r} must not support retention: {result}")


def test_retention_positive_control_explicit_retention_figure() -> None:
    """item 14's own positive control: explicit reported retention."""
    fact = {"kind": "retention_signal", "value": "STRONG"}
    result = check_semantic_fit(
        fact,
        "The company reports 95% net revenue retention.",
        "Net revenue retention stood at 95% for the fiscal year.",
    )
    expect(result.status == SemanticFitStatus.SUPPORTED, str(result))


def test_retention_positive_control_explicit_churn_figure() -> None:
    fact = {"kind": "retention_signal", "value": "WEAK"}
    result = check_semantic_fit(
        fact, "Monthly churn has risen to 8%.", "The company disclosed monthly customer churn of 8%.",
    )
    expect(result.status == SemanticFitStatus.SUPPORTED, str(result))


def test_retention_positive_control_explicit_renewal_language() -> None:
    fact = {"kind": "retention_signal", "value": "MODERATE"}
    result = check_semantic_fit(
        fact, "Most enterprise contracts renew annually.", "About two-thirds of enterprise contracts renew each year.",
    )
    expect(result.status == SemanticFitStatus.SUPPORTED, str(result))


# =============================================================================
# 2. Competitive-structure rule (item 8) -- the real Task 28 Notion false
# positive.
# =============================================================================

def test_competitive_structure_false_positive_bare_competitor_list_is_rejected() -> None:
    """The EXACT real, cited excerpt from `LIVE_EVALUATION_NOTION_002.md`
    §5: a bare competitor list with no structural characterization."""
    fact = {"kind": "competitive_structure", "value": "fragmented"}
    claim_text = "Notion operates in a competitive segment with competitors including Microsoft, Atlassian, and Airtable."
    excerpt = "Notion competitors View the competitive landscape for Notion, featuring companies like Microsoft, Atlassian, and Airtable."
    result = check_semantic_fit(fact, claim_text, excerpt)
    expect(result.status == SemanticFitStatus.UNSUPPORTED, f"a bare competitor list must not support fragmented: {result}")


def test_competitive_structure_rejects_a_bare_concentrated_claim_with_no_vocabulary_either() -> None:
    fact = {"kind": "competitive_structure", "value": "concentrated"}
    result = check_semantic_fit(
        fact, "The market includes Company A, Company B, and Company C.", "Key players include A, B, and C.",
    )
    expect(result.status == SemanticFitStatus.UNSUPPORTED, str(result))


def test_competitive_structure_fragmented_vocabulary_does_not_support_concentrated_value() -> None:
    """A rule must check the SPECIFIC value chosen, never just 'some
    structural word appeared somewhere'."""
    fact = {"kind": "competitive_structure", "value": "concentrated"}
    result = check_semantic_fit(
        fact, "The market is highly fragmented.", "Analysts describe the market as highly fragmented with no clear leader.",
    )
    expect(result.status == SemanticFitStatus.UNSUPPORTED, "fragmented-supporting text must not validate a 'concentrated' value")


def test_competitive_structure_positive_control_explicit_fragmentation_report() -> None:
    """item 14's own positive control: an independent market report
    explicitly describing fragmentation."""
    fact = {"kind": "competitive_structure", "value": "fragmented"}
    result = check_semantic_fit(
        fact,
        "The voice AI market remains highly fragmented.",
        "The voice AI market remains highly fragmented with no single dominant player, per the report.",
    )
    expect(result.status == SemanticFitStatus.SUPPORTED, str(result))


def test_competitive_structure_positive_control_explicit_concentration_report() -> None:
    fact = {"kind": "competitive_structure", "value": "concentrated"}
    result = check_semantic_fit(
        fact,
        "The cloud infrastructure market is concentrated.",
        "The report finds the cloud infrastructure market concentrated, dominated by three major players.",
    )
    expect(result.status == SemanticFitStatus.SUPPORTED, str(result))


# =============================================================================
# 3. NOT_APPLICABLE for kinds with no defined rule (never a false "pass").
# =============================================================================

def test_kind_with_no_rule_is_not_applicable_never_supported_or_unsupported() -> None:
    fact = {"kind": "founder_experience", "value": "DIRECT", "named_entity": "Ada Example", "person_id": "p1"}
    result = check_semantic_fit(fact, "irrelevant text", "irrelevant text")
    expect(result.status == SemanticFitStatus.NOT_APPLICABLE, str(result))


def test_none_fact_is_not_applicable() -> None:
    result = check_semantic_fit(None, "x", "y")
    expect(result.status == SemanticFitStatus.NOT_APPLICABLE, str(result))


# =============================================================================
# 4. Company-name invariance (item 11, item 19.10).
# =============================================================================

def test_semantic_fit_decision_is_company_name_invariant() -> None:
    """The SAME evidence shape must receive the identical semantic
    decision regardless of company name -- item 11's own explicit
    prohibition on inspecting company identity."""
    excerpt = "He added that about 90% of the business comes from \"multiplayer usage,\" or teams of workers."
    for company in ("Notion", "Stripe", "Fish Audio", "Acme Fictional Startup Inc."):
        fact = {"kind": "retention_signal", "named_entity": company, "value": "STRONG"}
        result = check_semantic_fit(fact, f"About 90% of {company}'s business comes from multiplayer usage.", excerpt)
        expect(result.status == SemanticFitStatus.UNSUPPORTED, f"decision must be identical for {company}: {result}")


def test_semantic_fit_function_never_reads_a_score_or_coverage_argument() -> None:
    """item 11: structural proof that the function signature itself
    cannot inspect Strength/Coverage -- it takes exactly (fact,
    claim_text, excerpt), nothing else."""
    import inspect
    sig = inspect.signature(check_semantic_fit)
    param_names = set(sig.parameters.keys())
    expect(
        param_names == {"fact", "claim_text", "excerpt"},
        f"check_semantic_fit must only ever see fact/claim_text/excerpt, got {param_names}",
    )


# =============================================================================
# 5. Routing integration (items 10, 19.6, 19.7, 19.11, 19.12).
# =============================================================================

def test_semantically_unsupported_retention_is_unrouted_with_its_own_typed_status() -> None:
    fact = {"kind": "retention_signal", "value": "STRONG"}
    candidate = _candidate(
        ["retention_renewal_signal"], fact,
        "About 90% of the business comes from multiplayer usage.",
        "about 90% of the business comes from \"multiplayer usage,\" or teams of workers",
    )
    result = route_candidate(candidate)
    expect(
        result.status == RoutingStatus.UNROUTED_SEMANTICALLY_UNSUPPORTED,
        f"must be its own distinct status, not folded into insufficient-structure: {result.status}",
    )
    expect(result.final_criteria == (), "semantic rejection must leave final_criteria empty")
    expect(result.semantic_fit_status == SemanticFitStatus.UNSUPPORTED.value, result.semantic_fit_status)


def test_semantically_unsupported_competitive_structure_is_unrouted() -> None:
    fact = {"kind": "competitive_structure", "value": "fragmented"}
    candidate = _candidate(
        ["competitive_landscape_position"], fact,
        "Notion competitors include Microsoft, Atlassian, and Airtable.",
        "View the competitive landscape for Notion, featuring companies like Microsoft, Atlassian, and Airtable.",
    )
    result = route_candidate(candidate)
    expect(result.status == RoutingStatus.UNROUTED_SEMANTICALLY_UNSUPPORTED, str(result.status))
    expect(result.final_criteria == (), "semantic rejection cannot broaden or preserve routing -- item 19.12")


def test_semantically_supported_retention_still_routes_normally() -> None:
    """A legitimate retention claim must not be blocked -- item 14's
    'validator must reject unsupported proxies without blocking
    legitimate evidence'."""
    fact = {"kind": "retention_signal", "value": "STRONG"}
    candidate = _candidate(
        ["retention_renewal_signal"], fact,
        "The company reports 95% net revenue retention.",
        "Net revenue retention stood at 95% for the fiscal year.",
    )
    result = route_candidate(candidate)
    expect(result.status == RoutingStatus.ROUTED, str(result.status))
    expect(result.final_criteria == ("retention_renewal_signal",), result.final_criteria)
    expect(result.semantic_fit_status == SemanticFitStatus.SUPPORTED.value, result.semantic_fit_status)


def test_semantically_unsupported_claim_still_reaches_the_ledger_grounded_and_unmodified() -> None:
    """item 10: preserve the grounded proposition and provenance -- a
    semantic mismatch narrows ROUTING, it never rejects the candidate
    outright or mutates its own claim_text/excerpt/structured_fact."""
    fact = {"kind": "retention_signal", "value": "STRONG"}
    original_excerpt = "about 90% of the business comes from \"multiplayer usage,\" or teams of workers"
    candidate = _candidate(["retention_renewal_signal"], fact, "About 90% multiplayer usage.", original_excerpt)
    finalized = _sanitize_assessment_criteria(candidate)
    expect(finalized.excerpt == original_excerpt, "the grounded excerpt must never be altered by semantic-fit rejection")
    expect(finalized.structured_fact == fact, "the structured_fact itself (including its value) must be preserved, not stripped")
    expect(finalized.assessment_criteria == [], "only assessment_criteria narrows -- the claim itself is preserved")


def test_semantic_rejection_cannot_increase_coverage_or_strength() -> None:
    """item 19.11, proven structurally: since assessment_criteria ends up
    empty, `resolve_dimension_evidence()` (unchanged, existing mechanism)
    can never see this claim for retention_renewal_signal -- the same
    "invisible to that dimension" guarantee every other UNROUTED status
    already relies on, not a new mechanism."""
    fact = {"kind": "retention_signal", "value": "STRONG"}
    candidate = _candidate(["retention_renewal_signal"], fact, "About 90% multiplayer usage.", "about 90% of the business comes from multiplayer usage")
    finalized = _sanitize_assessment_criteria(candidate)
    expect("retention_renewal_signal" not in finalized.assessment_criteria, "the dimension must be unreachable, structurally")


def test_check_methodology_readiness_requires_both_structural_and_semantic_support() -> None:
    """item 15: `methodology-usable` = classifier-compatible AND
    semantically-supported (when a rule applies)."""
    structurally_ready_semantically_wrong = {"kind": "retention_signal", "value": "STRONG"}
    expect(check_classifier_readiness(structurally_ready_semantically_wrong), "precondition: structurally this fact is classifier-ready")
    expect(
        not check_methodology_readiness(structurally_ready_semantically_wrong, "About 90% multiplayer usage.", "90% multiplayer usage"),
        "methodology-readiness must additionally require semantic support",
    )

    structurally_ready_semantically_right = {"kind": "retention_signal", "value": "STRONG"}
    expect(
        check_methodology_readiness(structurally_ready_semantically_right, "95% net revenue retention.", "net revenue retention of 95%"),
        "a semantically-supported, structurally-ready fact must be methodology-usable",
    )

    structurally_incomplete = {"kind": "retention_signal"}  # missing required value
    expect(
        not check_methodology_readiness(structurally_incomplete, "95% net revenue retention.", "net revenue retention of 95%"),
        "structural incompleteness alone must still block methodology-readiness",
    )

    kind_with_no_semantic_rule = {"kind": "customer_band", "value": "LARGE"}
    expect(
        check_methodology_readiness(kind_with_no_semantic_rule, "irrelevant", "irrelevant"),
        "a kind with no semantic-fit rule must be gated by structural readiness alone",
    )


TESTS = [
    test_retention_false_positive_adoption_usage_is_rejected,
    test_retention_rejects_bare_customer_count,
    test_retention_rejects_logos_testimonials_longevity_growth_popularity,
    test_retention_positive_control_explicit_retention_figure,
    test_retention_positive_control_explicit_churn_figure,
    test_retention_positive_control_explicit_renewal_language,
    test_competitive_structure_false_positive_bare_competitor_list_is_rejected,
    test_competitive_structure_rejects_a_bare_concentrated_claim_with_no_vocabulary_either,
    test_competitive_structure_fragmented_vocabulary_does_not_support_concentrated_value,
    test_competitive_structure_positive_control_explicit_fragmentation_report,
    test_competitive_structure_positive_control_explicit_concentration_report,
    test_kind_with_no_rule_is_not_applicable_never_supported_or_unsupported,
    test_none_fact_is_not_applicable,
    test_semantic_fit_decision_is_company_name_invariant,
    test_semantic_fit_function_never_reads_a_score_or_coverage_argument,
    test_semantically_unsupported_retention_is_unrouted_with_its_own_typed_status,
    test_semantically_unsupported_competitive_structure_is_unrouted,
    test_semantically_supported_retention_still_routes_normally,
    test_semantically_unsupported_claim_still_reaches_the_ledger_grounded_and_unmodified,
    test_semantic_rejection_cannot_increase_coverage_or_strength,
    test_check_methodology_readiness_requires_both_structural_and_semantic_support,
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
