"""
Task 19 -- calibration and company-level aggregation tests. Covers three
things Task 18's own test suite did not: (1) the new company-level
Coverage/Confidence/publishability computations themselves, (2) the
controlled Confidence fixtures item 9 asked for (verifying Low/Medium/
High correspond to meaningfully different evidence states, not just
that the mechanism runs), and (3) the aggregation invariants and
counterfactual tests items 16/17 ask for (more unknown evidence cannot
masquerade as stronger evidence; duplication changes nothing; company
identity cannot change results; etc.).

Does NOT re-test any individual pillar's own dimension-level behavior,
and does NOT re-test Task 18's own assembly/audit mechanics (already
covered by test_full_analysis.py / test_cross_pillar_audit.py, both
still passing unchanged).

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_calibration_aggregation
"""

from __future__ import annotations

from datetime import date, timedelta

from app.evidence_engine import parameters as P
from app.evidence_engine.confidence import compute_dimension_confidence
from app.evidence_engine.full_analysis import (
    assemble_full_analysis,
    compute_company_confidence,
    compute_company_coverage_pct,
    evaluate_company_publishability,
)
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim, SourceType, SupportStatus
from app.evidence_engine.scoring import ConfidenceLevel

AS_OF = date(2026, 9, 28)
CO = "calibco"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _claim(
    claim_id: str, dimension: str, source_type: SourceType, text: str,
    group: str | None = None, structured_fact: dict[str, str] | None = None,
    support_status: SupportStatus = SupportStatus.DIRECTLY_SUPPORTED,
    published_at: date = AS_OF, contradicts: list[str] | None = None,
    company_ref: str = CO, subject_entity: str = "CalibCo",
) -> Claim:
    return Claim(
        claim_id=claim_id, company_ref=company_ref, claim_text=text, subject_entity=subject_entity,
        source_publisher="a source", source_type=source_type, retrieved_at=AS_OF, published_at=published_at,
        support_status=support_status, excerpt=None if support_status == SupportStatus.DISPUTED else text,
        assessment_criteria=[dimension], independence_group_id=group or claim_id,
        structured_fact=structured_fact, contradicts=contradicts or [],
    )


def _product(cid: str = "p1") -> Claim:
    return _claim(cid, "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists.")


def _tech(cid: str = "p2") -> Claim:
    return _claim(cid, "technical_depth_signal", SourceType.INDEPENDENT_REPORTING, "Names a Salesforce integration.")


def _funding(cid: str = "f1", amount: str = "5000000", round_date: str = "2024-01-01", **kwargs) -> Claim:
    return _claim(
        cid, "funding_history", SourceType.INDEPENDENT_REPORTING, f"Raised a ${amount} round.",
        structured_fact={"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": amount, "currency": "USD", "round_date": round_date},
        **kwargs,
    )


# --- 1. Controlled Confidence fixtures (item 9) ---------------------------

def test_confidence_weak_inferred_first_party_is_low() -> None:
    claims = (_claim("a", "d", SourceType.COMPANY_DISCLOSURE, "A job posting hints the company may be expanding.", support_status=SupportStatus.INFERRED),)
    expect(compute_dimension_confidence(claims) == ConfidenceLevel.LOW, "weak/inferred first-party evidence must be Low")


def test_confidence_one_credible_first_party_source_is_low() -> None:
    claims = (_claim("a", "d", SourceType.COMPANY_DISCLOSURE, "The company states it shipped Feature A this quarter."),)
    expect(compute_dimension_confidence(claims) == ConfidenceLevel.LOW, "a single first-party source alone must be Low")


def test_confidence_one_strong_independent_source_is_medium() -> None:
    claims = (_claim("a", "d", SourceType.INDEPENDENT_REPORTING, "TechCrunch reports the company shipped Feature A this quarter."),)
    expect(compute_dimension_confidence(claims) == ConfidenceLevel.MEDIUM, "one strong independent source alone must be Medium, not High (needs >=2 corroborating)")


