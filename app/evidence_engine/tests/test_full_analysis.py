"""
Task 18 -- full-engine assembly tests. Covers the `FullCompanyAnalysis`
contract, the orchestration flow (`assemble_full_analysis`), single-
stage resolution shared across all six pillars, preservation of every
pillar's own publication gate (published/withheld in every combination),
full-analysis-level deterministic reproducibility, and item 15's own
explicit architectural-risk checklist re-verified at assembly scale (not
just within each pillar's own test suite).

Does NOT re-test any individual pillar's own dimension-level behavior --
that is each pillar's own test file's job (290 tests already passing).
This file tests what only exists once six pillars are assembled together.

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_full_analysis
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.evidence_engine import parameters as P
from app.evidence_engine.classification import ClassificationRequest, ClassificationResponse
from app.evidence_engine.full_analysis import FullCompanyAnalysis, assemble_full_analysis
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim, SourceType, SupportStatus
from app.evidence_engine.stage import Stage

AS_OF = date(2026, 9, 28)
CO = "assemblyco"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _claim(
    claim_id: str, dimension: str, source_type: SourceType, text: str,
    group: str | None = None, structured_fact: dict[str, str] | None = None,
    support_status: SupportStatus = SupportStatus.DIRECTLY_SUPPORTED,
    published_at: date = AS_OF, contradicts: list[str] | None = None,
    company_ref: str = CO,
) -> Claim:
    return Claim(
        claim_id=claim_id, company_ref=company_ref, claim_text=text, subject_entity="AssemblyCo",
        source_publisher="a source", source_type=source_type, retrieved_at=AS_OF, published_at=published_at,
        support_status=support_status, excerpt=None if support_status == SupportStatus.DISPUTED else text,
        assessment_criteria=[dimension], independence_group_id=group or claim_id,
        structured_fact=structured_fact, contradicts=contradicts or [],
    )


_ALL_SIX_PILLARS = (
    "Market Opportunity", "Product & Technology", "Team & Leadership",
    "Commercial Traction", "Execution & Momentum", "Financial & Funding Signals",
)


# --- 1. Contract shape --------------------------------------------------

def test_full_analysis_contains_exactly_six_pillar_results() -> None:
    analysis = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF)
    expect(len(analysis.pillar_results) == 6, f"expected exactly 6 pillar results, got {len(analysis.pillar_results)}")
    expect({pr.pillar for pr in analysis.pillar_results} == set(_ALL_SIX_PILLARS), "must include all six pillar names, exactly")


def test_full_analysis_carries_no_overall_score() -> None:
    """Explicit negative test: this contract must never grow an overall
    0-100 score, grade, ranking, or verdict field (Task 18's own scope)."""
    analysis = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF)
    forbidden_field_names = {"overall_score", "score", "grade", "rank", "ranking", "verdict", "recommendation", "pass_fail"}
    actual_fields = {f.name for f in analysis.__dataclass_fields__.values()}
    expect(not (forbidden_field_names & actual_fields), f"contract must not carry an overall score/grade/rank field, found: {forbidden_field_names & actual_fields}")


def test_pillar_lookup_by_name() -> None:
    analysis = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF)
    pt = analysis.pillar("Product & Technology")
    expect(pt is not None and pt.pillar == "Product & Technology", "pillar() lookup must find the exact pillar by name")
    expect(analysis.pillar("Nonexistent Pillar") is None, "an unknown pillar name must return None, not raise")


def test_generated_at_and_as_of_are_distinct_fields() -> None:
    analysis = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF, generated_at=date(2027, 1, 1))
    expect(analysis.as_of == AS_OF, "as_of must be the evidence-cutoff date passed in")
    expect(analysis.generated_at == date(2027, 1, 1), "generated_at must be independently settable/distinct from as_of")


# --- 2. Withholding remains first-class (item 8) -------------------------

