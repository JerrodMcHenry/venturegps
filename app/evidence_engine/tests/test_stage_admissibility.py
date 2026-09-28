"""
Task 12, item 2 -- stage determination now routes through the exact same
admissibility check (ledger.resolve_dimension_evidence) every scored
dimension already uses: a disputed or stale stage-signal claim is
excluded before `determine_stage()` ever reads its `structured_fact`,
closing the real gap NEW_ENGINE_LIVE_EVALUATION.md §5.3 found (stage
determination previously read raw claims directly, with no
dispute/staleness awareness at all). Also covers the expanded
round-type keyword recognition (tender offers, YC cohort identifiers)
and reconfirms insufficient evidence still resolves to Undetermined,
never a guess.

No real LLM call anywhere in this file.

Run with:
    python -m app.evidence_engine.tests.test_stage_admissibility
"""

from __future__ import annotations

from datetime import date, timedelta

from app.evidence_engine import parameters as P
from app.evidence_engine.ledger import EvidenceLedger
from app.evidence_engine.models import Claim, SourceType, SupportStatus
from app.evidence_engine.stage import STAGE_SIGNAL_DIMENSION, Stage, determine_stage

AS_OF = date(2026, 9, 27)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _stage_claim(
    claim_id: str, company_ref: str, value: str, support_status: SupportStatus = SupportStatus.DIRECTLY_SUPPORTED,
    published_at: date = AS_OF, contradicts: list[str] | None = None,
) -> Claim:
    return Claim(
        claim_id=claim_id, company_ref=company_ref, claim_text=f"stage signal: {value}",
        subject_entity=company_ref, source_publisher="a source", source_type=SourceType.INDEPENDENT_REPORTING,
        retrieved_at=AS_OF, published_at=published_at, support_status=support_status,
        excerpt=f"stage signal: {value}" if support_status != SupportStatus.DISPUTED else None,
        assessment_criteria=[STAGE_SIGNAL_DIMENSION], independence_group_id=claim_id,
        structured_fact={"kind": "funding_round_type", "value": value},
        contradicts=contradicts or [],
    )


# --- Disputed/stale stage signals must not decide the stage -----------------

def test_a_disputed_stage_signal_alone_resolves_to_undetermined() -> None:
    # Unlike Notion's real case (where two disputed claims happened to
    # agree on the round TYPE, only disagreeing on date), this constructs
    # the harder case the old code could get wrong: two disputed claims
    # that disagree on the round type itself. With no other admissible
    # signal, this must resolve to Undetermined, never silently pick
    # whichever disputed claim has the later published_at.
    claims = [
        _stage_claim("s1", "co", "Series A", support_status=SupportStatus.DISPUTED, published_at=date(2024, 1, 1), contradicts=["s2"]),
        _stage_claim("s2", "co", "Series C", support_status=SupportStatus.DISPUTED, published_at=date(2026, 1, 1), contradicts=["s1"]),
    ]
    stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
    expect(
        stage == Stage.UNDETERMINED,
        f"Two disputed, conflicting stage signals with nothing else admissible must resolve to Undetermined, got {stage}",
    )


def test_a_non_disputed_signal_wins_over_a_disputed_one() -> None:
    claims = [
        _stage_claim("s1", "co", "Series A", support_status=SupportStatus.DISPUTED, published_at=date(2026, 1, 1), contradicts=["s2"]),
        _stage_claim("s2", "co", "Series C", support_status=SupportStatus.DIRECTLY_SUPPORTED, published_at=date(2024, 1, 1)),
    ]
    stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
    expect(
        stage == Stage.SERIES_B_PLUS,
        f"The one non-disputed signal (Series C) must be used, ignoring the disputed one entirely, got {stage}",
    )