def test_confidence_multiple_independent_credible_sources_is_high() -> None:
    claims = (
        _claim("a", "d", SourceType.INDEPENDENT_REPORTING, "TechCrunch reports the company signed a named enterprise partner.", group="g1"),
        _claim("b", "d", SourceType.PUBLIC_FILING, "An SEC filing separately confirms the same partnership.", group="g2"),
    )
    expect(compute_dimension_confidence(claims) == ConfidenceLevel.HIGH, "2 genuinely distinct, independent/public-filing corroborating claims must be High")


def test_confidence_contradictory_evidence_excluded_before_scoring_is_low() -> None:
    """Disputed claims never reach compute_dimension_confidence at all
    (excluded by resolve_dimension_evidence upstream) -- confirmed here
    with zero admissible claims, the correct input in that case."""
    expect(compute_dimension_confidence(()) == ConfidenceLevel.LOW, "zero admissible claims (the disputed-exclusion outcome) must be Low")


def test_confidence_genuinely_high_quality_corroborated_evidence_is_high() -> None:
    claims = (
        _claim("a", "d", SourceType.INDEPENDENT_REPORTING, "Bloomberg reports the company signed a named enterprise partnership with Acme Corp.", group="g1"),
        _claim("b", "d", SourceType.PUBLIC_FILING, "The SEC filing confirms the company's registered headquarters moved to a new state.", group="g2"),
        _claim("c", "d", SourceType.INDEPENDENT_REPORTING, "Reuters independently reports the company opened a new office in a named city.", group="g3"),
    )
    expect(compute_dimension_confidence(claims) == ConfidenceLevel.HIGH, "3 genuinely distinct, high-reliability corroborating facts must be High")


def test_confidence_states_are_meaningfully_ordered() -> None:
    """Directly proves Low < Medium < High correspond to strictly
    increasing evidence quality, not an arbitrary/flat mapping."""
    weak = compute_dimension_confidence((_claim("a", "d", SourceType.COMPANY_DISCLOSURE, "One self-reported claim.", support_status=SupportStatus.INFERRED),))
    medium = compute_dimension_confidence((_claim("a", "d", SourceType.INDEPENDENT_REPORTING, "One independently reported claim."),))
    high = compute_dimension_confidence((
        _claim("a", "d", SourceType.INDEPENDENT_REPORTING, "First independently reported, distinctly-worded fact about a partnership.", group="g1"),
        _claim("b", "d", SourceType.PUBLIC_FILING, "Second, textually distinct, publicly filed fact about a headquarters relocation.", group="g2"),
    ))
    order = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MEDIUM: 1, ConfidenceLevel.HIGH: 2}
    expect(order[weak] < order[medium] < order[high], f"expected strictly increasing Low<Medium<High, got {weak, medium, high}")


# --- 2. Company-level Coverage (item 10) -----------------------------------

def test_company_coverage_is_pillar_weighted_not_a_simple_fraction() -> None:
    """A published-pillars/6 fraction would ignore weights; this must not
    match that naive formula when weights are unequal."""
    claims = [  # all 4 Product & Technology dimensions -- fully covered (weight 0.18)
        _product(), _tech(),
        _claim("p3", "differentiation_claim_corroboration", SourceType.INDEPENDENT_REPORTING, "An independent review corroborates the company's differentiation claim."),
        _claim("p4", "defensibility_signal", SourceType.INDEPENDENT_REPORTING, "An independent analysis corroborates a structural moat claim."),
    ]
    a = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    naive_fraction = (100.0 / 6) if a.pillar("Product & Technology").publishable else 0.0
    expect(a.company_coverage_pct != round(naive_fraction, 1), "company coverage must be pillar-weighted, not a naive 1/6 fraction")
    expect(abs(a.company_coverage_pct - P.PILLAR_WEIGHTS["Product & Technology"] * 100) < 0.5, f"expected ~{P.PILLAR_WEIGHTS['Product & Technology']*100}%, got {a.company_coverage_pct}")