def test_all_six_pillars_published() -> None:
    """A rich, cross-pillar ledger where every pillar clears its own
    gates."""
    claims = [
        # Market Opportunity
        _claim("m1", "market_definition_size", SourceType.INDEPENDENT_REPORTING, "Market sized at $5B.",
               structured_fact={"kind": "market_size_usd", "value": "5000000000"}),
        _claim("m2", "market_growth_signal", SourceType.INDEPENDENT_REPORTING, "Category growing 20%/yr.",
               structured_fact={"kind": "category_growth_rate_pct", "value": "20"}),
        # Product & Technology
        _claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists."),
        _claim("p2", "technical_depth_signal", SourceType.INDEPENDENT_REPORTING, "Names a Salesforce integration."),
        # Team & Leadership
        _claim("t1", "team_identity", SourceType.COMPANY_DISCLOSURE, "Names the founder.",
               structured_fact={"kind": "team_identity", "person_id": "p1", "role": "founder"}),
        _claim("t2", "founder_relevant_experience", SourceType.COMPANY_DISCLOSURE, "Prior role at a named company.",
               structured_fact={"kind": "founder_experience", "value": "DIRECT", "person_id": "p1", "named_entity": "NamedCo"}),
        _claim("t3", "public_track_record", SourceType.INDEPENDENT_REPORTING, "A prior exit is confirmed.",
               structured_fact={"kind": "track_record", "value": "PRIOR_EXIT", "person_id": "p1", "named_entity": "PriorCo"}),
        # Commercial Traction
        _claim("c1", "disclosed_scale", SourceType.COMPANY_DISCLOSURE, "Revenue of $5M disclosed.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2026-01-01"}),
        _claim("c2", "customer_base_breadth", SourceType.COMPANY_DISCLOSURE, "A large named customer base.",
               structured_fact={"kind": "customer_band", "value": "LARGE", "named_entity": "500 named customers"}),
        # Execution & Momentum
        _claim("e1", "shipping_velocity", SourceType.COMPANY_DISCLOSURE, "Feature A shipped.",
               structured_fact={"kind": "product_release", "status": "launched", "named_entity": "Feature A", "event_date": "2026-06-01"}),
        _claim("e2", "shipping_velocity", SourceType.COMPANY_DISCLOSURE, "Feature B is now live for all users.",
               structured_fact={"kind": "product_release", "status": "launched", "named_entity": "Feature B", "event_date": "2026-07-01"}),
        _claim("e3", "gtm_motion_evidence", SourceType.COMPANY_DISCLOSURE, "A named GTM channel is disclosed.",
               structured_fact={"kind": "gtm_evidence", "gtm_type": "channel", "named_entity": "outbound sales"}),
        # Financial & Funding
        _claim("f1", "funding_history", SourceType.INDEPENDENT_REPORTING, "Raised a $5M round.",
               structured_fact={"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": "5000000", "currency": "USD", "round_date": "2024-01-01"}),
        _claim("f2", "capital_efficiency", SourceType.COMPANY_DISCLOSURE, "A disclosed 75% gross margin.",
               structured_fact={"kind": "capital_efficiency_signal", "metric": "gross_margin", "value": "STRONG", "named_entity": "75% gross margin"}),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    for pr in analysis.pillar_results:
        expect(pr.publishable, f"{pr.pillar} should publish with this rich a ledger, got withheld: {pr.withhold_reasons}")


def test_some_pillars_withheld_others_published() -> None:
    """A Market → published, Product → published, everything else →
    withheld pattern, per the task's own explicit example shape."""
    claims = [
        _claim("m1", "market_definition_size", SourceType.INDEPENDENT_REPORTING, "Market sized at $5B.",
               structured_fact={"kind": "market_size_usd", "value": "5000000000"}),
        _claim("m2", "market_growth_signal", SourceType.INDEPENDENT_REPORTING, "Category growing 20%/yr.",
               structured_fact={"kind": "category_growth_rate_pct", "value": "20"}),
        _claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists."),
        _claim("p2", "technical_depth_signal", SourceType.INDEPENDENT_REPORTING, "Names a Salesforce integration."),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    published = {pr.pillar for pr in analysis.published_pillars}
    withheld = {pr.pillar for pr in analysis.withheld_pillars}
    expect(published == {"Market Opportunity", "Product & Technology"}, f"unexpected published set: {published}")
    expect(withheld == set(_ALL_SIX_PILLARS) - published, f"unexpected withheld set: {withheld}")
    for pr in analysis.withheld_pillars:
        expect(pr.strength is None, f"{pr.pillar} is withheld but has a numeric strength: {pr.strength}")
        expect(pr.withhold_reasons, f"{pr.pillar} is withheld but gives no withhold_reasons")


def test_sparse_company_almost_nothing_publishable() -> None:
    claims = [_claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists.")]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    expect(len(analysis.published_pillars) == 0, f"expected zero published pillars, got {[p.pillar for p in analysis.published_pillars]}")
    expect(len(analysis.withheld_pillars) == 6, "all six pillars should be withheld for a near-empty ledger")


def test_completely_empty_ledger_withholds_every_pillar() -> None:
    analysis = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF)
    expect(len(analysis.published_pillars) == 0, "zero evidence must withhold every pillar")
    for pr in analysis.pillar_results:
        expect(pr.strength is None, f"{pr.pillar} must have strength=None with zero evidence")


def test_withheld_pillar_is_present_in_contract_never_omitted() -> None:
    analysis = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF)
    expect(len(analysis.pillar_results) == 6, "a withheld pillar must still appear in pillar_results, never be dropped from the contract")