def test_a_stale_stage_signal_is_excluded() -> None:
    stale_date = AS_OF - timedelta(days=P.STAGE_SIGNAL_STALENESS_DAYS + 30)
    claims = [_stage_claim("s1", "co", "Series A", published_at=stale_date)]
    stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
    expect(
        stage == Stage.UNDETERMINED,
        f"A stage signal older than STAGE_SIGNAL_STALENESS_DAYS must be excluded, got {stage}",
    )


def test_a_fresh_signal_is_used_even_when_an_older_one_exists() -> None:
    stale_date = AS_OF - timedelta(days=P.STAGE_SIGNAL_STALENESS_DAYS + 30)
    claims = [
        _stage_claim("s1", "co", "Series A", published_at=stale_date),
        _stage_claim("s2", "co", "Series C", published_at=date(2026, 1, 1)),
    ]
    stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
    expect(stage == Stage.SERIES_B_PLUS, f"The fresh signal must be used once the stale one is excluded, got {stage}")


# --- Expanded keyword recognition (real terms Task 11 found unrecognized) --

def test_tender_offer_is_recognized_as_a_growth_stage_signal() -> None:
    claims = [_stage_claim("s1", "co", "tender offer")]
    stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
    expect(stage == Stage.GROWTH, f"'tender offer' must now map to Growth, got {stage}")


def test_yc_batch_codes_are_recognized_as_pre_seed() -> None:
    for value in ("YC S26", "YC W26", "Y Combinator"):
        claims = [_stage_claim("s1", "co", value)]
        stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
        expect(stage == Stage.PRE_SEED, f"{value!r} must map to Pre-Seed, got {stage}")


def test_yc_keyword_does_not_false_positive_on_unrelated_text() -> None:
    # A basic collision sanity-check for the new short "yc s"/"yc w"
    # keywords -- must not fire on ordinary text that happens to contain
    # similar letter sequences.
    claims = [_stage_claim("s1", "co", "a policy sets new industry standards")]
    stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
    expect(
        stage == Stage.UNDETERMINED,
        f"Unrelated text must not false-positive-match a YC keyword, got {stage}",
    )


# --- Insufficient evidence must never be guessed -----------------------------

def test_zero_stage_signal_claims_resolves_to_undetermined() -> None:
    stage = determine_stage(EvidenceLedger.from_list([]), "co", AS_OF)
    expect(stage == Stage.UNDETERMINED, f"Zero evidence must resolve to Undetermined, got {stage}")


def test_only_disputed_and_stale_claims_resolves_to_undetermined() -> None:
    stale_date = AS_OF - timedelta(days=P.STAGE_SIGNAL_STALENESS_DAYS + 30)
    claims = [
        _stage_claim("s1", "co", "Series A", published_at=stale_date),
        _stage_claim("s2", "co", "Series C", support_status=SupportStatus.DISPUTED, published_at=date(2026, 1, 1), contradicts=["s3"]),
        _stage_claim("s3", "co", "Seed", support_status=SupportStatus.DISPUTED, published_at=date(2026, 1, 1), contradicts=["s2"]),
    ]
    stage = determine_stage(EvidenceLedger.from_list(claims), "co", AS_OF)
    expect(
        stage == Stage.UNDETERMINED,
        f"A stale claim plus a disputed pair, with nothing admissible, must resolve to Undetermined, got {stage}",
    )


TESTS = [
    test_a_disputed_stage_signal_alone_resolves_to_undetermined,
    test_a_non_disputed_signal_wins_over_a_disputed_one,
    test_a_stale_stage_signal_is_excluded,
    test_a_fresh_signal_is_used_even_when_an_older_one_exists,
    test_tender_offer_is_recognized_as_a_growth_stage_signal,
    test_yc_batch_codes_are_recognized_as_pre_seed,
    test_yc_keyword_does_not_false_positive_on_unrelated_text,
    test_zero_stage_signal_claims_resolves_to_undetermined,
    test_only_disputed_and_stale_claims_resolves_to_undetermined,
]


def main() -> None:
    print("\nVentureGPS Evidence Engine -- stage admissibility tests")
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