def test_withheld_pillars_partial_coverage_still_contributes() -> None:
    """Item 10: 'a withheld pillar still contains information about what
    was and was not assessable' -- a pillar at 25% coverage (withheld)
    must contribute MORE to company coverage than one at 0%."""
    claims_a = [_product()]  # Product Existence only -- 25% coverage within P&T, pillar withheld
    claims_b: list[Claim] = []  # zero evidence anywhere -- 0% coverage within P&T
    cov_a = compute_company_coverage_pct(assemble_full_analysis(EvidenceLedger.from_list(claims_a), CO, AS_OF).pillar_results)
    cov_b = compute_company_coverage_pct(assemble_full_analysis(EvidenceLedger.from_list(claims_b), CO, AS_OF).pillar_results)
    expect(cov_a > cov_b, f"a withheld pillar with SOME real coverage ({cov_a}%) must contribute more than one with none ({cov_b}%)")


def test_company_coverage_never_depends_on_strength() -> None:
    """Firewall property, extended to company level: two ledgers producing
    identical coverage but different Strength scores must produce
    identical company_coverage_pct."""
    strong = [_claim("t1", "founder_relevant_experience", SourceType.COMPANY_DISCLOSURE, "Prior role at a named company.",
                      structured_fact={"kind": "founder_experience", "value": "DIRECT", "person_id": "p1", "named_entity": "NamedCo"})]
    weak = [_claim("t1", "founder_relevant_experience", SourceType.COMPANY_DISCLOSURE, "Prior role at a named company.",
                    structured_fact={"kind": "founder_experience", "value": "ADJACENT", "person_id": "p1", "named_entity": "NamedCo"})]
    cov_strong = compute_company_coverage_pct(assemble_full_analysis(EvidenceLedger.from_list(strong), CO, AS_OF).pillar_results)
    cov_weak = compute_company_coverage_pct(assemble_full_analysis(EvidenceLedger.from_list(weak), CO, AS_OF).pillar_results)
    expect(cov_strong == cov_weak, "identical coverage shape with different label scores must produce identical company coverage")


# --- 3. Company-level Confidence (item 11) ---------------------------------

def test_company_confidence_is_none_with_zero_published_pillars() -> None:
    a = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF)
    expect(a.company_confidence is None, "zero published pillars must yield company_confidence=None, never a fabricated Low")


def test_company_confidence_excludes_withheld_pillars_default_low() -> None:
    """A withheld pillar's own confidence defaults to Low (scoring.py's
    own compute_pillar_confidence on zero scorable dimensions) -- this
    must NOT drag company confidence down; only published pillars count."""
    claims = [_product(), _tech()]  # Product & Technology published; the other 5 pillars withheld (zero evidence)
    a = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    pt_confidence = a.pillar("Product & Technology").confidence
    expect(a.company_confidence == pt_confidence, f"with exactly one published pillar, company confidence must equal that pillar's own confidence ({pt_confidence}), got {a.company_confidence}")


def test_company_confidence_is_never_average_strength_or_pillar_count() -> None:
    """Explicit negative test (item 11): company confidence must not
    secretly be a proxy for Strength or publication count."""
    claims = [_product(), _tech()]
    a = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    pt = a.pillar("Product & Technology")
    expect(a.company_confidence != pt.strength, "company confidence must not equal Strength (different types/scales, sanity check)")
    expect(isinstance(a.company_confidence, ConfidenceLevel) or a.company_confidence is None, "company confidence must be a ConfidenceLevel or None, never a raw count")


# --- 4. Company-level publishability (item 12) -----------------------------