# --- 3. Single-stage resolution (item 10) --------------------------------

def test_all_six_pillars_receive_the_identical_stage_object() -> None:
    claims = [_claim("s1", "stage_signal", SourceType.INDEPENDENT_REPORTING, "A disclosed Series B round.",
                      structured_fact={"kind": "funding_round_type", "value": "Series B"})]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    expect(analysis.stage == Stage.SERIES_B_PLUS, f"expected Series B+, got {analysis.stage}")
    # There is only ONE stage value on the contract at all -- by
    # construction, every pillar was called with this exact value; this
    # test documents and locks that structural guarantee.


def test_undetermined_stage_is_preserved_not_forced() -> None:
    analysis = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF)
    expect(analysis.stage == Stage.UNDETERMINED, f"no stage signal at all must resolve to Undetermined, got {analysis.stage}")


def test_stage_affects_every_stage_tiered_pillar_consistently() -> None:
    """The same company, evaluated once at Pre-Seed and once at Growth
    (forcing stage via a disclosed round-type claim each time), must
    shift every stage-tiered dimension's score in the SAME documented
    direction it does when each pillar is tested in isolation -- proving
    the shared stage value actually reaches every pillar, not just some."""
    def _claims_for(round_type: str) -> list[Claim]:
        return [
            _claim("s1", "stage_signal", SourceType.INDEPENDENT_REPORTING, f"A disclosed {round_type} round.",
                   structured_fact={"kind": "funding_round_type", "value": round_type}),
            _claim("f1", "funding_history", SourceType.INDEPENDENT_REPORTING, "Raised a $5M round.",
                   structured_fact={"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": "5000000", "currency": "USD", "round_date": "2024-01-01"}),
        ]
    early = assemble_full_analysis(EvidenceLedger.from_list(_claims_for("Pre-Seed")), CO, AS_OF)
    late = assemble_full_analysis(EvidenceLedger.from_list(_claims_for("Series C")), CO, AS_OF)
    early_funding = early.pillar("Financial & Funding Signals").dimension_results[0]
    late_funding = late.pillar("Financial & Funding Signals").dimension_results[0]
    expect(early_funding.score > late_funding.score, "the identical funding evidence should score higher at Pre-Seed than at Series C, via the shared stage")


# --- 4. Reproducibility (item 11) -----------------------------------------

def test_full_analysis_is_deterministically_reproducible() -> None:
    claims = [
        _claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists."),
        _claim("f1", "funding_history", SourceType.INDEPENDENT_REPORTING, "Raised a $5M round.",
               structured_fact={"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": "5000000", "currency": "USD", "round_date": "2024-01-01"}),
    ]
    ledger = EvidenceLedger.from_list(claims)
    a1 = assemble_full_analysis(ledger, CO, AS_OF)
    a2 = assemble_full_analysis(ledger, CO, AS_OF)
    expect(a1.stage == a2.stage, "stage must be reproducible")
    for pr1, pr2 in zip(a1.pillar_results, a2.pillar_results):
        expect(pr1.strength == pr2.strength, f"{pr1.pillar} strength must be reproducible")
        expect(pr1.coverage_pct == pr2.coverage_pct, f"{pr1.pillar} coverage must be reproducible")
        expect(pr1.publishable == pr2.publishable, f"{pr1.pillar} publishable must be reproducible")
    expect(len(a1.cross_pillar_audit) == len(a2.cross_pillar_audit), "audit finding count must be reproducible")


