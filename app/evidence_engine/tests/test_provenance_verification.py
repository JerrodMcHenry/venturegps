"""
Task 10, item 1 -- evidence-independence verification
(app.evidence_engine.provenance), tested directly, plus its end-to-end
effect on Technical Depth Signal's SUBSTANTIAL threshold and dimension
Confidence: two claims declared under DIFFERENT `independence_group_id`s
must still be folded together when their content/provenance reveals them
to be the same underlying disclosure (a syndicated restatement, a copied
press release) -- the specific gap flagged in
NEW_ENGINE_CALIBRATION_REPORT.md Part 9 (Task 9) as unverified.

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_provenance_verification
"""

from __future__ import annotations

from datetime import date

from app.evidence_engine import parameters as P
from app.evidence_engine.classification import requires_minimum_distinct_facts
from app.evidence_engine.confidence import compute_dimension_confidence
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim, SourceType, SupportStatus
from app.evidence_engine.pillars.product_technology import (
    DIMENSION_TECHNICAL_DEPTH,
    evaluate_technical_depth_signal,
)
from app.evidence_engine.provenance import IndependenceVerdict, assess_independence, verify_independence
from app.evidence_engine.scoring import AvailabilityStatus, ConfidenceLevel
from app.evidence_engine.stage import Stage

AS_OF = date(2026, 9, 27)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _tech_claim(claim_id: str, group: str, publisher: str, text: str, url: str | None = None) -> Claim:
    return Claim(
        claim_id=claim_id, company_ref="prov_co", claim_text=text, subject_entity="prov_co",
        source_publisher=publisher, source_type=SourceType.INDEPENDENT_REPORTING, retrieved_at=AS_OF,
        support_status=SupportStatus.DIRECTLY_SUPPORTED, excerpt=text, source_url=url,
        assessment_criteria=[DIMENSION_TECHNICAL_DEPTH], independence_group_id=group,
    )


# --- Pairwise verdicts --------------------------------------------------------

def test_identical_source_url_with_dissimilar_text_is_independent() -> None:
    # Task 12, item 1 (reversed from the prior behavior this test used to
    # assert): a shared source_url is NOT evidence of duplication on its
    # own -- a single reference page can and does state multiple distinct
    # facts (Notion's own integrations page is the real example that
    # exposed this, NEW_ENGINE_LIVE_EVALUATION.md §4.1). Claim identity is
    # decided by content, never by which page the claims happen to share.
    a = _tech_claim("a", "g1", "Outlet A", "The company announced a new integration with Acme.", url="https://example.com/story")
    b = _tech_claim("b", "g2", "Outlet B", "A wholly different sentence describing something else entirely.", url="https://example.com/story")
    verdict = assess_independence(a, b)
    expect(
        verdict == IndependenceVerdict.INDEPENDENT,
        f"Identical source_url with genuinely dissimilar text must be INDEPENDENT, got {verdict}",
    )


def test_identical_source_url_with_near_identical_text_is_still_a_duplicate() -> None:
    # The legitimate case a shared URL usually DOES indicate (the same
    # restated sentence, re-scraped) is still caught correctly -- by text
    # similarity alone, with no need for the URL check that used to (and
    # no longer does) short-circuit this decision.
    a = _tech_claim("a", "g1", "Outlet A", "The company announced a new integration with a payments provider.", url="https://example.com/story")
    b = _tech_claim("b", "g2", "Outlet B", "The company announced a new integration with a payments provider!", url="https://example.com/story")
    verdict = assess_independence(a, b)
    expect(
        verdict == IndependenceVerdict.LIKELY_DUPLICATE,
        f"Identical source_url with near-identical text must still be LIKELY_DUPLICATE (via text similarity alone), got {verdict}",
    )


def test_near_identical_text_is_a_likely_duplicate() -> None:
    a = _tech_claim("a", "g1", "Outlet A", "The company today announced a new integration with a major payments provider.")
    b = _tech_claim("b", "g2", "Outlet B", "The company today announced a new integration with a major payments provider!")
    verdict = assess_independence(a, b)
    expect(verdict == IndependenceVerdict.LIKELY_DUPLICATE, f"Near-identical text (wire syndication) must be LIKELY_DUPLICATE, got {verdict}")


def test_moderately_similar_text_is_unknown_not_independent_or_duplicate() -> None:
    a = _tech_claim("a", "g1", "Outlet A", "The company announced a new integration with a payments provider this week.")
    b = _tech_claim("b", "g2", "Outlet B", "This week the company revealed a payments provider integration in its product.")
    verdict = assess_independence(a, b)
    expect(
        verdict == IndependenceVerdict.UNKNOWN,
        f"Moderately overlapping text must be UNKNOWN (per Task 10's own instruction), got {verdict}",
    )