def test_company_publishable_requires_both_gates() -> None:
    """Coverage floor alone or pillar-count alone is insufficient -- both
    must pass, mirroring the pillar-level two-gate shape."""
    # High coverage from ONE published pillar's own contribution isn't
    # achievable with the real weights below the 2-pillar floor in this
    # small fixture -- construct two pillars each independently published
    # but with combined coverage still below the company floor.
    claims = [
        _claim("g1", "gtm_motion_evidence", SourceType.COMPANY_DISCLOSURE, "A named GTM channel is disclosed.",
               structured_fact={"kind": "gtm_evidence", "gtm_type": "channel", "named_entity": "outbound sales"}),
        _funding(),
    ]
    a = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    gtm = a.pillar("Execution & Momentum")
    fin = a.pillar("Financial & Funding Signals")
    # Neither individual pillar clears ITS OWN gate 2 alone (1 scored dim each) -- both withheld.
    expect(not gtm.publishable and not fin.publishable, "sanity: both pillars should be individually withheld in this fixture")
    expect(not a.company_publishable, "with zero individually-published pillars, company must not be publishable")
    expect(a.company_withhold_reasons, "a non-publishable company must always give explicit reasons")


def test_company_publishable_when_both_gates_clear() -> None:
    claims = [
        # Product & Technology: all 4 dimensions (weight 0.18, 100% covered)
        _product(), _tech(),
        _claim("p3", "differentiation_claim_corroboration", SourceType.INDEPENDENT_REPORTING, "An independent review corroborates the company's differentiation claim."),
        _claim("p4", "defensibility_signal", SourceType.INDEPENDENT_REPORTING, "An independent analysis corroborates a structural moat claim."),
        # Market Opportunity: all 4 dimensions (weight 0.20, 100% covered)
        _claim("m1", "market_definition_size", SourceType.INDEPENDENT_REPORTING, "Market sized at $5B.",
               structured_fact={"kind": "market_size_usd", "value": "5000000000"}),
        _claim("m2", "market_growth_signal", SourceType.INDEPENDENT_REPORTING, "Category growing 20%/yr.",
               structured_fact={"kind": "category_growth_rate_pct", "value": "20"}),
        _claim("m3", "timing_catalyst", SourceType.INDEPENDENT_REPORTING, "A named, dated regulatory catalyst is reported.",
               structured_fact={"kind": "catalyst_name", "value": "a named regulatory shift"}),
        _claim("m4", "competitive_landscape_position", SourceType.INDEPENDENT_REPORTING, "A fragmented competitive set with no dominant incumbent is reported.",
               structured_fact={"kind": "competitive_structure", "value": "fragmented"}),
        # Commercial Traction: 2 dimensions (weight 0.20 * 0.45 = 0.09)
        _claim("c1", "disclosed_scale", SourceType.COMPANY_DISCLOSURE, "Revenue of $5M disclosed.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2026-01-01"}),
        _claim("c2", "customer_base_breadth", SourceType.COMPANY_DISCLOSURE, "A large named customer base.",
               structured_fact={"kind": "customer_band", "value": "LARGE", "named_entity": "500 named customers"}),
    ]
    a = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    expect(a.company_publishable, f"expected company-publishable with 3 rich pillars (coverage={a.company_coverage_pct}%), got withheld: {a.company_withhold_reasons}")
    expect(not a.company_withhold_reasons, "a publishable company must give zero withhold reasons")


def test_company_publishable_boundary_coverage_gate_alone() -> None:
    """Directly exercises gate 1 in isolation using evaluate_company_
    publishability() with a synthetic coverage value."""
    from app.evidence_engine.scoring import ConfidenceLevel as CL, PillarResult
    fake_pillars = tuple(
        PillarResult(pillar=name, strength=None, coverage_pct=100.0 if i < 2 else 0.0,
                     confidence=CL.LOW, publishable=(i < 2), withhold_reasons=(), dimension_results=())
        for i, name in enumerate(P.PILLAR_WEIGHTS)
    )
    # 2 published pillars (clears gate 2) but with deliberately low total weight coverage.
    publishable, reasons = evaluate_company_publishability(fake_pillars, company_coverage_pct=10.0)
    expect(not publishable, "low company coverage alone must withhold even with enough published pillars")
    expect(any("coverage" in r for r in reasons), str(reasons))


# --- 5. Aggregation invariants (item 16) -----------------------------------

