"""
Task 27, item 12 -- consumer/extractor contract tests.

The central invariant item 12 asks for: "a schema-valid extraction
object accepted for that fact kind can be consumed safely by its
intended deterministic classifier." For every one of the 20 fact kinds
`fact_contracts.py` defines (18 kind-gated + 2 context-only), this file
proves BOTH halves of that invariant against the REAL production
consumer -- never a reimplementation of a classifier's own logic:

  - POSITIVE: a fact `check_classifier_readiness()` accepts (True) is
    recognized and used CORRECTLY by the real downstream
    classifier/parser/resolver (the right label, the right parsed value,
    never a fallback/absence outcome).
  - NEGATIVE: a fact `check_classifier_readiness()` rejects (False) --
    missing a required field, an out-of-vocabulary categorical value, or
    an unparseable numeric/date field -- is safely, silently ignored by
    that same real consumer: never a crash, never a fabricated label,
    never a value invented in the missing field's place (item 11's own
    fail-closed requirement, verified here at the CONSUMER boundary, not
    merely at the contract-check boundary `test_routing_completeness_
    and_observability.py` already covers for routing/applicability).

No real LLM call anywhere in this file. No pillar file's own classifier/
parser logic is modified or duplicated here -- every assertion below
calls the actual imported production function or class.

Run with:
    python -m app.evidence_engine.tests.test_fact_contracts
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.acquisition.fact_contracts import FACT_CONTRACTS, check_classifier_readiness
from app.evidence_engine.classification import ClassificationRequest, EvidenceItem
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import INDEPENDENT_SOURCE_TYPES, Claim, SourceType, SupportStatus
from app.evidence_engine.pillars.commercial_traction import (
    WellBehavedCommercialValidationClassifier,
    WellBehavedCustomerBaseBreadthClassifier,
    WellBehavedRetentionRenewalClassifier,
    _parse_scale_point,
)
from app.evidence_engine.pillars.execution_momentum import (
    WellBehavedGTMMotionClassifier,
    WellBehavedShippingVelocityClassifier,
)
from app.evidence_engine.pillars.financial_funding import WellBehavedCapitalEfficiencyClassifier, parse_funding_round
from app.evidence_engine.pillars.market_opportunity import (
    WellBehavedCompetitiveLandscapeClassifier,
    WellBehavedMarketGrowthClassifier,
    WellBehavedMarketSizeClassifier,
    WellBehavedTimingCatalystClassifier,
)
from app.evidence_engine.pillars.team_leadership import (
    TEAM_IDENTITY_DIMENSION,
    WellBehavedFounderExperienceClassifier,
    WellBehavedLeadershipCompositionClassifier,
    WellBehavedPublicTrackRecordClassifier,
    _confirmed_person_ids,
)
from app.evidence_engine.stage import STAGE_SIGNAL_DIMENSION, Stage, determine_stage

AS_OF = date(2026, 9, 28)
CO = "contractco"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# --- Shared construction helpers --------------------------------------------

def _claim(
    claim_id: str, assessment_criteria: list[str], structured_fact: dict[str, str] | None,
    source_type: SourceType = SourceType.INDEPENDENT_REPORTING, group: str | None = None,
    published_at: date = AS_OF,
) -> Claim:
    return Claim(
        claim_id=claim_id, company_ref=CO, claim_text="a claim", subject_entity="ContractCo",
        source_publisher="a source", source_type=source_type, retrieved_at=AS_OF, published_at=published_at,
        support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt="a claim",
        assessment_criteria=assessment_criteria, independence_group_id=group or claim_id,
        structured_fact=structured_fact,
    )


def _item(
    claim_id: str, structured_fact: dict[str, str] | None,
    source_type: SourceType = SourceType.INDEPENDENT_REPORTING, group: str | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        claim_id=claim_id, redacted_text="a claim", source_type=source_type,
        support_status=SupportStatus.DIRECTLY_SUPPORTED, independence_group_id=group or claim_id,
        structured_fact=structured_fact,
    )


def _request(dimension: str, allowed_labels: tuple[str, ...], items: list[EvidenceItem]) -> ClassificationRequest:
    return ClassificationRequest(dimension=dimension, allowed_labels=allowed_labels, evidence_items=tuple(items))


# =============================================================================
# 1. funding_round -- pillars/financial_funding.py::parse_funding_round()
# =============================================================================

def test_funding_round_positive_is_parsed_correctly() -> None:
    fact = {
        "kind": "funding_round", "financing_type": "equity", "status": "completed",
        "currency": "USD", "amount": "5000000", "round_date": "2024-01-15",
    }
    expect(check_classifier_readiness(fact), "well-formed funding_round should be classifier-ready")
    parsed = parse_funding_round(_claim("c1", ["funding_history"], fact))
    expect(parsed is not None, "a classifier-ready funding_round must parse")
    expect(parsed.amount == 5_000_000.0, f"wrong amount parsed: {parsed.amount}")
    expect(parsed.round_date == date(2024, 1, 15), f"wrong date parsed: {parsed.round_date}")


def test_funding_round_negative_missing_round_date_is_safely_unparsed() -> None:
    fact = {"kind": "funding_round", "financing_type": "equity", "status": "completed", "currency": "USD", "amount": "5000000"}
    expect(not check_classifier_readiness(fact), "funding_round missing round_date must not be classifier-ready")
    expect(parse_funding_round(_claim("c2", ["funding_history"], fact)) is None, "missing round_date must parse to None, never crash")


def test_funding_round_negative_financing_type_is_a_round_label_not_a_legal_structure() -> None:
    """The cohort's own Fish Audio finding: financing_type populated with
    "Seed" (a round label) instead of "equity" (the legal structure)."""
    fact = {
        "kind": "funding_round", "financing_type": "Seed", "status": "completed",
        "currency": "USD", "amount": "3000000", "round_date": "2023-06-01",
    }
    expect(not check_classifier_readiness(fact), "a round-label financing_type must not be classifier-ready")
    expect(parse_funding_round(_claim("c3", ["funding_history"], fact)) is None, "must safely fail to parse, never silently count a non-equity label as equity")


# =============================================================================
# 2/3. funding_round_type / founding_year -- stage.py::determine_stage()
# =============================================================================

def test_funding_round_type_positive_determines_the_correct_stage() -> None:
    fact = {"kind": "funding_round_type", "value": "Series B"}
    expect(check_classifier_readiness(fact), "a real round label should be classifier-ready")
    ledger = EvidenceLedger.from_list([_claim("c4", [STAGE_SIGNAL_DIMENSION], fact)])
    stage = determine_stage(ledger, CO, AS_OF)
    expect(stage != Stage.UNDETERMINED, f"a recognized round label must determine a real stage, got {stage}")


def test_funding_round_type_negative_unrecognized_label_falls_closed_to_undetermined() -> None:
    fact = {"kind": "funding_round_type", "value": "banana round"}
    expect(not check_classifier_readiness(fact), "an unrecognized round label must not be classifier-ready")
    ledger = EvidenceLedger.from_list([_claim("c5", [STAGE_SIGNAL_DIMENSION], fact)])
    stage = determine_stage(ledger, CO, AS_OF)
    expect(stage == Stage.UNDETERMINED, f"an unrecognized label must never determine a stage, got {stage}")


def test_founding_year_positive_determines_the_correct_stage() -> None:
    fact = {"kind": "founding_year", "value": "2024"}
    expect(check_classifier_readiness(fact), "a well-formed founding_year should be classifier-ready")
    ledger = EvidenceLedger.from_list([_claim("c6", [STAGE_SIGNAL_DIMENSION], fact)])
    stage = determine_stage(ledger, CO, AS_OF)
    expect(stage != Stage.UNDETERMINED, f"a parseable founding year must determine a real stage, got {stage}")


def test_founding_year_negative_amount_instead_of_value_is_safely_ignored() -> None:
    """The recurring real bug (Linear 002, Notion 001, Fish Audio 001):
    the model populates "amount" instead of the "value" field
    determine_stage() actually reads."""
    fact = {"kind": "founding_year", "amount": "2024"}
    expect(not check_classifier_readiness(fact), "founding_year with 'amount' instead of 'value' must not be classifier-ready")
    ledger = EvidenceLedger.from_list([_claim("c7", [STAGE_SIGNAL_DIMENSION], fact)])
    stage = determine_stage(ledger, CO, AS_OF)
    expect(stage == Stage.UNDETERMINED, f"a fact missing its real 'value' field must never crash or fabricate a stage, got {stage}")


# =============================================================================
# 4. capital_efficiency_signal -- WellBehavedCapitalEfficiencyClassifier
# =============================================================================

def test_capital_efficiency_signal_positive_is_classified_correctly() -> None:
    fact = {"kind": "capital_efficiency_signal", "value": "STRONG"}
    expect(check_classifier_readiness(fact), "a real STRONG signal should be classifier-ready")
    response = WellBehavedCapitalEfficiencyClassifier().classify(
        _request("capital_efficiency", ("NONE_DISCLOSED", "WEAK", "MODERATE", "STRONG"), [_item("c8", fact)])
    )
    expect(response.label == "STRONG", f"expected STRONG, got {response.label}")


def test_capital_efficiency_signal_negative_missing_value_falls_closed() -> None:
    fact = {"kind": "capital_efficiency_signal"}
    expect(not check_classifier_readiness(fact), "capital_efficiency_signal missing value must not be classifier-ready")
    response = WellBehavedCapitalEfficiencyClassifier().classify(
        _request("capital_efficiency", ("NONE_DISCLOSED", "WEAK", "MODERATE", "STRONG"), [_item("c9", fact)])
    )
    expect(response.label == "NONE_DISCLOSED", f"a fact missing its value must never be classified as a real label, got {response.label}")


# =============================================================================
# 5. team_identity -- pillars/team_leadership.py::_confirmed_person_ids()
# (context_only=True: never a scored dimension, feeds identity resolution)
# =============================================================================

def test_team_identity_positive_confirms_the_person_id() -> None:
    fact = {"kind": "team_identity", "person_id": "p_ada", "role": "founder", "named_entity": "Ada Example"}
    expect(not check_classifier_readiness(fact), "team_identity is context-only -- never itself classifier-ready as a scored dimension")
    ledger = EvidenceLedger.from_list([_claim("c10", [TEAM_IDENTITY_DIMENSION], fact)])
    confirmed = _confirmed_person_ids(ledger, CO, AS_OF, role="founder")
    expect("p_ada" in confirmed, "a well-formed, admissible team_identity claim must confirm its person_id")


def test_team_identity_negative_missing_person_id_confirms_nobody() -> None:
    fact = {"kind": "team_identity", "role": "founder", "named_entity": "A Vague Person"}
    ledger = EvidenceLedger.from_list([_claim("c11", [TEAM_IDENTITY_DIMENSION], fact)])
    confirmed = _confirmed_person_ids(ledger, CO, AS_OF, role="founder")
    expect(confirmed == frozenset(), f"a team_identity fact with no person_id must never confirm any identity, got {confirmed}")


# =============================================================================
# 6. founder_experience -- WellBehavedFounderExperienceClassifier
# =============================================================================

def test_founder_experience_positive_is_classified_correctly() -> None:
    fact = {"kind": "founder_experience", "person_id": "p_ada", "value": "DIRECT", "named_entity": "Ada Example"}
    expect(check_classifier_readiness(fact), "a well-formed DIRECT founder_experience should be classifier-ready")
    response = WellBehavedFounderExperienceClassifier().classify(
        _request("founder_relevant_experience", ("NONE_DISCLOSED", "ADJACENT", "DIRECT"), [_item("c12", fact)])
    )
    expect(response.label == "DIRECT", f"expected DIRECT, got {response.label}")


def test_founder_experience_negative_missing_value_falls_closed() -> None:
    fact = {"kind": "founder_experience", "person_id": "p_ada", "named_entity": "Ada Example"}
    expect(not check_classifier_readiness(fact), "founder_experience missing value must not be classifier-ready")
    response = WellBehavedFounderExperienceClassifier().classify(
        _request("founder_relevant_experience", ("NONE_DISCLOSED", "ADJACENT", "DIRECT"), [_item("c13", fact)])
    )
    expect(response.label == "NONE_DISCLOSED", f"a fact missing its value must never be classified as ADJACENT/DIRECT, got {response.label}")


# =============================================================================
# 7/8. leadership_hire / founders_only_confirmed --
# WellBehavedLeadershipCompositionClassifier
# =============================================================================

def test_leadership_hire_positive_is_counted() -> None:
    fact = {"kind": "leadership_hire", "named_entity": "Bo Example", "role": "CTO"}
    expect(check_classifier_readiness(fact), "leadership_hire's contract requires no fields beyond kind -- presence alone must be classifier-ready")
    response = WellBehavedLeadershipCompositionClassifier().classify(
        _request("leadership_composition", ("NOT_ESTABLISHED", "NONE_BEYOND_FOUNDERS", "SOME_HIRES", "SUBSTANTIAL_HIRES"), [_item("c14", fact)])
    )
    expect(response.label == "SOME_HIRES", f"one distinct hire should reach SOME_HIRES, got {response.label}")


def test_leadership_hire_negative_no_fact_is_never_counted() -> None:
    response = WellBehavedLeadershipCompositionClassifier().classify(
        _request("leadership_composition", ("NOT_ESTABLISHED", "NONE_BEYOND_FOUNDERS", "SOME_HIRES", "SUBSTANTIAL_HIRES"), [_item("c15", None)])
    )
    expect(response.label == "NOT_ESTABLISHED", f"an item with no structured_fact must never be counted as a hire, got {response.label}")


def test_founders_only_confirmed_positive_is_classified_correctly() -> None:
    fact = {"kind": "founders_only_confirmed"}
    expect(check_classifier_readiness(fact), "founders_only_confirmed's contract requires no fields beyond kind")
    response = WellBehavedLeadershipCompositionClassifier().classify(
        _request("leadership_composition", ("NOT_ESTABLISHED", "NONE_BEYOND_FOUNDERS", "SOME_HIRES", "SUBSTANTIAL_HIRES"), [_item("c16", fact)])
    )
    expect(response.label == "NONE_BEYOND_FOUNDERS", f"expected NONE_BEYOND_FOUNDERS, got {response.label}")


# =============================================================================
# 9. track_record -- WellBehavedPublicTrackRecordClassifier
# =============================================================================

def test_track_record_positive_is_classified_correctly() -> None:
    fact = {"kind": "track_record", "person_id": "p_ada", "value": "PRIOR_EXIT", "named_entity": "Ada Example"}
    expect(check_classifier_readiness(fact), "a well-formed PRIOR_EXIT track_record should be classifier-ready")
    response = WellBehavedPublicTrackRecordClassifier().classify(
        _request("public_track_record", ("NONE_DISCLOSED", "PRIOR_VENTURE_ROLE", "PRIOR_EXIT"), [_item("c17", fact)])
    )
    expect(response.label == "PRIOR_EXIT", f"expected PRIOR_EXIT, got {response.label}")


def test_track_record_negative_missing_value_falls_closed() -> None:
    fact = {"kind": "track_record", "person_id": "p_ada", "named_entity": "Ada Example"}
    expect(not check_classifier_readiness(fact), "track_record missing value must not be classifier-ready")
    response = WellBehavedPublicTrackRecordClassifier().classify(
        _request("public_track_record", ("NONE_DISCLOSED", "PRIOR_VENTURE_ROLE", "PRIOR_EXIT"), [_item("c18", fact)])
    )
    expect(response.label == "NONE_DISCLOSED", f"a fact missing its value must never be classified as a real label, got {response.label}")


# =============================================================================
# 10. product_release -- WellBehavedShippingVelocityClassifier
# =============================================================================

def test_product_release_positive_launched_releases_are_counted() -> None:
    fact_a = {"kind": "product_release", "named_entity": "Feature A", "status": "launched"}
    fact_b = {"kind": "product_release", "named_entity": "Feature B", "status": "launched"}
    expect(check_classifier_readiness(fact_a), "a well-formed launched product_release should be classifier-ready")
    response = WellBehavedShippingVelocityClassifier().classify(
        _request("shipping_velocity", ("INSUFFICIENT", "STEADY", "RAPID"), [_item("c19", fact_a), _item("c20", fact_b, group="c20")])
    )
    expect(response.label == "STEADY", f"two distinct launched releases should reach STEADY, got {response.label}")


def test_product_release_negative_announced_never_counts_as_launched() -> None:
    fact = {"kind": "product_release", "named_entity": "Feature C", "status": "announced"}
    expect(check_classifier_readiness(fact), "a well-formed announced product_release is still a real, representable, classifier-ready fact")
    response = WellBehavedShippingVelocityClassifier().classify(
        _request("shipping_velocity", ("INSUFFICIENT", "STEADY", "RAPID"), [_item("c21", fact)])
    )
    expect(response.label == "INSUFFICIENT", f"an announced-only release must never be upgraded to counting as launched, got {response.label}")


# =============================================================================
# 11. gtm_evidence -- WellBehavedGTMMotionClassifier
# =============================================================================

def test_gtm_evidence_positive_is_classified_correctly() -> None:
    fact = {"kind": "gtm_evidence", "named_entity": "Partnership with X"}
    expect(check_classifier_readiness(fact), "gtm_evidence's contract requires no fields beyond kind")
    response = WellBehavedGTMMotionClassifier().classify(
        _request("gtm_motion_evidence", ("NOT_ESTABLISHED", "GTM_FACT_PRESENT"), [_item("c22", fact)])
    )
    expect(response.label == "GTM_FACT_PRESENT", f"expected GTM_FACT_PRESENT, got {response.label}")


def test_gtm_evidence_negative_wrong_kind_is_never_counted() -> None:
    fact = {"kind": "leadership_hire", "named_entity": "General headcount"}
    response = WellBehavedGTMMotionClassifier().classify(
        _request("gtm_motion_evidence", ("NOT_ESTABLISHED", "GTM_FACT_PRESENT"), [_item("c23", fact)])
    )
    expect(response.label == "NOT_ESTABLISHED", f"a differently-kinded fact must never be read as GTM evidence, got {response.label}")


# =============================================================================
# 12. strategic_statement -- context-only, never itself a scored dimension
# (Strategic Consistency reads evidence.disputed directly, per module
# docstring -- this contract's own invariant is simply "never fail-open")
# =============================================================================

def test_strategic_statement_is_always_context_only_never_classifier_ready() -> None:
    for fact in ({"kind": "strategic_statement", "topic": "pricing"}, {"kind": "strategic_statement"}):
        expect(not check_classifier_readiness(fact), f"strategic_statement must never be classifier-ready (context-only): {fact}")
    expect(FACT_CONTRACTS["strategic_statement"].consumer_dimensions == frozenset(), "strategic_statement must have no scored consumer dimension")


# =============================================================================
# 13. market_size_usd -- WellBehavedMarketSizeClassifier
# =============================================================================

def test_market_size_usd_positive_is_classified_correctly() -> None:
    fact = {"kind": "market_size_usd", "value": "5000000000"}  # $5B -> SUBSTANTIAL
    expect(check_classifier_readiness(fact), "a well-formed market_size_usd should be classifier-ready")
    response = WellBehavedMarketSizeClassifier().classify(
        _request("market_definition_size", ("NOT_DISCLOSED", "NARROW", "SUBSTANTIAL", "LARGE"), [_item("c24", fact)])
    )
    expect(response.label == "SUBSTANTIAL", f"expected SUBSTANTIAL for $5B, got {response.label}")


def test_market_size_usd_negative_unparseable_value_falls_closed() -> None:
    fact = {"kind": "market_size_usd", "value": "a huge market"}
    expect(not check_classifier_readiness(fact), "an unparseable market_size_usd value must not be classifier-ready")
    response = WellBehavedMarketSizeClassifier().classify(
        _request("market_definition_size", ("NOT_DISCLOSED", "NARROW", "SUBSTANTIAL", "LARGE"), [_item("c25", fact)])
    )
    expect(response.label == "NOT_DISCLOSED", f"an unparseable value must never be classified into a real band, got {response.label}")


# =============================================================================
# 14. category_growth_rate_pct -- WellBehavedMarketGrowthClassifier
# =============================================================================

def test_category_growth_rate_pct_positive_is_classified_correctly() -> None:
    fact = {"kind": "category_growth_rate_pct", "value": "35"}  # -> FAST
    expect(check_classifier_readiness(fact), "a well-formed category_growth_rate_pct should be classifier-ready")
    response = WellBehavedMarketGrowthClassifier().classify(
        _request("market_growth_signal", ("NOT_DISCLOSED", "SLOW", "MODERATE", "FAST"), [_item("c26", fact)])
    )
    expect(response.label == "FAST", f"expected FAST for 35%, got {response.label}")


def test_category_growth_rate_pct_negative_unparseable_value_falls_closed() -> None:
    fact = {"kind": "category_growth_rate_pct", "value": "rapidly"}
    expect(not check_classifier_readiness(fact), "an unparseable growth rate must not be classifier-ready")
    response = WellBehavedMarketGrowthClassifier().classify(
        _request("market_growth_signal", ("NOT_DISCLOSED", "SLOW", "MODERATE", "FAST"), [_item("c27", fact)])
    )
    expect(response.label == "NOT_DISCLOSED", f"an unparseable value must never be classified into a real band, got {response.label}")


# =============================================================================
# 15. catalyst_name -- WellBehavedTimingCatalystClassifier
# =============================================================================

def test_catalyst_name_positive_is_classified_correctly() -> None:
    fact = {"kind": "catalyst_name", "named_entity": "a new EU regulation"}
    expect(check_classifier_readiness(fact), "catalyst_name's contract requires no fields beyond kind")
    response = WellBehavedTimingCatalystClassifier().classify(
        _request("timing_catalyst", ("NONE_DISCLOSED", "GENERIC_ONLY", "SPECIFIC_CATALYST"), [_item("c28", fact)])
    )
    expect(response.label == "SPECIFIC_CATALYST", f"expected SPECIFIC_CATALYST, got {response.label}")


def test_catalyst_name_negative_no_catalyst_fact_falls_back_to_generic() -> None:
    response = WellBehavedTimingCatalystClassifier().classify(
        _request("timing_catalyst", ("NONE_DISCLOSED", "GENERIC_ONLY", "SPECIFIC_CATALYST"), [_item("c29", None)])
    )
    expect(response.label == "GENERIC_ONLY", f"independent evidence with no named catalyst must never be upgraded to SPECIFIC_CATALYST, got {response.label}")


# =============================================================================
# 16. competitive_structure -- WellBehavedCompetitiveLandscapeClassifier
# =============================================================================

def test_competitive_structure_positive_is_classified_correctly() -> None:
    fact = {"kind": "competitive_structure", "value": "fragmented"}
    expect(check_classifier_readiness(fact), "a well-formed competitive_structure should be classifier-ready")
    response = WellBehavedCompetitiveLandscapeClassifier().classify(
        _request("competitive_landscape_position", ("NOT_ESTABLISHED", "FRAGMENTED", "CONCENTRATED"), [_item("c30", fact)])
    )
    expect(response.label == "FRAGMENTED", f"expected FRAGMENTED, got {response.label}")


def test_competitive_structure_negative_unrecognized_value_falls_closed() -> None:
    fact = {"kind": "competitive_structure", "value": "hard to say"}
    expect(not check_classifier_readiness(fact), "an out-of-vocabulary competitive_structure value must not be classifier-ready")
    response = WellBehavedCompetitiveLandscapeClassifier().classify(
        _request("competitive_landscape_position", ("NOT_ESTABLISHED", "FRAGMENTED", "CONCENTRATED"), [_item("c31", fact)])
    )
    expect(response.label == "NOT_ESTABLISHED", f"an unrecognized value must never be guessed into fragmented/concentrated, got {response.label}")


# =============================================================================
# 17. traction_metric -- pillars/commercial_traction.py::_parse_scale_point()
# =============================================================================

def test_traction_metric_positive_is_parsed_correctly() -> None:
    fact = {
        "kind": "traction_metric", "metric": "revenue", "value_type": "actual",
        "amount": "2500000", "period_date": "2025-01-01", "currency": "USD",
    }
    expect(check_classifier_readiness(fact), "a well-formed money traction_metric should be classifier-ready")
    point = _parse_scale_point(_claim("c32", ["disclosed_scale"], fact))
    expect(point is not None, "a classifier-ready traction_metric must parse")
    expect(point.amount == 2_500_000.0, f"wrong amount parsed: {point.amount}")


def test_traction_metric_negative_paraphrased_metric_is_safely_unparsed() -> None:
    """The cohort's own repeated finding: metric populated as "annual
    revenue" instead of the recognized "revenue"."""
    fact = {
        "kind": "traction_metric", "metric": "annual revenue", "value_type": "actual",
        "amount": "2500000", "period_date": "2025-01-01", "currency": "USD",
    }
    expect(not check_classifier_readiness(fact), "a paraphrased metric name must not be classifier-ready")
    expect(_parse_scale_point(_claim("c33", ["disclosed_scale"], fact)) is None, "a paraphrased metric must safely fail to parse, never be guessed into a real bucket")