def test_dissimilar_text_from_different_publishers_is_independent() -> None:
    a = _tech_claim("a", "g1", "Outlet A", "The company shipped a public API for third-party developers.")
    b = _tech_claim("b", "g2", "Outlet B", "Reviewers praised the redesigned onboarding checklist in the mobile app.")
    verdict = assess_independence(a, b)
    expect(verdict == IndependenceVerdict.INDEPENDENT, f"Genuinely distinct facts must be INDEPENDENT, got {verdict}")


# --- Clustering (verify_independence) -----------------------------------------

def test_verify_independence_folds_a_syndicated_restatement_under_a_different_declared_group() -> None:
    # THE core Task 10 scenario: three claims tagged for Technical Depth
    # Signal, each given a DIFFERENT independence_group_id upstream (so
    # ledger-level dedup by declared group does NOT collapse them) -- but
    # two of the three are near-identical text (a wire-syndicated
    # restatement mistakenly given its own group id). Provenance
    # verification must still fold them together.
    original = _tech_claim("orig", "group-A", "Outlet A", "The company today announced a new integration with a major CRM provider.")
    restatement = _tech_claim("restatement", "group-B", "Outlet B (wire syndication)", "The company today announced a new integration with a major CRM provider!")
    genuinely_distinct = _tech_claim("distinct", "group-C", "Outlet C", "Independent reviewers highlighted a substantial redesign of the mobile onboarding flow.")

    result = verify_independence((original, restatement, genuinely_distinct))
    expect(
        len(result.confirmed_independent) == 2,
        f"Expected 2 confirmed-distinct facts (orig+restatement folded, distinct counted separately), "
        f"got {len(result.confirmed_independent)}: {[c.claim_id for c in result.confirmed_independent]}",
    )
    expect(
        restatement in result.folded_duplicates,
        "The syndicated restatement must be folded as a duplicate despite its own distinct independence_group_id",
    )


def test_unknown_independence_claims_are_not_counted_as_distinct() -> None:
    a = _tech_claim("a", "g1", "Outlet A", "The company announced a new integration with a payments provider this week.")
    b = _tech_claim("b", "g2", "Outlet B", "This week the company revealed a payments provider integration in its product.")
    result = verify_independence((a, b))
    expect(len(result.confirmed_independent) == 1, "The first claim seeds the confirmed set")
    expect(b in result.unknown_independence, "The second, ambiguously-similar claim must be UNKNOWN, not confirmed-independent")
    expect(len(result.folded_duplicates) == 0, "UNKNOWN is a distinct outcome from a confirmed duplicate")


def test_verification_never_increases_the_declared_distinct_count() -> None:
    # Verification can only fold groups together (or mark them Unknown) --
    # it must never invent MORE distinct facts than the number of claims
    # actually supplied.
    claims = tuple(
        _tech_claim(f"c{i}", f"group-{i}", f"Outlet {i}", f"Distinct sentence number {i} about a different topic entirely.")
        for i in range(4)
    )
    result = verify_independence(claims)
    expect(
        len(result.confirmed_independent) <= len(claims),
        "Verified distinct count can never exceed the number of input claims",
    )


# --- End-to-end: Technical Depth Signal + Confidence --------------------------

def test_technical_depth_does_not_reach_substantial_via_a_wrongly_split_duplicate() -> None:
    # Three claims cited by the (naive, group-id-trusting) well-behaved
    # classifier as three distinct facts -- but two are actually a
    # syndicated restatement mistakenly given a different group id. The
    # deterministic validator (now provenance-aware) must catch this and
    # reject SUBSTANTIAL, even though the classifier itself "believed" 3.
    ledger = EvidenceLedger.from_list(
        [
            _tech_claim("td-orig", "group-A", "Outlet A", "The company today announced a new integration with a major CRM provider."),
            _tech_claim("td-restated", "group-B", "Outlet B (wire syndication)", "The company today announced a new integration with a major CRM provider!"),
            _tech_claim("td-distinct", "group-C", "Outlet C", "Independent reviewers highlighted a substantial redesign of the mobile onboarding flow."),
        ]
    )
    result = evaluate_technical_depth_signal(ledger, "prov_co", AS_OF, Stage.UNDETERMINED)
    expect(
        result.classification_label != "SUBSTANTIAL",
        f"A provenance-verified 2-distinct-fact case must not reach SUBSTANTIAL, got {result.classification_label}",
    )
    # The naive classifier's own proposal (SUBSTANTIAL, all 3 cited) fails
    # validation on both attempts (retry does not fix a static/naive
    # classifier's belief -- see test_classification_recovery.py for the
    # case where a model DOES correct itself), so this dimension fails
    # closed to Unscored rather than silently downgrading to SOME on its
    # own.
    expect(result.score is None, "A rejected SUBSTANTIAL proposal must not silently become a different score")
    expect(result.availability == AvailabilityStatus.UNSCORED_EXTRACTION_FAILED, result.availability.value)


