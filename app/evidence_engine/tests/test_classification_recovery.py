"""
Task 10, item 2 -- classification recovery: on a validation failure, the
model gets exactly one retry with the violations fed back as structured
`validation_feedback`. If the second response is still invalid, the
dimension fails closed to Unscored -- never a substituted score, never an
accepted unsupported evidence reference, on either attempt.

Every mock model here is a deliberately constructed test double
(read-the-feedback / ignore-the-feedback / still-cheats-on-retry) --
no real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_classification_recovery
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.evidence_engine.classification import (
    ClassificationRequest,
    ClassificationResponse,
    classify_with_recovery,
)
from app.evidence_engine.ledger import EvidenceLedger, resolve_dimension_evidence
from app.evidence_engine.models import Claim, SourceType, SupportStatus
from app.evidence_engine.pillars.product_technology import (
    DIMENSION_TECHNICAL_DEPTH,
    evaluate_technical_depth_signal,
)
from app.evidence_engine.scoring import AvailabilityStatus
from app.evidence_engine.stage import Stage

AS_OF = date(2026, 9, 27)
DIMENSION = DIMENSION_TECHNICAL_DEPTH


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _claim(claim_id: str, group: str, text: str, source_type: SourceType = SourceType.INDEPENDENT_REPORTING) -> Claim:
    return Claim(
        claim_id=claim_id, company_ref="recov_co", claim_text=text, subject_entity="recov_co",
        source_publisher="a source", source_type=source_type, retrieved_at=AS_OF,
        support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt=text,
        assessment_criteria=[DIMENSION], independence_group_id=group,
    )


# --- Test doubles -------------------------------------------------------------

@dataclass(frozen=True)
class ReadsFeedbackAndDropsFlaggedClaim:
    """First attempt: over-optimistically cites everything it was given.
    Second attempt: reads `validation_feedback` for the text this
    codebase's own rejection message uses to name a folded duplicate, and
    drops exactly that citation, falling back to a more conservative
    label with the remaining evidence."""

    optimistic_label: str
    fallback_label: str

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        if not request.validation_feedback:
            return ClassificationResponse(
                label=self.optimistic_label, supporting_claim_ids=tuple(e.claim_id for e in request.evidence_items)
            )
        feedback_text = " ".join(request.validation_feedback)
        remaining = tuple(
            e.claim_id for e in request.evidence_items if e.claim_id not in feedback_text
        )
        return ClassificationResponse(label=self.fallback_label, supporting_claim_ids=remaining)


@dataclass(frozen=True)
class IgnoresFeedbackAndRepeatsItself:
    """Never reads validation_feedback -- returns the exact same (invalid)
    response on both attempts. Models a static/non-self-correcting model."""

    label: str

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        return ClassificationResponse(label=self.label, supporting_claim_ids=tuple(e.claim_id for e in request.evidence_items))


@dataclass(frozen=True)
class CorrectsLabelButStillCitesAFabricatedClaim:
    """Simulates a model that DOES read feedback and change its label, but
    -- still incorrectly -- invents a citation on the retry. Proves
    recovery never relaxes evidence validation on the second attempt."""

    def classify(self, request: ClassificationRequest) -> ClassificationResponse:
        if not request.validation_feedback:
            return ClassificationResponse(label="SUBSTANTIAL", supporting_claim_ids=("fabricated-1", "fabricated-2", "fabricated-3"))
        return ClassificationResponse(label="SOME", supporting_claim_ids=("still-fabricated",))


# --- Fixture: 3 cited claims, 2 of which are a syndicated restatement --------

def _three_claims_two_are_duplicates() -> tuple[Claim, ...]:
    # Claim ids are deliberately chosen to share no substring with the
    # rejection-message wording itself (e.g. not "distinct", which is a
    # word the validator's own message text uses) -- ReadsFeedbackAndDrops
    # FlaggedClaim below identifies which citation to drop by substring
    # search over the feedback text, and a stray collision with the
    # message's own prose would make that test double silently misbehave.
    return (
        _claim("orig-001", "group-A", "The company today announced a new integration with a major CRM provider."),
        _claim("restated-002", "group-B", "The company today announced a new integration with a major CRM provider!"),
        _claim("genuine-003", "group-C", "Independent reviewers highlighted a substantial redesign of the onboarding flow."),
    )


def test_second_attempt_succeeds_when_the_model_reads_feedback_and_corrects() -> None:
    ledger = EvidenceLedger.from_list(_three_claims_two_are_duplicates())
    result = evaluate_technical_depth_signal(
        ledger, "recov_co", AS_OF, Stage.UNDETERMINED,
        model=ReadsFeedbackAndDropsFlaggedClaim(optimistic_label="SUBSTANTIAL", fallback_label="SOME"),
    )
    expect(result.availability == AvailabilityStatus.SCORABLE, f"Expected recovery to succeed, got {result.availability.value}: {result.rationale}")
    expect(result.classification_label == "SOME", f"Expected the corrected SOME label, got {result.classification_label}")
    expect("accepted on retry" in result.rationale, f"Rationale should disclose the retry, got: {result.rationale}")
    expect(
        len(result.supporting_claim_ids) == 2,
        f"Expected the 2 remaining (non-duplicate) claims cited, got {result.supporting_claim_ids}",
    )


def test_recovery_mechanism_directly_reports_attempts_and_recovered_flag() -> None:
    dimension_evidence = resolve_dimension_evidence(
        EvidenceLedger.from_list(_three_claims_two_are_duplicates()), DIMENSION, AS_OF, staleness_days=730
    )
    from app.evidence_engine.classification import requires_minimum_distinct_facts
    from app.evidence_engine import parameters as P
    from app.evidence_engine.classification import to_evidence_items

    request = ClassificationRequest(
        dimension=DIMENSION, allowed_labels=("NONE", "SOME", "SUBSTANTIAL"),
        evidence_items=to_evidence_items(dimension_evidence.admissible, ()),
    )
    outcome = classify_with_recovery(
        ReadsFeedbackAndDropsFlaggedClaim(optimistic_label="SUBSTANTIAL", fallback_label="SOME"),
        request, dimension_evidence,
        requires_minimum_distinct_facts({"SUBSTANTIAL": P.TECHNICAL_DEPTH_SUBSTANTIAL_MIN_FACTS, "SOME": 1}),
    )
    expect(outcome.attempts == 2, f"Expected exactly 2 attempts, got {outcome.attempts}")
    expect(outcome.recovered is True, "recovered must be True when attempt 1 failed and attempt 2 passed")
    expect(outcome.response is not None and outcome.response.label == "SOME", "Expected the corrected response")


def test_second_invalid_attempt_fails_closed_to_unscored() -> None:
    ledger = EvidenceLedger.from_list(_three_claims_two_are_duplicates())
    result = evaluate_technical_depth_signal(
        ledger, "recov_co", AS_OF, Stage.UNDETERMINED,
        model=IgnoresFeedbackAndRepeatsItself(label="SUBSTANTIAL"),
    )
    expect(result.score is None, "A model that repeats the same invalid response twice must not score")
    expect(
        result.availability == AvailabilityStatus.UNSCORED_EXTRACTION_FAILED,
        f"Expected UNSCORED_EXTRACTION_FAILED, got {result.availability.value}",
    )
    expect("after 2 attempt(s)" in result.rationale, f"Rationale must disclose both attempts failed, got: {result.rationale}")


def test_recovery_never_relaxes_citation_validation_on_the_second_attempt() -> None:
    ledger = EvidenceLedger.from_list(_three_claims_two_are_duplicates())
    result = evaluate_technical_depth_signal(
        ledger, "recov_co", AS_OF, Stage.UNDETERMINED,
        model=CorrectsLabelButStillCitesAFabricatedClaim(),
    )
    expect(result.score is None, "A fabricated citation on the retry must still be rejected -- never scored")
    expect(result.availability == AvailabilityStatus.UNSCORED_EXTRACTION_FAILED, result.availability.value)
    expect(result.classification_label is None, "An unvalidated label must never be echoed back as if it were accepted")


def test_a_model_that_is_correct_on_the_first_attempt_is_never_retried() -> None:
    # Sanity check on the mechanism's own cost discipline: recovery must
    # not add a needless second call when the first attempt already
    # passes validation.
    call_count = {"n": 0}

    @dataclass(frozen=True)
    class CountingCorrectModel:
        def classify(self, request: ClassificationRequest) -> ClassificationResponse:
            call_count["n"] += 1
            return ClassificationResponse(label="NONE", supporting_claim_ids=())

    ledger = EvidenceLedger.from_list([])
    result = evaluate_technical_depth_signal(ledger, "recov_co", AS_OF, Stage.UNDETERMINED, model=CountingCorrectModel())
    expect(call_count["n"] == 1, f"Expected exactly 1 call for an already-valid response, got {call_count['n']}")
    expect(result.availability == AvailabilityStatus.UNSCORED_NO_EVIDENCE, result.availability.value)


TESTS = [
    test_second_attempt_succeeds_when_the_model_reads_feedback_and_corrects,
    test_recovery_mechanism_directly_reports_attempts_and_recovered_flag,
    test_second_invalid_attempt_fails_closed_to_unscored,
    test_recovery_never_relaxes_citation_validation_on_the_second_attempt,
    test_a_model_that_is_correct_on_the_first_attempt_is_never_retried,
]


def main() -> None:
    print("\nVentureGPS Evidence Engine -- classification recovery tests")
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