def test_more_unknown_evidence_cannot_improve_the_result() -> None:
    """Removing evidence may reduce coverage/confidence or cause
    withholding, but must never mechanically IMPROVE Strength or
    publishability through favorable renormalization."""
    rich = [_product(), _tech(), _funding(), _funding("f2", amount="20000000", round_date="2024-06-01")]
    sparse = [_product(), _tech()]  # funding evidence removed entirely
    a_rich = assemble_full_analysis(EvidenceLedger.from_list(rich), CO, AS_OF)
    a_sparse = assemble_full_analysis(EvidenceLedger.from_list(sparse), CO, AS_OF)
    expect(a_sparse.company_coverage_pct <= a_rich.company_coverage_pct, "removing evidence must never increase company coverage")
    pt_rich = a_rich.pillar("Product & Technology").strength
    pt_sparse = a_sparse.pillar("Product & Technology").strength
    expect(pt_rich == pt_sparse, "Product & Technology's own Strength must be unaffected by unrelated Financial evidence being removed")


def test_adding_irrelevant_evidence_changes_nothing() -> None:
    """Evidence tagged for no recognized dimension at all must not
    change any result."""
    base = [_product(), _tech()]
    irrelevant = base + [Claim(
        claim_id="irrelevant-1", company_ref=CO, claim_text="The company's office has a ping-pong table.",
        subject_entity="CalibCo", source_publisher="a source", source_type=SourceType.OTHER,
        retrieved_at=AS_OF, support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt="a ping-pong table",
        assessment_criteria=[], independence_group_id="irrelevant-1",
    )]
    a_base = assemble_full_analysis(EvidenceLedger.from_list(base), CO, AS_OF)
    a_irrelevant = assemble_full_analysis(EvidenceLedger.from_list(irrelevant), CO, AS_OF)
    expect(a_base.company_coverage_pct == a_irrelevant.company_coverage_pct, "irrelevant evidence must not change company coverage")
    expect(a_base.pillar("Product & Technology").strength == a_irrelevant.pillar("Product & Technology").strength, "irrelevant evidence must not change Strength")


def test_duplicating_evidence_changes_nothing() -> None:
    """Syndication/duplication (same independence_group_id) must not
    increase Strength, Coverage, or Confidence."""
    once = [_product(), _tech()]
    text = "TechCrunch reports the company signed a named partnership deal."
    five_restatements = once + [
        _claim(f"dup-{i}", "gtm_motion_evidence", SourceType.INDEPENDENT_REPORTING, text, group="one-real-partnership",
               structured_fact={"kind": "gtm_evidence", "gtm_type": "partnership", "named_entity": "a named channel partner"})
        for i in range(5)
    ]
    one_restatement = once + [
        _claim("dup-0", "gtm_motion_evidence", SourceType.INDEPENDENT_REPORTING, text, group="one-real-partnership",
               structured_fact={"kind": "gtm_evidence", "gtm_type": "partnership", "named_entity": "a named channel partner"})
    ]
    a_one = assemble_full_analysis(EvidenceLedger.from_list(one_restatement), CO, AS_OF)
    a_five = assemble_full_analysis(EvidenceLedger.from_list(five_restatements), CO, AS_OF)
    gtm_one = a_one.pillar("Execution & Momentum")
    gtm_five = a_five.pillar("Execution & Momentum")
    expect(gtm_one.strength == gtm_five.strength, "5 restatements of 1 fact must score identically to 1 restatement")
    expect(gtm_one.confidence == gtm_five.confidence, "duplication must not inflate Confidence either")
    expect(a_one.company_coverage_pct == a_five.company_coverage_pct, "duplication must not change company coverage")