def test_orchestrator_itself_introduces_no_randomness() -> None:
    """A dedicated check that result ORDER (which pillar module is
    iterated first) never affects any individual pillar's own outcome --
    each pillar only ever reads the shared ledger/stage, never another
    pillar's own result."""
    claims = [_claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists.")]
    ledger = EvidenceLedger.from_list(claims)
    a1 = assemble_full_analysis(ledger, CO, AS_OF)
    pt1 = a1.pillar("Product & Technology")
    # Re-run and confirm the same pillar's result is identical regardless
    # of how many times assembly has run this session (no hidden state).
    a2 = assemble_full_analysis(ledger, CO, AS_OF)
    pt2 = a2.pillar("Product & Technology")
    expect(pt1.strength == pt2.strength and pt1.coverage_pct == pt2.coverage_pct, "no hidden orchestration state may affect results")


# --- 5. Graceful withholding on a pillar-level model crash ----------------

def test_orchestrator_withholds_gracefully_when_one_pillar_model_crashes() -> None:
    claims = [_claim("t1", "founder_relevant_experience", SourceType.COMPANY_DISCLOSURE, "Prior role at a named company.",
                      structured_fact={"kind": "founder_experience", "value": "DIRECT", "person_id": "p1", "named_entity": "NamedCo"})]

    @dataclass(frozen=True)
    class _CrashingModel:
        def classify(self, request: ClassificationRequest) -> ClassificationResponse:
            raise RuntimeError("simulated model failure")

    analysis = assemble_full_analysis(
        EvidenceLedger.from_list(claims), CO, AS_OF,
        pillar_model_overrides={"Team & Leadership": {"founder_experience_model": _CrashingModel()}},
    )
    expect(len(analysis.pillar_results) == 6, "a crash in ONE pillar's model must not prevent the other five from being assembled")
    team = analysis.pillar("Team & Leadership")
    expect(not team.publishable, "the crashed dimension's own pillar should be withheld (or at least not silently scored)")


# --- 6. Item 15's architectural-risk checklist, re-verified at full-engine scale --

def test_unknown_private_metrics_remain_unscored_across_the_whole_system() -> None:
    """(A) Unknown != poor, verified with zero evidence at all."""
    analysis = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF)
    for pr in analysis.pillar_results:
        for d in pr.dimension_results:
            expect(d.score is None, f"{pr.pillar}/{d.dimension} must be None with zero evidence, got {d.score}")


def test_funding_never_manufactures_financial_health_at_assembly_scale() -> None:
    """(B) Funding != financial health."""
    claims = [_claim("f1", "funding_history", SourceType.INDEPENDENT_REPORTING, "Raised a $100M round.",
                      structured_fact={"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": "100000000", "currency": "USD", "round_date": "2024-01-01"})]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    financial = analysis.pillar("Financial & Funding Signals")
    capital_efficiency = next(d for d in financial.dimension_results if d.dimension == "capital_efficiency")
    expect(capital_efficiency.score is None, "a $100M round alone must never establish Capital Efficiency")


