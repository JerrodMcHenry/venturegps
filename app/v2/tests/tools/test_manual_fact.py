"""manual_fact.py: human-guided (not automated) location of a fact's evidence in a second document. Increment
18.2's own required coverage: evidence locator integrity, absent/ambiguous information, conflicting dates."""

from pathlib import Path

import pytest

from app.v2.domain.financing import AmountSemantics, FinancingDateKind
from app.v2.tools.manual_fact import FactNotFoundError, build_manual_amount, build_manual_date, count_occurrences, locate_evidence

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
SNIPPET = (FIXTURE_DIR / "synthetic_announcement_snippet.html").read_bytes()
HEADLINE = "Example Robotics Co. raises $42M Series B"


def test_counts_the_real_repeated_occurrences():
    assert count_occurrences(SNIPPET, HEADLINE) == 4


def test_locates_a_specific_named_occurrence_correctly():
    for occurrence in range(4):
        locator = locate_evidence(SNIPPET, HEADLINE, occurrence=occurrence)
        assert SNIPPET[locator.byte_start:locator.byte_end].decode("utf-8") == HEADLINE


def test_an_out_of_range_occurrence_is_refused_not_wrapped_or_clamped():
    with pytest.raises(FactNotFoundError):
        locate_evidence(SNIPPET, HEADLINE, occurrence=4)  # only 0-3 exist


def test_a_substring_that_does_not_appear_at_all_is_refused():
    with pytest.raises(FactNotFoundError):
        locate_evidence(SNIPPET, "this text is not in the document", occurrence=0)


def test_an_empty_substring_is_refused_not_matched_everywhere():
    with pytest.raises(FactNotFoundError):
        locate_evidence(SNIPPET, "", occurrence=0)


def test_build_manual_amount_produces_the_exact_stated_amount():
    amount = build_manual_amount(
        SNIPPET, semantics=AmountSemantics.ANNOUNCED_ROUND_AMOUNT, amount="42000000", currency_code="USD",
        evidence_substring=HEADLINE, occurrence=0,
    )
    assert amount.semantics is AmountSemantics.ANNOUNCED_ROUND_AMOUNT
    assert amount.money.currency_code == "USD"
    assert amount.money.minor_units == 42_000_000_00
    assert SNIPPET[amount.evidence.byte_start:amount.evidence.byte_end].decode("utf-8") == HEADLINE


def test_build_manual_amount_never_fabricates_evidence_the_locator_always_cites_real_bytes():
    """The amount VALUE the human supplies ("42000000") never needs to look like the cited text ("$42M") --
    this proves the resulting EvidenceLocator still points at genuinely present bytes, not a synthesized span."""
    amount = build_manual_amount(
        SNIPPET, semantics=AmountSemantics.ANNOUNCED_ROUND_AMOUNT, amount="42000000", currency_code="USD",
        evidence_substring="$42M", occurrence=0,
    )
    cited = SNIPPET[amount.evidence.byte_start:amount.evidence.byte_end]
    assert cited == b"$42M"


def test_build_manual_date_produces_day_precision_from_the_cited_text():
    date = build_manual_date(SNIPPET, kind=FinancingDateKind.ANNOUNCEMENT_DATE, iso_date="2025-07-01", evidence_substring="2025-07-01")
    assert date.kind is FinancingDateKind.ANNOUNCEMENT_DATE
    assert date.time.start.isoformat() == "2025-07-01T00:00:00+00:00"
    assert SNIPPET[date.evidence.byte_start:date.evidence.byte_end].decode("utf-8") == "2025-07-01"


def test_build_manual_date_rejects_a_malformed_date():
    with pytest.raises(FactNotFoundError):
        build_manual_date(SNIPPET, kind=FinancingDateKind.ANNOUNCEMENT_DATE, iso_date="not-a-date", evidence_substring="2025-07-01")


def test_two_manual_amounts_for_different_semantics_never_collapse():
    """Conflicting/complementary amounts (Increment 18.2's required "conflicting amounts" case, at the fact-
    building layer): announced_round_amount and, hypothetically, a differently-sourced amount are built
    independently and never merged into one value."""
    announced = build_manual_amount(SNIPPET, semantics=AmountSemantics.ANNOUNCED_ROUND_AMOUNT, amount="42000000",
                                    currency_code="USD", evidence_substring=HEADLINE, occurrence=0)
    offering = build_manual_amount(SNIPPET, semantics=AmountSemantics.OFFERING_AMOUNT, amount="45000000",
                                   currency_code="USD", evidence_substring=HEADLINE, occurrence=1)
    assert announced.semantics != offering.semantics
    assert announced.money.minor_units != offering.money.minor_units
    assert announced.evidence.byte_start != offering.evidence.byte_start  # different occurrences, genuinely different spans