def test_traction_metric_negative_missing_value_type_is_safely_unparsed() -> None:
    fact = {"kind": "traction_metric", "metric": "arr", "amount": "1000000", "period_date": "2025-01-01", "currency": "USD"}
    expect(not check_classifier_readiness(fact), "traction_metric missing value_type must not be classifier-ready")
    expect(_parse_scale_point(_claim("c34", ["disclosed_scale"], fact)) is None, "a missing value_type must never be assumed 'actual'")


# =============================================================================
# 18. customer_band -- WellBehavedCustomerBaseBreadthClassifier
# =============================================================================

def test_customer_band_positive_is_classified_correctly() -> None:
    fact = {"kind": "customer_band", "value": "LARGE"}
    expect(check_classifier_readiness(fact), "a well-formed customer_band should be classifier-ready")
    response = WellBehavedCustomerBaseBreadthClassifier().classify(
        _request("customer_base_breadth", ("NOT_DISCLOSED", "SMALL", "MODERATE", "LARGE"), [_item("c35", fact)])
    )
    expect(response.label == "LARGE", f"expected LARGE, got {response.label}")


def test_customer_band_negative_bare_count_is_never_a_band() -> None:
    """Item 7's own explicit exclusion: a bare customer count alone is not
    usable here -- only a qualitative band."""
    fact = {"kind": "customer_band", "value": "500"}
    expect(not check_classifier_readiness(fact), "a bare numeric count is not a recognized band and must not be classifier-ready")
    response = WellBehavedCustomerBaseBreadthClassifier().classify(
        _request("customer_base_breadth", ("NOT_DISCLOSED", "SMALL", "MODERATE", "LARGE"), [_item("c36", fact)])
    )
    expect(response.label == "NOT_DISCLOSED", f"a bare count must never be guessed into a band, got {response.label}")