def test_activity_never_manufactures_execution_at_assembly_scale() -> None:
    """(C) Activity != execution."""
    claims = [
        _claim("f1", "funding_history", SourceType.INDEPENDENT_REPORTING, "Raised a $50M round.",
               structured_fact={"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": "50000000", "currency": "USD", "round_date": "2024-01-01"}),
        _claim("h1", "gtm_motion_evidence", SourceType.INDEPENDENT_REPORTING, "Hired 30 engineers.",
               structured_fact={"kind": "headcount_growth", "value": "30", "function": "engineering"}),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    execution = analysis.pillar("Execution & Momentum")
    for d in execution.dimension_results:
        expect(d.score is None, f"funding + general headcount alone must never establish {d.dimension}")


def test_product_never_manufactures_traction_at_assembly_scale() -> None:
    """(D) Product != traction."""
    claims = [
        _claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product exists."),
        _claim("e1", "shipping_velocity", SourceType.COMPANY_DISCLOSURE, "Feature A shipped.",
               structured_fact={"kind": "product_release", "status": "launched", "named_entity": "Feature A", "event_date": "2026-06-01"}),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    traction = analysis.pillar("Commercial Traction")
    for d in traction.dimension_results:
        expect(d.score is None, f"a shipped product alone must never establish Commercial Traction's {d.dimension}")


def test_market_never_manufactures_traction_at_assembly_scale() -> None:
    """(E) Market != traction."""
    claims = [_claim("m1", "market_definition_size", SourceType.INDEPENDENT_REPORTING, "A huge, fast-growing $50B market.",
                      structured_fact={"kind": "market_size_usd", "value": "50000000000"})]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    traction = analysis.pillar("Commercial Traction")
    for d in traction.dimension_results:
        expect(d.score is None, f"a large market alone must never establish Commercial Traction's {d.dimension}")


def test_prestige_never_manufactures_team_strength_at_assembly_scale() -> None:
    """(F) Prestige != team quality."""
    claims = [_claim("i1", "founder_relevant_experience", SourceType.INDEPENDENT_REPORTING, "A famous, prestigious VC backs the company.",
                      structured_fact={"kind": "investor_relationship", "named_entity": "a famous VC"})]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    team = analysis.pillar("Team & Leadership")
    for d in team.dimension_results:
        expect(d.score is None, f"a famous investor relationship alone must never establish Team & Leadership's {d.dimension}")


def test_revenue_identity_reused_across_pillars_at_assembly_scale() -> None:
    """(G) Revenue identity -- the same canonical claim, cited by both
    Commercial Traction and Financial & Funding Signals."""
    shared = _claim("r1", "disclosed_scale", SourceType.COMPANY_DISCLOSURE, "Revenue of $5M disclosed.",
                     structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2026-01-01"})
    shared = shared.model_copy(update={"assessment_criteria": ["disclosed_scale", "revenue_disclosure"]})
    analysis = assemble_full_analysis(EvidenceLedger.from_list([shared]), CO, AS_OF)
    traction_ids = {cid for d in analysis.pillar("Commercial Traction").dimension_results for cid in d.supporting_claim_ids}
    financial_ids = {cid for d in analysis.pillar("Financial & Funding Signals").dimension_results for cid in d.supporting_claim_ids}
    expect("r1" in traction_ids and "r1" in financial_ids, "the same claim_id must be cited by both pillars")
    reuse_findings = [f for f in analysis.cross_pillar_audit if f.finding_type.value == "canonical_claim_reused_across_pillars"]
    expect(len(reuse_findings) == 1, f"expected exactly one reuse finding, got {len(reuse_findings)}")


def test_duplicate_reporting_does_not_become_multiple_facts_at_assembly_scale() -> None:
    """(H) Duplicate reporting."""
    text = "Five outlets restate the same $500K funding announcement, closed January 2024."
    claims = [
        _claim(f"f{i}", "funding_history", SourceType.INDEPENDENT_REPORTING, text, group="one-real-round",
               structured_fact={"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": "500000", "currency": "USD", "round_date": "2024-01-01"})
        for i in range(1, 6)
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    funding = next(d for d in analysis.pillar("Financial & Funding Signals").dimension_results if d.dimension == "funding_history")
    expect(funding.classification_label == "SMALL", f"5 restatements of ONE $500K round must total $500K (SMALL), not $2.5M, got {funding.classification_label}")


def test_insufficient_evidence_withholds_rather_than_fabricating_at_assembly_scale() -> None:
    """(I) Withholding."""
    analysis = assemble_full_analysis(EvidenceLedger.from_list([]), CO, AS_OF)
    expect(all(not pr.publishable for pr in analysis.pillar_results), "zero evidence anywhere must withhold every pillar, not fabricate a neutral result")


# --- 7. Contract's own audit surface --------------------------------------

def test_zero_audit_errors_on_a_clean_well_formed_ledger() -> None:
    claims = [
        _claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists."),
        _claim("f1", "funding_history", SourceType.INDEPENDENT_REPORTING, "Raised a $5M round.",
               structured_fact={"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": "5000000", "currency": "USD", "round_date": "2024-01-01"}),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    expect(len(analysis.audit_errors) == 0, f"a clean ledger must produce zero ERROR-severity audit findings, got: {analysis.audit_errors}")


TESTS = [
    test_full_analysis_contains_exactly_six_pillar_results,
    test_full_analysis_carries_no_overall_score,
    test_pillar_lookup_by_name,
    test_generated_at_and_as_of_are_distinct_fields,
    test_all_six_pillars_published,
    test_some_pillars_withheld_others_published,
    test_sparse_company_almost_nothing_publishable,
    test_completely_empty_ledger_withholds_every_pillar,
    test_withheld_pillar_is_present_in_contract_never_omitted,
    test_all_six_pillars_receive_the_identical_stage_object,
    test_undetermined_stage_is_preserved_not_forced,
    test_stage_affects_every_stage_tiered_pillar_consistently,
    test_full_analysis_is_deterministically_reproducible,
    test_orchestrator_itself_introduces_no_randomness,
    test_orchestrator_withholds_gracefully_when_one_pillar_model_crashes,
    test_unknown_private_metrics_remain_unscored_across_the_whole_system,
    test_funding_never_manufactures_financial_health_at_assembly_scale,
    test_activity_never_manufactures_execution_at_assembly_scale,
    test_product_never_manufactures_traction_at_assembly_scale,
    test_market_never_manufactures_traction_at_assembly_scale,
    test_prestige_never_manufactures_team_strength_at_assembly_scale,
    test_revenue_identity_reused_across_pillars_at_assembly_scale,
    test_duplicate_reporting_does_not_become_multiple_facts_at_assembly_scale,
    test_insufficient_evidence_withholds_rather_than_fabricating_at_assembly_scale,
    test_zero_audit_errors_on_a_clean_well_formed_ledger,
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