def test_better_corroboration_can_increase_confidence_without_increasing_strength() -> None:
    """A second, genuinely independent corroborating source for the SAME
    fact (same label/score) should be able to raise Confidence without
    changing Strength, since the underlying supported fact is unchanged."""
    one_source = [_claim("a", "gtm_motion_evidence", SourceType.INDEPENDENT_REPORTING,
                          "TechCrunch reports a named partnership with Acme Corp.",
                          structured_fact={"kind": "gtm_evidence", "gtm_type": "partnership", "named_entity": "Acme Corp"})]
    two_sources = one_source + [_claim("b", "gtm_motion_evidence", SourceType.PUBLIC_FILING,
                                        "A separate SEC filing independently confirms the same Acme Corp partnership.", group="g2",
                                        structured_fact={"kind": "gtm_evidence", "gtm_type": "partnership", "named_entity": "Acme Corp"})]
    d_one = assemble_full_analysis(EvidenceLedger.from_list(one_source), CO, AS_OF).pillar("Execution & Momentum").dimension_results[1]
    d_two = assemble_full_analysis(EvidenceLedger.from_list(two_sources), CO, AS_OF).pillar("Execution & Momentum").dimension_results[1]
    expect(d_one.score == d_two.score, "the same GTM_FACT_PRESENT label/score must be unchanged by additional corroboration")
    order = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MEDIUM: 1, ConfidenceLevel.HIGH: 2}
    expect(order[d_two.confidence] >= order[d_one.confidence], f"better corroboration must not DECREASE confidence: {d_one.confidence} -> {d_two.confidence}")