def test_technical_depth_reaches_substantial_when_distinct_facts_share_one_source_url() -> None:
    # Task 12, item 1's own explicit regression case: reproduces
    # NEW_ENGINE_LIVE_EVALUATION.md §4.1 exactly -- three genuinely
    # distinct technical facts, two of which (as in Notion's real
    # integrations page) happen to be documented at the SAME source_url.
    # Before the fix, the shared URL alone forced a LIKELY_DUPLICATE
    # verdict regardless of content, incorrectly capping this at 2
    # distinct facts and rejecting SUBSTANTIAL. After the fix, only
    # content similarity decides distinctness -- these three, being
    # genuinely different facts, must all count.
    shared_url = "https://example.com/product/integrations"
    ledger = EvidenceLedger.from_list(
        [
            _tech_claim("api-fact", "group-api", "Product docs", "The product publishes a public API for building integrations.", url=shared_url),
            _tech_claim("gallery-fact", "group-gallery", "Product docs", "The integration gallery lists Jira, Google Drive, and Slack among supported tools.", url=shared_url),
            _tech_claim("independent-fact", "group-independent", "Independent outlet", "Independent reporting confirms the product's AI features can read connected chat and file services.", url="https://independent-outlet.example.com/review"),
        ]
    )
    result = evaluate_technical_depth_signal(ledger, "prov_co", AS_OF, Stage.UNDETERMINED)
    expect(
        result.classification_label == "SUBSTANTIAL",
        f"Three genuinely distinct facts (two sharing one source_url) must reach SUBSTANTIAL, got "
        f"{result.classification_label} ({result.rationale})",
    )
    expect(result.score is not None, "A correctly-reached SUBSTANTIAL must score, not fail closed")
    expect(len(result.supporting_claim_ids) == 3, f"All three distinct facts must be cited, got {result.supporting_claim_ids}")


def test_confidence_corroboration_uses_verified_not_declared_distinct_count() -> None:
    # Two claims declared under different groups but near-identical text
    # must not count as 2 corroborating events for Confidence purposes.
    original = _tech_claim("c-orig", "group-A", "Outlet A", "The company disclosed a new enterprise customer this quarter.")
    restatement = _tech_claim("c-restated", "group-B", "Outlet B (wire syndication)", "The company disclosed a new enterprise customer this quarter!")
    naive_group_count = len({c.independence_group_id for c in (original, restatement)})
    expect(naive_group_count == 2, "Test setup: the two claims must have different declared groups")

    confidence = compute_dimension_confidence((original, restatement))
    # With only 1 verified distinct fact (not 2), this must not reach the
    # HIGH bar's corroboration requirement (>=2 verified distinct groups).
    expect(
        confidence != ConfidenceLevel.HIGH,
        "Confidence must not reach HIGH on the strength of a syndicated restatement miscounted as second corroboration",
    )


TESTS = [
    test_identical_source_url_with_dissimilar_text_is_independent,
    test_identical_source_url_with_near_identical_text_is_still_a_duplicate,
    test_near_identical_text_is_a_likely_duplicate,
    test_moderately_similar_text_is_unknown_not_independent_or_duplicate,
    test_dissimilar_text_from_different_publishers_is_independent,
    test_verify_independence_folds_a_syndicated_restatement_under_a_different_declared_group,
    test_unknown_independence_claims_are_not_counted_as_distinct,
    test_verification_never_increases_the_declared_distinct_count,
    test_technical_depth_does_not_reach_substantial_via_a_wrongly_split_duplicate,
    test_technical_depth_reaches_substantial_when_distinct_facts_share_one_source_url,
    test_confidence_corroboration_uses_verified_not_declared_distinct_count,
]


def main() -> None:
    print("\nVentureGPS Evidence Engine -- evidence-independence verification tests")
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