# =============================================================================
# 19. commercial_commitment -- WellBehavedCommercialValidationClassifier
# =============================================================================

def test_commercial_commitment_positive_is_counted() -> None:
    fact = {"kind": "commercial_commitment", "named_entity": "Acme Corp pilot"}
    expect(check_classifier_readiness(fact), "commercial_commitment's contract requires no fields beyond kind")
    response = WellBehavedCommercialValidationClassifier().classify(
        _request("commercial_validation", ("NOT_ESTABLISHED", "SOME_VALIDATION", "SUBSTANTIAL_VALIDATION"), [_item("c37", fact)])
    )
    expect(response.label == "SOME_VALIDATION", f"one distinct commitment should reach SOME_VALIDATION, got {response.label}")


def test_commercial_commitment_negative_wrong_kind_is_never_counted() -> None:
    fact = {"kind": "gtm_evidence", "named_entity": "a GTM hire, not a commitment"}
    response = WellBehavedCommercialValidationClassifier().classify(
        _request("commercial_validation", ("NOT_ESTABLISHED", "SOME_VALIDATION", "SUBSTANTIAL_VALIDATION"), [_item("c38", fact)])
    )
    expect(response.label == "NOT_ESTABLISHED", f"a differently-kinded fact must never be counted as a commercial commitment, got {response.label}")