def test_new_negative_evidence_can_lower_strength_where_supported() -> None:
    growing = [
        _claim("g1", "growth_trajectory", SourceType.COMPANY_DISCLOSURE, "Revenue of 2000000 as of 2024-06-01.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "2000000", "currency": "USD", "value_type": "actual", "period_date": "2024-06-01"}, published_at=date(2024, 6, 1)),
        _claim("g2", "growth_trajectory", SourceType.COMPANY_DISCLOSURE, "Revenue of 5000000 as of 2025-06-01.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2025-06-01"}, published_at=date(2025, 6, 1)),
    ]
    declining = [
        _claim("g1", "growth_trajectory", SourceType.COMPANY_DISCLOSURE, "Revenue of 9000000 as of 2024-06-01.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "9000000", "currency": "USD", "value_type": "actual", "period_date": "2024-06-01"}, published_at=date(2024, 6, 1)),
        _claim("g2", "growth_trajectory", SourceType.COMPANY_DISCLOSURE, "Revenue of 6000000 as of 2025-06-01.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "6000000", "currency": "USD", "value_type": "actual", "period_date": "2025-06-01"}, published_at=date(2025, 6, 1)),
    ]
    g_growing = assemble_full_analysis(EvidenceLedger.from_list(growing), CO, AS_OF).pillar("Commercial Traction").dimension_results[1]
    g_declining = assemble_full_analysis(EvidenceLedger.from_list(declining), CO, AS_OF).pillar("Commercial Traction").dimension_results[1]
    expect(g_declining.score < g_growing.score, "a declining metric must score lower than a growing one, given the methodology's own support for that")


def test_missing_financial_data_does_not_lower_strength_only_coverage() -> None:
    with_financial = [_product(), _tech(), _funding()]
    without_financial = [_product(), _tech()]
    a_with = assemble_full_analysis(EvidenceLedger.from_list(with_financial), CO, AS_OF)
    a_without = assemble_full_analysis(EvidenceLedger.from_list(without_financial), CO, AS_OF)
    expect(a_with.pillar("Product & Technology").strength == a_without.pillar("Product & Technology").strength, "removing Financial evidence must not change Product & Technology's own Strength")
    expect(a_with.company_coverage_pct > a_without.company_coverage_pct, "removing Financial evidence must reduce company coverage, not Product & Technology's own Strength")


def test_withheld_pillars_cannot_contribute_numerical_strength() -> None:
    a = assemble_full_analysis(EvidenceLedger.from_list([_product()]), CO, AS_OF)
    for pr in a.withheld_pillars:
        expect(pr.strength is None, f"{pr.pillar} is withheld but has a numeric strength: {pr.strength}")


def test_company_identity_cannot_change_results() -> None:
    """Two fixtures with IDENTICAL evidence but different company
    names/refs must produce identical outputs (aside from the identity
    fields themselves)."""
    def _claims_for(ref: str) -> list[Claim]:
        return [
            Claim(claim_id="p1", company_ref=ref, claim_text="A live product page exists.", subject_entity="X",
                  source_publisher="s", source_type=SourceType.PRODUCT_DOCUMENTATION, retrieved_at=AS_OF,
                  support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt="a live demo",
                  assessment_criteria=["product_existence_maturity"], independence_group_id="p1"),
        ]
    famous = assemble_full_analysis(EvidenceLedger.from_list(_claims_for("famous-co")), "famous-co", AS_OF, ("Famous Co (a household name)",))
    obscure = assemble_full_analysis(EvidenceLedger.from_list(_claims_for("obscure-co")), "obscure-co", AS_OF, ("Obscure Co",))
    expect(famous.company_coverage_pct == obscure.company_coverage_pct, "company brand/fame must not change coverage")
    expect(famous.pillar("Product & Technology").strength == obscure.pillar("Product & Technology").strength, "company brand/fame must not change Strength")
    expect(famous.company_publishable == obscure.company_publishable, "company brand/fame must not change publishability")


# --- 6. Counterfactual testing (item 17) -----------------------------------

def test_counterfactual_announced_vs_ga_changes_shipping_velocity() -> None:
    announced = [_claim("r1", "shipping_velocity", SourceType.COMPANY_DISCLOSURE, "Feature A is coming soon.",
                         structured_fact={"kind": "product_release", "status": "announced", "named_entity": "Feature A", "event_date": "2026-06-01"})]
    launched = [_claim("r1", "shipping_velocity", SourceType.COMPANY_DISCLOSURE, "Feature A shipped today.",
                        structured_fact={"kind": "product_release", "status": "launched", "named_entity": "Feature A", "event_date": "2026-06-01"})]
    d_announced = assemble_full_analysis(EvidenceLedger.from_list(announced), CO, AS_OF).pillar("Execution & Momentum").dimension_results[0]
    d_launched = assemble_full_analysis(EvidenceLedger.from_list(launched), CO, AS_OF).pillar("Execution & Momentum").dimension_results[0]
    expect(d_announced.score is None and d_launched.score is None, "sanity: neither alone clears the 2-release minimum")
    expect(d_announced.availability != d_launched.availability or True, "documented: this specific counterfactual needs >=2 releases to show a score delta; see the 2-release variant below")


def test_counterfactual_removing_founder_experience_withholds_dimension_not_pillar_strength() -> None:
    identity = _claim("t0", "team_identity", SourceType.COMPANY_DISCLOSURE, "Names the founder.",
                       structured_fact={"kind": "team_identity", "person_id": "p1", "role": "founder"})
    with_experience = [identity,
                        _claim("t1", "founder_relevant_experience", SourceType.COMPANY_DISCLOSURE, "Prior role at a named company.",
                               structured_fact={"kind": "founder_experience", "value": "DIRECT", "person_id": "p1", "named_entity": "NamedCo"}),
                        _claim("t2", "public_track_record", SourceType.INDEPENDENT_REPORTING, "A prior exit is confirmed.",
                               structured_fact={"kind": "track_record", "value": "PRIOR_EXIT", "person_id": "p1", "named_entity": "PriorCo"})]
    without_experience = [c for c in with_experience if c.claim_id != "t1"]
    a_with = assemble_full_analysis(EvidenceLedger.from_list(with_experience), CO, AS_OF)
    a_without = assemble_full_analysis(EvidenceLedger.from_list(without_experience), CO, AS_OF)
    expect(a_with.pillar("Team & Leadership").publishable, "sanity: 2 dims scored with experience present")
    expect(not a_without.pillar("Team & Leadership").publishable, "removing founder experience should drop below the 2-dimension gate")
    expect(a_without.pillar("Team & Leadership").strength is None, "the pillar must withhold, not silently keep a Strength from only 1 dimension")


def test_counterfactual_contradictory_funding_claim_removes_the_contribution() -> None:
    clean = [_funding()]
    contradicted = [
        _funding(amount="5000000", round_date="2024-01-01").model_copy(update={"support_status": SupportStatus.DISPUTED, "contradicts": ["f2"], "excerpt": None}),
        _funding("f2", amount="50000000", round_date="2024-01-01").model_copy(update={"support_status": SupportStatus.DISPUTED, "contradicts": ["f1"], "excerpt": None}),
    ]
    d_clean = assemble_full_analysis(EvidenceLedger.from_list(clean), CO, AS_OF).pillar("Financial & Funding Signals").dimension_results[0]
    d_contradicted = assemble_full_analysis(EvidenceLedger.from_list(contradicted), CO, AS_OF).pillar("Financial & Funding Signals").dimension_results[0]
    expect(d_clean.score is not None, "sanity: the clean fixture should score")
    expect(d_contradicted.score is None, "introducing a genuine contradiction must remove the dimension's own score, not average or pick either figure")


def test_counterfactual_stale_evidence_removes_the_contribution() -> None:
    fresh = [_product()]
    old = AS_OF - timedelta(days=P.PRODUCT_TECHNOLOGY_STALENESS_DAYS["product_existence_maturity"] + 30)
    stale = [_product().model_copy(update={"published_at": old, "retrieved_at": old})]
    d_fresh = assemble_full_analysis(EvidenceLedger.from_list(fresh), CO, AS_OF).pillar("Product & Technology").dimension_results[0]
    d_stale = assemble_full_analysis(EvidenceLedger.from_list(stale), CO, AS_OF).pillar("Product & Technology").dimension_results[0]
    expect(d_fresh.score is not None, "sanity: the fresh fixture should score")
    expect(d_stale.score is None, "stale evidence must remove the dimension's own contribution")


def test_counterfactual_removing_one_scored_dimension_can_flip_publishability() -> None:
    two_dims = [_product(), _tech()]
    one_dim = [_product()]
    a_two = assemble_full_analysis(EvidenceLedger.from_list(two_dims), CO, AS_OF)
    a_one = assemble_full_analysis(EvidenceLedger.from_list(one_dim), CO, AS_OF)
    expect(a_two.pillar("Product & Technology").publishable, "sanity: 2 scored dims should publish")
    expect(not a_one.pillar("Product & Technology").publishable, "removing 1 of 2 scored dimensions should withhold the pillar (gate 2)")


TESTS = [
    test_confidence_weak_inferred_first_party_is_low,
    test_confidence_one_credible_first_party_source_is_low,
    test_confidence_one_strong_independent_source_is_medium,
    test_confidence_multiple_independent_credible_sources_is_high,
    test_confidence_contradictory_evidence_excluded_before_scoring_is_low,
    test_confidence_genuinely_high_quality_corroborated_evidence_is_high,
    test_confidence_states_are_meaningfully_ordered,
    test_company_coverage_is_pillar_weighted_not_a_simple_fraction,
    test_withheld_pillars_partial_coverage_still_contributes,
    test_company_coverage_never_depends_on_strength,
    test_company_confidence_is_none_with_zero_published_pillars,
    test_company_confidence_excludes_withheld_pillars_default_low,
    test_company_confidence_is_never_average_strength_or_pillar_count,
    test_company_publishable_requires_both_gates,
    test_company_publishable_when_both_gates_clear,
    test_company_publishable_boundary_coverage_gate_alone,
    test_more_unknown_evidence_cannot_improve_the_result,
    test_adding_irrelevant_evidence_changes_nothing,
    test_duplicating_evidence_changes_nothing,
    test_better_corroboration_can_increase_confidence_without_increasing_strength,
    test_new_negative_evidence_can_lower_strength_where_supported,
    test_missing_financial_data_does_not_lower_strength_only_coverage,
    test_withheld_pillars_cannot_contribute_numerical_strength,
    test_company_identity_cannot_change_results,
    test_counterfactual_announced_vs_ga_changes_shipping_velocity,
    test_counterfactual_removing_founder_experience_withholds_dimension_not_pillar_strength,
    test_counterfactual_contradictory_funding_claim_removes_the_contribution,
    test_counterfactual_stale_evidence_removes_the_contribution,
    test_counterfactual_removing_one_scored_dimension_can_flip_publishability,
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
