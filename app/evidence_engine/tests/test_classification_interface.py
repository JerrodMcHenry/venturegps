"""
Task 9, item 2 -- the AI classification/extraction interface itself:
validate_classification()/validate_extraction() must reject an invalid
label, a citation of a claim that does not exist or is not admissible,
and a label the cited evidence does not structurally establish --
regardless of what the (mocked) model asserts. Also covers
identity-blindness (redaction) at the interface boundary.

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_classification_interface
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine.classification import (
    ClassificationRequest,
    ClassificationResponse,
    ExtractionRequest,
    ExtractionResponse,
    redact_company_identity,
    requires_independent_source,
    requires_minimum_distinct_facts,
    to_evidence_items,
    validate_classification,
    validate_extraction,
)
from app.evidence_engine.ledger import EvidenceLedger, resolve_dimension_evidence
from app.evidence_engine.models import Claim, SourceType, SupportStatus

AS_OF = date(2026, 9, 27)
DIMENSION = "differentiation_claim_corroboration"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _claim(claim_id: str, source_type: SourceType, group: str, text: str = "A claim.") -> Claim:
    # `text` defaults to a shared placeholder for tests that don't exercise
    # provenance/independence verification at all (it only runs when a
    # `requires_minimum_distinct_facts` check is actually in play) --
    # tests that DO exercise it (below) must pass genuinely distinct text,
    # or app.evidence_engine.provenance would correctly (not incorrectly)
    # judge identical placeholder text across claims as the same
    # underlying disclosure.
    return Claim(
        claim_id=claim_id, company_ref="acme", claim_text=text, subject_entity="acme",
        source_publisher="somewhere", source_type=source_type, retrieved_at=AS_OF,
        support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt=text,
        assessment_criteria=[DIMENSION], independence_group_id=group,
    )


def _evidence():
    independent = _claim("c-001", SourceType.INDEPENDENT_REPORTING, "g1")
    company_only = _claim("c-002", SourceType.COMPANY_DISCLOSURE, "g2")
    ledger = EvidenceLedger.from_list([independent, company_only])
    return resolve_dimension_evidence(ledger, DIMENSION, AS_OF, staleness_days=730), independent, company_only


def test_invalid_label_is_rejected() -> None:
    evidence, independent, _ = _evidence()
    request = ClassificationRequest(
        dimension=DIMENSION, allowed_labels=("NONE_DISCLOSED", "UNCORROBORATED", "CORROBORATED"),
        evidence_items=to_evidence_items(evidence.admissible, ()),
    )
    response = ClassificationResponse(label="DEFINITELY_TRUE", supporting_claim_ids=(independent.claim_id,))
    violations = validate_classification(response, request, evidence)
    expect(len(violations) == 1, f"Expected exactly one violation for an invalid label, got {violations}")
    expect("not one of the allowed labels" in violations[0], f"Wrong violation message: {violations[0]}")


def test_citation_of_nonexistent_claim_is_rejected() -> None:
    evidence, independent, _ = _evidence()
    request = ClassificationRequest(
        dimension=DIMENSION, allowed_labels=("NONE_DISCLOSED", "UNCORROBORATED", "CORROBORATED"),
        evidence_items=to_evidence_items(evidence.admissible, ()),
    )
    response = ClassificationResponse(label="CORROBORATED", supporting_claim_ids=("claim-that-does-not-exist",))
    violations = validate_classification(response, request, evidence)
    expect(len(violations) == 1, f"Expected one violation for a fabricated claim_id, got {violations}")
    expect("does not exist" in violations[0] or "not currently admissible" in violations[0], violations[0])


def test_citation_of_inadmissible_claim_is_rejected() -> None:
    # A claim that IS real but is disputed/stale (not admissible) must not
    # be accepted as a citation even though it "exists."
    evidence, independent, company_only = _evidence()
    stale_claim = _claim("c-003", SourceType.INDEPENDENT_REPORTING, "g3")
    ledger = EvidenceLedger.from_list([independent, company_only])  # c-003 deliberately NOT in the ledger
    request = ClassificationRequest(
        dimension=DIMENSION, allowed_labels=("NONE_DISCLOSED", "UNCORROBORATED", "CORROBORATED"),
        evidence_items=to_evidence_items(evidence.admissible, ()),
    )
    response = ClassificationResponse(label="CORROBORATED", supporting_claim_ids=(stale_claim.claim_id,))
    violations = validate_classification(response, request, evidence)
    expect(len(violations) == 1, f"Expected one violation citing an inadmissible/unknown claim, got {violations}")


def test_label_exceeding_cited_evidence_is_rejected() -> None:
    # CORROBORATED requires an independent source among the CITED claims.
    # Citing only the company-disclosure claim, even though an independent
    # claim exists elsewhere in the ledger, must be rejected -- credit
    # only what was actually cited.
    evidence, independent, company_only = _evidence()
    request = ClassificationRequest(
        dimension=DIMENSION, allowed_labels=("NONE_DISCLOSED", "UNCORROBORATED", "CORROBORATED"),
        evidence_items=to_evidence_items(evidence.admissible, ()),
    )
    response = ClassificationResponse(label="CORROBORATED", supporting_claim_ids=(company_only.claim_id,))
    violations = validate_classification(
        response, request, evidence, requires_independent_source(frozenset({"CORROBORATED"}))
    )
    expect(len(violations) == 1, f"Expected one violation for a label unsupported by its own cited evidence, got {violations}")
    expect("requires at least one independently-sourced" in violations[0], violations[0])


def test_label_backed_by_real_independent_citation_is_accepted() -> None:
    evidence, independent, _ = _evidence()
    request = ClassificationRequest(
        dimension=DIMENSION, allowed_labels=("NONE_DISCLOSED", "UNCORROBORATED", "CORROBORATED"),
        evidence_items=to_evidence_items(evidence.admissible, ()),
    )
    response = ClassificationResponse(label="CORROBORATED", supporting_claim_ids=(independent.claim_id,))
    violations = validate_classification(
        response, request, evidence, requires_independent_source(frozenset({"CORROBORATED"}))
    )
    expect(not violations, f"A correctly-cited, evidence-backed label must be accepted, got violations: {violations}")


def test_minimum_distinct_facts_requirement_rejects_a_single_cited_group() -> None:
    check = requires_minimum_distinct_facts({"SUBSTANTIAL": 3})
    one_claim = _claim("t-001", SourceType.INDEPENDENT_REPORTING, "same-group")
    reason = check("SUBSTANTIAL", (one_claim,))
    expect(reason is not None, "SUBSTANTIAL cited from only one distinct fact must be rejected")
    expect(">= 3 provenance-verified distinct facts" in reason, reason)


def test_minimum_distinct_facts_requirement_accepts_enough_distinct_groups() -> None:
    check = requires_minimum_distinct_facts({"SUBSTANTIAL": 3})
    # Genuinely distinct text per claim -- provenance verification must
    # NOT fold these together the way it correctly would for near-
    # identical/syndicated text (see test_provenance_verification.py for
    # that side of the behavior).
    texts = [
        "The company shipped a public integration with a payments provider.",
        "A separate report covers the company's expansion into a new distribution channel.",
        "Reviewers independently highlighted a redesigned onboarding flow in a recent release.",
    ]
    claims = tuple(
        _claim(f"t-{i}", SourceType.INDEPENDENT_REPORTING, f"group-{i}", text=texts[i]) for i in range(3)
    )
    reason = check("SUBSTANTIAL", claims)
    expect(reason is None, f"3 genuinely distinct facts should satisfy a minimum of 3, got: {reason}")


def test_extraction_rejects_artifact_observed_with_no_citations() -> None:
    evidence, independent, _ = _evidence()
    request = ExtractionRequest(dimension="product_existence_maturity", evidence_items=())
    response = ExtractionResponse(artifact_observed=True, supporting_claim_ids=())
    violations = validate_extraction(response, evidence)
    expect(len(violations) == 1, f"Expected one violation for an uncited positive extraction, got {violations}")


def test_extraction_rejects_citation_of_inadmissible_claim() -> None:
    evidence, _, _ = _evidence()
    response = ExtractionResponse(artifact_observed=True, supporting_claim_ids=("not-a-real-claim-id",))
    violations = validate_extraction(response, evidence)
    expect(len(violations) == 1, f"Expected one violation, got {violations}")


def test_negative_extraction_with_stray_citations_is_rejected() -> None:
    evidence, independent, _ = _evidence()
    response = ExtractionResponse(artifact_observed=False, supporting_claim_ids=(independent.claim_id,))
    violations = validate_extraction(response, evidence)
    expect(len(violations) == 1, "artifact_observed=False must not carry any supporting_claim_ids")


def test_company_identity_is_redacted_before_reaching_a_classification_request() -> None:
    text = "Acme Corp announced that Acme Corp's product now supports a new integration."
    redacted = redact_company_identity(text, ("Acme Corp",))
    expect("Acme Corp" not in redacted, f"Company name must be fully redacted, got: {redacted!r}")
    expect(redacted.count("[THE SUBJECT COMPANY]") == 2, f"Both occurrences must be replaced, got: {redacted!r}")


TESTS = [
    test_invalid_label_is_rejected,
    test_citation_of_nonexistent_claim_is_rejected,
    test_citation_of_inadmissible_claim_is_rejected,
    test_label_exceeding_cited_evidence_is_rejected,
    test_label_backed_by_real_independent_citation_is_accepted,
    test_minimum_distinct_facts_requirement_rejects_a_single_cited_group,
    test_minimum_distinct_facts_requirement_accepts_enough_distinct_groups,
    test_extraction_rejects_artifact_observed_with_no_citations,
    test_extraction_rejects_citation_of_inadmissible_claim,
    test_negative_extraction_with_stray_citations_is_rejected,
    test_company_identity_is_redacted_before_reaching_a_classification_request,
]


def main() -> None:
    print("\nVentureGPS Evidence Engine -- AI classification interface tests")
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