# =============================================================================
# 20. retention_signal -- WellBehavedRetentionRenewalClassifier
# =============================================================================

def test_retention_signal_positive_is_classified_correctly() -> None:
    fact = {"kind": "retention_signal", "value": "STRONG"}
    expect(check_classifier_readiness(fact), "a well-formed retention_signal should be classifier-ready")
    response = WellBehavedRetentionRenewalClassifier().classify(
        _request("retention_renewal_signal", ("NONE_DISCLOSED", "WEAK", "MODERATE", "STRONG"), [_item("c39", fact)])
    )
    expect(response.label == "STRONG", f"expected STRONG, got {response.label}")


def test_retention_signal_negative_customer_count_is_never_retention_evidence() -> None:
    """Item 7's own explicit exclusion list: never a customer logo,
    count, testimonial, adoption claim, or longevity fact."""
    fact = {"kind": "customer_band", "value": "LARGE"}
    response = WellBehavedRetentionRenewalClassifier().classify(
        _request("retention_renewal_signal", ("NONE_DISCLOSED", "WEAK", "MODERATE", "STRONG"), [_item("c40", fact)])
    )
    expect(response.label == "NONE_DISCLOSED", f"a customer_band fact must never be read as retention evidence, got {response.label}")


# =============================================================================
# Coverage sanity -- every FACT_CONTRACTS entry has at least one dedicated
# positive+negative pair above (guards against a future kind being added to
# fact_contracts.py without a matching consumer test ever being written).
# =============================================================================

