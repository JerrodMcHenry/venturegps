"""
Task 18 -- dedicated tests for `cross_pillar_audit.py`. Constructs
already-computed `PillarResult` sets by hand (via `full_analysis.
assemble_full_analysis`) and verifies each individual audit check fires
exactly when it should and never when it shouldn't -- including the
documented exceptions (Strategic Consistency's own legitimate use of
disputed evidence; a withheld pillar's own gate-blind Strength
recomputation, item 6's own "prefer structured audit findings" list).

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_cross_pillar_audit
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.cross_pillar_audit import AuditFindingType, AuditSeverity
from app.evidence_engine.full_analysis import assemble_full_analysis
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim, SourceType, SupportStatus

AS_OF = date(2026, 9, 28)
CO = "auditco"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _claim(
    claim_id: str, dimension: str, source_type: SourceType, text: str,
    group: str | None = None, structured_fact: dict[str, str] | None = None,
    support_status: SupportStatus = SupportStatus.DIRECTLY_SUPPORTED,
    published_at: date = AS_OF, contradicts: list[str] | None = None,
) -> Claim:
    return Claim(
        claim_id=claim_id, company_ref=CO, claim_text=text, subject_entity="AuditCo",
        source_publisher="a source", source_type=source_type, retrieved_at=AS_OF, published_at=published_at,
        support_status=support_status, excerpt=None if support_status == SupportStatus.DISPUTED else text,
        assessment_criteria=[dimension], independence_group_id=group or claim_id,
        structured_fact=structured_fact, contradicts=contradicts or [],
    )


def _findings_of(analysis, finding_type: AuditFindingType):
    return [f for f in analysis.cross_pillar_audit if f.finding_type == finding_type]


# --- 1. Legitimate reuse vs. accidental duplication ------------------------

def test_legitimate_reuse_is_info_not_warning_or_error() -> None:
    shared = _claim("r1", "disclosed_scale", SourceType.COMPANY_DISCLOSURE, "Revenue of $5M disclosed.",
                     structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2026-01-01"})
    shared = shared.model_copy(update={"assessment_criteria": ["disclosed_scale", "revenue_disclosure"]})
    analysis = assemble_full_analysis(EvidenceLedger.from_list([shared]), CO, AS_OF)
    reuse = _findings_of(analysis, AuditFindingType.CANONICAL_CLAIM_REUSED_ACROSS_PILLARS)
    expect(len(reuse) == 1, f"expected exactly one reuse finding, got {len(reuse)}")
    expect(reuse[0].severity == AuditSeverity.INFO, f"legitimate reuse must be INFO, got {reuse[0].severity}")
    expect(set(reuse[0].related_pillars) == {"Commercial Traction", "Financial & Funding Signals"}, str(reuse[0].related_pillars))


def test_no_reuse_finding_when_a_claim_serves_only_one_pillar() -> None:
    claims = [_claim("r1", "disclosed_scale", SourceType.COMPANY_DISCLOSURE, "Revenue of $5M disclosed.",
                      structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2026-01-01"})]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    reuse = _findings_of(analysis, AuditFindingType.CANONICAL_CLAIM_REUSED_ACROSS_PILLARS)
    expect(len(reuse) == 0, f"a claim used by only one pillar must not be flagged as reused, got {reuse}")


def test_duplicate_extraction_across_pillars_is_detected() -> None:
    claims = [
        _claim("r1", "disclosed_scale", SourceType.COMPANY_DISCLOSURE, "Revenue of $2M disclosed.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "2000000", "currency": "USD", "value_type": "actual", "period_date": "2026-06-30"}),
        _claim("r2", "revenue_disclosure", SourceType.INDEPENDENT_REPORTING, "Independent reporting gives revenue of $5M.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2026-07-15"}),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    dup = _findings_of(analysis, AuditFindingType.POSSIBLE_DUPLICATE_EXTRACTION_ACROSS_PILLARS)
    expect(len(dup) == 1, f"expected exactly one duplicate-extraction finding, got {len(dup)}")
    expect(dup[0].severity == AuditSeverity.WARNING, str(dup[0].severity))
    expect(set(dup[0].related_claim_ids) == {"r1", "r2"}, str(dup[0].related_claim_ids))


def test_duplicate_extraction_not_flagged_when_amounts_agree() -> None:
    """Two independent, genuinely-agreeing figures across pillars are
    corroboration, not a duplicate-extraction concern."""
    claims = [
        _claim("r1", "disclosed_scale", SourceType.COMPANY_DISCLOSURE, "Revenue of $5.0M disclosed.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2026-06-30"}),
        _claim("r2", "revenue_disclosure", SourceType.INDEPENDENT_REPORTING, "Independent reporting confirms revenue near $5.05M.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5050000", "currency": "USD", "value_type": "actual", "period_date": "2026-07-15"}),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    dup = _findings_of(analysis, AuditFindingType.POSSIBLE_DUPLICATE_EXTRACTION_ACROSS_PILLARS)
    expect(len(dup) == 0, f"agreeing figures within tolerance must not be flagged, got {dup}")


def test_duplicate_extraction_not_flagged_when_properly_linked_via_contradicts() -> None:
    """When the conflict IS properly tagged disputed/contradicts, the
    ordinary dispute mechanism already handles it -- the audit's
    duplicate-extraction check must not pile on a redundant finding."""
    claims = [
        _claim("r1", "disclosed_scale", SourceType.COMPANY_DISCLOSURE, "Revenue of $2M disclosed.",
               support_status=SupportStatus.DISPUTED, contradicts=["r2"],
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "2000000", "currency": "USD", "value_type": "actual", "period_date": "2026-06-30"}),
        _claim("r2", "revenue_disclosure", SourceType.INDEPENDENT_REPORTING, "Independent reporting gives revenue of $5M.",
               support_status=SupportStatus.DISPUTED, contradicts=["r1"],
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2026-07-15"}),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    dup = _findings_of(analysis, AuditFindingType.POSSIBLE_DUPLICATE_EXTRACTION_ACROSS_PILLARS)
    expect(len(dup) == 0, f"a properly-disputed pair must not also trigger the duplicate-extraction warning, got {dup}")


def test_duplicate_extraction_not_flagged_across_distant_periods() -> None:
    claims = [
        _claim("r1", "disclosed_scale", SourceType.COMPANY_DISCLOSURE, "Revenue of $2M in 2023.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "2000000", "currency": "USD", "value_type": "actual", "period_date": "2023-01-01"}),
        _claim("r2", "revenue_disclosure", SourceType.INDEPENDENT_REPORTING, "Revenue of $5M in 2026.",
               structured_fact={"kind": "traction_metric", "metric": "revenue", "amount": "5000000", "currency": "USD", "value_type": "actual", "period_date": "2026-06-30"}),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    dup = _findings_of(analysis, AuditFindingType.POSSIBLE_DUPLICATE_EXTRACTION_ACROSS_PILLARS)
    expect(len(dup) == 0, "different reporting periods are different facts, not a duplicate-extraction concern")


# --- 2. Disputed evidence used (with the documented exception) -----------

def test_disputed_evidence_used_is_structurally_impossible_normally() -> None:
    """The ordinary case: disputed claims are always excluded from
    admissible evidence by the shared ledger, so this check should find
    nothing across a normal, correctly-functioning ledger."""
    claims = [
        _claim("c1", "customer_base_breadth", SourceType.COMPANY_DISCLOSURE, "Large customer base claimed.",
               support_status=SupportStatus.DISPUTED, contradicts=["c2"],
               structured_fact={"kind": "customer_band", "value": "LARGE", "named_entity": "thousands of customers"}),
        _claim("c2", "customer_base_breadth", SourceType.INDEPENDENT_REPORTING, "Independent reporting: sparse traction.",
               support_status=SupportStatus.DISPUTED, contradicts=["c1"],
               structured_fact={"kind": "customer_band", "value": "SMALL", "named_entity": "under 100 customers"}),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    expect(len(_findings_of(analysis, AuditFindingType.DISPUTED_EVIDENCE_USED)) == 0, "disputed claims must never actually be cited")
    traction = analysis.pillar("Commercial Traction")
    cbb = next(d for d in traction.dimension_results if d.dimension == "customer_base_breadth")
    expect(cbb.score is None, "the disputed customer-count pair must resolve to Unscored, not a score")


def test_strategic_consistency_disputed_citation_is_not_flagged() -> None:
    """The one documented exception: Strategic Consistency legitimately
    cites disputed claims as the evidence FOR its own CONTAINS_
    CONTRADICTION verdict -- the audit must not flag this as a defect."""
    claims = [
        _claim("s1", "strategic_consistency", SourceType.COMPANY_DISCLOSURE, "States it targets enterprise customers exclusively.",
               support_status=SupportStatus.DISPUTED, contradicts=["s2"]),
        _claim("s2", "strategic_consistency", SourceType.COMPANY_DISCLOSURE, "Elsewhere states it targets only small businesses.",
               support_status=SupportStatus.DISPUTED, contradicts=["s1"], published_at=date(2026, 8, 1)),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    execution = analysis.pillar("Execution & Momentum")
    sc = next(d for d in execution.dimension_results if d.dimension == "strategic_consistency")
    expect(sc.classification_label == "CONTAINS_CONTRADICTION", f"expected CONTAINS_CONTRADICTION, got {sc.classification_label}")
    expect(sc.score is not None, "a detected contradiction is a real, scored outcome")
    expect(len(_findings_of(analysis, AuditFindingType.DISPUTED_EVIDENCE_USED)) == 0, "the documented Strategic Consistency exception must not be flagged")


# --- 3. Stale evidence used ------------------------------------------------

def test_stale_evidence_is_never_actually_cited_normally() -> None:
    """The ordinary blanket-staleness dimensions correctly exclude stale
    claims before they could ever be cited -- this check should find
    nothing given the shared, unmodified staleness mechanism."""
    from datetime import timedelta
    old = AS_OF - timedelta(days=2000)
    claims = [_claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists.", published_at=old)]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    expect(len(_findings_of(analysis, AuditFindingType.STALE_EVIDENCE_USED)) == 0, "a stale claim must never actually be cited in the first place")


def test_funding_history_exception_is_not_flagged_as_stale() -> None:
    """Funding History's own documented no-staleness-exclusion behavior
    (Task 17) must not be misinterpreted as a defect by the audit."""
    claims = [_claim("f1", "funding_history", SourceType.INDEPENDENT_REPORTING, "A disclosed 2019 round.",
                      published_at=date(2019, 1, 1),
                      structured_fact={"kind": "funding_round", "financing_type": "equity", "status": "completed", "amount": "5000000", "currency": "USD", "round_date": "2019-01-01"})]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    expect(len(_findings_of(analysis, AuditFindingType.STALE_EVIDENCE_USED)) == 0, "the documented Funding History exception must not be flagged as stale")
    funding = next(d for d in analysis.pillar("Financial & Funding Signals").dimension_results if d.dimension == "funding_history")
    expect(funding.score is not None, "the old round must still score, per Task 17's own documented behavior")


# --- 4. Traceability -------------------------------------------------------

def test_traceability_is_clean_on_a_well_formed_ledger() -> None:
    claims = [_claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists.")]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    expect(len(_findings_of(analysis, AuditFindingType.UNSUPPORTED_DIMENSION_RESULT)) == 0, "a well-formed ledger must produce zero traceability findings")


# --- 5. Strength / publication invariants (the gate-aware fix) -----------

def test_a_single_scored_dimension_below_gate_2_is_not_flagged_as_a_strength_mismatch() -> None:
    """The exact false-positive this audit check originally had:
    compute_pillar_strength() is gate-blind (spec Part 6.6's firewall
    property) and would happily compute a number from one scorable
    dimension even though the pillar's own real, correct Strength is
    None (withheld, gate 2 failed). The audit must recognize this is
    NOT an inconsistency."""
    claims = [_claim("t1", "founder_relevant_experience", SourceType.COMPANY_DISCLOSURE, "Prior role at a named company.",
                      structured_fact={"kind": "founder_experience", "value": "DIRECT", "person_id": "p1", "named_entity": "NamedCo"})]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    team = analysis.pillar("Team & Leadership")
    expect(not team.publishable, "sanity: this fixture is designed to have exactly 1 scored dimension, below gate 2")
    expect(len(_findings_of(analysis, AuditFindingType.STRENGTH_INCONSISTENT_WITH_SCORABLE_DIMENSIONS)) == 0, "a withheld pillar's gate-blind recomputation must not be flagged")
    expect(len(_findings_of(analysis, AuditFindingType.WITHHELD_PILLAR_HAS_NUMERIC_STRENGTH)) == 0, "the pillar correctly reports strength=None, so this must not fire either")


def test_published_pillar_strength_matches_independent_recomputation() -> None:
    claims = [
        _claim("p1", "product_existence_maturity", SourceType.PRODUCT_DOCUMENTATION, "A live product page exists."),
        _claim("p2", "technical_depth_signal", SourceType.INDEPENDENT_REPORTING, "Names a Salesforce integration."),
    ]
    analysis = assemble_full_analysis(EvidenceLedger.from_list(claims), CO, AS_OF)
    pt = analysis.pillar("Product & Technology")
    expect(pt.publishable, "sanity: this fixture should clear both gates")
    expect(len(_findings_of(analysis, AuditFindingType.STRENGTH_INCONSISTENT_WITH_SCORABLE_DIMENSIONS)) == 0, "a genuinely published pillar's own strength must match the independent recomputation")


TESTS = [
    test_legitimate_reuse_is_info_not_warning_or_error,
    test_no_reuse_finding_when_a_claim_serves_only_one_pillar,
    test_duplicate_extraction_across_pillars_is_detected,
    test_duplicate_extraction_not_flagged_when_amounts_agree,
    test_duplicate_extraction_not_flagged_when_properly_linked_via_contradicts,
    test_duplicate_extraction_not_flagged_across_distant_periods,
    test_disputed_evidence_used_is_structurally_impossible_normally,
    test_strategic_consistency_disputed_citation_is_not_flagged,
    test_stale_evidence_is_never_actually_cited_normally,
    test_funding_history_exception_is_not_flagged_as_stale,
    test_traceability_is_clean_on_a_well_formed_ledger,
    test_a_single_scored_dimension_below_gate_2_is_not_flagged_as_a_strength_mismatch,
    test_published_pillar_strength_matches_independent_recomputation,
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