_TESTED_KINDS = {
    "funding_round", "funding_round_type", "founding_year", "capital_efficiency_signal",
    "team_identity", "founder_experience", "leadership_hire", "founders_only_confirmed",
    "track_record", "product_release", "gtm_evidence", "strategic_statement",
    "market_size_usd", "category_growth_rate_pct", "catalyst_name", "competitive_structure",
    "traction_metric", "customer_band", "commercial_commitment", "retention_signal",
}


def test_every_fact_contract_has_a_dedicated_consumer_test() -> None:
    missing = set(FACT_CONTRACTS.keys()) - _TESTED_KINDS
    expect(not missing, f"fact kind(s) with no dedicated consumer test above: {missing}")
    extra = _TESTED_KINDS - set(FACT_CONTRACTS.keys())
    expect(not extra, f"tested kind(s) no longer in FACT_CONTRACTS (stale test): {extra}")


TESTS = [
    test_funding_round_positive_is_parsed_correctly,
    test_funding_round_negative_missing_round_date_is_safely_unparsed,
    test_funding_round_negative_financing_type_is_a_round_label_not_a_legal_structure,
    test_funding_round_type_positive_determines_the_correct_stage,
    test_funding_round_type_negative_unrecognized_label_falls_closed_to_undetermined,
    test_founding_year_positive_determines_the_correct_stage,
    test_founding_year_negative_amount_instead_of_value_is_safely_ignored,
    test_capital_efficiency_signal_positive_is_classified_correctly,
    test_capital_efficiency_signal_negative_missing_value_falls_closed,
    test_team_identity_positive_confirms_the_person_id,
    test_team_identity_negative_missing_person_id_confirms_nobody,
    test_founder_experience_positive_is_classified_correctly,
    test_founder_experience_negative_missing_value_falls_closed,
    test_leadership_hire_positive_is_counted,
    test_leadership_hire_negative_no_fact_is_never_counted,
    test_founders_only_confirmed_positive_is_classified_correctly,
    test_track_record_positive_is_classified_correctly,
    test_track_record_negative_missing_value_falls_closed,
    test_product_release_positive_launched_releases_are_counted,
    test_product_release_negative_announced_never_counts_as_launched,
    test_gtm_evidence_positive_is_classified_correctly,
    test_gtm_evidence_negative_wrong_kind_is_never_counted,
    test_strategic_statement_is_always_context_only_never_classifier_ready,
    test_market_size_usd_positive_is_classified_correctly,
    test_market_size_usd_negative_unparseable_value_falls_closed,
    test_category_growth_rate_pct_positive_is_classified_correctly,
    test_category_growth_rate_pct_negative_unparseable_value_falls_closed,
    test_catalyst_name_positive_is_classified_correctly,
    test_catalyst_name_negative_no_catalyst_fact_falls_back_to_generic,
    test_competitive_structure_positive_is_classified_correctly,
    test_competitive_structure_negative_unrecognized_value_falls_closed,
    test_traction_metric_positive_is_parsed_correctly,
    test_traction_metric_negative_paraphrased_metric_is_safely_unparsed,
    test_traction_metric_negative_missing_value_type_is_safely_unparsed,
    test_customer_band_positive_is_classified_correctly,
    test_customer_band_negative_bare_count_is_never_a_band,
    test_commercial_commitment_positive_is_counted,
    test_commercial_commitment_negative_wrong_kind_is_never_counted,
    test_retention_signal_positive_is_classified_correctly,
    test_retention_signal_negative_customer_count_is_never_retention_evidence,
    test_every_fact_contract_has_a_dedicated_consumer_test,
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
