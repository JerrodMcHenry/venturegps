"""Pure tests: the financing-candidate vocabulary. Exact money, explicit semantics, unknown stays unknown."""

import inspect
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.v2.domain import financing
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.errors import DomainError, InvalidInputError
from app.v2.domain.financing import (
    CURRENCY_MINOR_UNIT_EXPONENTS,
    AmountSemantics,
    FinancingDateKind,
    FinancingEventCandidateProposal,
    FinancingType,
    Money,
    ProposedAmount,
    ProposedFinancingDate,
    ProposedFinancingType,
    ProposedStage,
    Stage,
    StoredFinancingEventCandidate,
)
from app.v2.domain.time import EventTime, EventTimePrecision
from app.v2.observations.hashing import compute_content_hash

COMPANY = uuid.UUID("00000000-0000-0000-0000-000000000001")
LOC = EvidenceLocator(byte_start=0, byte_end=5, evidence_hash=compute_content_hash(b"hello"))


# ---------------- vocabulary

def test_vocabularies_are_explicit_and_include_unknown():
    assert [s.value for s in Stage] == ["pre_seed", "seed", "series_a", "series_b", "growth", "unknown"]
    assert [t.value for t in FinancingType] == ["equity", "convertible", "debt", "other", "unknown"]
    assert [s.value for s in AmountSemantics] == ["offering_amount", "amount_sold", "announced_round_amount"]
    assert [k.value for k in FinancingDateKind] == ["first_sale_date", "filing_date", "announcement_date"]


def test_there_is_no_verified_generic_or_funding_amount_and_no_event_date_anywhere():
    surface = " ".join(list(FinancingEventCandidateProposal.model_fields) + list(ProposedAmount.model_fields)
                       + list(ProposedFinancingDate.model_fields) + list(StoredFinancingEventCandidate.model_fields)
                       + [m.value for m in AmountSemantics] + [k.value for k in FinancingDateKind])
    for word in ("verified", "funding", "event_date", "confidence", "score", "model", "provider", "prompt", "venture"):
        assert word not in surface, word
    assert "amount" not in FinancingEventCandidateProposal.model_fields          # only semantic amounts exist
    assert not any("float" in str(f.annotation) for c in (Money, ProposedAmount, FinancingEventCandidateProposal) for f in c.model_fields.values())


def test_a_stored_candidate_is_explicitly_untrusted():
    assert StoredFinancingEventCandidate.TRUST_LEVEL == "untrusted_proposal"


# ---------------- exact money

@pytest.mark.parametrize("amount, currency, minor", [
    ("10000000", "USD", 1_000_000_000), (Decimal("7000000.50"), "USD", 700_000_050), (20_000_000, "EUR", 2_000_000_000),
    ("0", "USD", 0), ("5000", "JPY", 5000), ("0.01", "GBP", 1), ("92233720368547758.07", "USD", 2**63 - 1),
])
def test_money_is_exact_integer_minor_units(amount, currency, minor):
    money = Money.from_decimal(amount, currency)
    assert (money.currency_code, money.minor_units) == (currency, minor) and type(money.minor_units) is int


@pytest.mark.parametrize("bad", [0.1, 1e6, float("nan"), True, None, [], b"5", "1e2000000", "NaN", "Infinity", "-5", "", "five", "0.001"])
def test_floats_bools_and_sub_minor_unit_amounts_are_refused_not_rounded(bad):
    with pytest.raises(InvalidInputError):
        Money.from_decimal(bad, "USD")


def test_a_fraction_of_a_yen_is_refused_and_money_beyond_bigint_is_refused():
    with pytest.raises(InvalidInputError):
        Money.from_decimal("1.5", "JPY")
    with pytest.raises(InvalidInputError):
        Money.from_decimal("92233720368547758.08", "USD")
    with pytest.raises(ValidationError):
        Money(currency_code="USD", minor_units=2**63)


def test_the_currency_is_always_explicit_never_assumed_and_never_converted():
    with pytest.raises(ValidationError):
        Money(minor_units=100)                                                    # no default currency
    for bad in ("usd", "US", "USDX", "XXX", "", None, "BTC"):
        with pytest.raises((InvalidInputError, ValidationError)):
            Money.from_decimal("1", bad)
    assert Money.from_decimal("1", "USD") != Money.from_decimal("1", "EUR")       # equal numbers, different currencies
    assert not hasattr(financing, "convert") and not any("fx" in n.lower() or "rate" in n.lower() for n in dir(financing))
    assert CURRENCY_MINOR_UNIT_EXPONENTS["JPY"] == 0 and CURRENCY_MINOR_UNIT_EXPONENTS["USD"] == 2


# ---------------- unknown stays unknown

def test_unknown_stage_and_type_are_expressed_by_absence_and_cannot_be_proposed_with_evidence():
    proposal = FinancingEventCandidateProposal(company_id=COMPANY, event_evidence=LOC)
    assert proposal.stage is None and proposal.stage_value is Stage.UNKNOWN
    assert proposal.financing_type is None and proposal.financing_type_value is FinancingType.UNKNOWN
    with pytest.raises(InvalidInputError):
        ProposedStage(stage=Stage.UNKNOWN, evidence=LOC)
    with pytest.raises(InvalidInputError):
        ProposedFinancingType(financing_type=FinancingType.UNKNOWN, evidence=LOC)


def test_an_amount_never_implies_a_stage_or_a_type():
    for cents in ("50000", "2000000", "20000000", "900000000"):
        proposal = FinancingEventCandidateProposal(
            company_id=COMPANY, event_evidence=LOC,
            amounts=(ProposedAmount(semantics=AmountSemantics.ANNOUNCED_ROUND_AMOUNT, money=Money.from_decimal(cents, "USD"), evidence=LOC),))
        assert proposal.stage_value is Stage.UNKNOWN and proposal.financing_type_value is FinancingType.UNKNOWN
    assert not [n for n, f in inspect.getmembers(financing, inspect.isfunction) if "infer" in n or "guess" in n]


@pytest.mark.parametrize("value", ["series_c", "SEED", "", None, "unknown ", 5])
def test_unsupported_stage_values_are_rejected(value):
    with pytest.raises((ValidationError, ValueError)):
        ProposedStage(stage=value, evidence=LOC)


@pytest.mark.parametrize("value", ["revenue_based", "EQUITY", "", None])
def test_unsupported_financing_types_are_rejected(value):
    with pytest.raises((ValidationError, ValueError)):
        ProposedFinancingType(financing_type=value, evidence=LOC)


# ---------------- proposal shape

def test_the_company_is_a_canonical_id_and_never_a_name_or_url():
    for bad in ("Acme Robotics", "acmerobotics.com", "https://acme.example", 5, None):
        with pytest.raises(ValidationError):
            FinancingEventCandidateProposal(company_id=bad, event_evidence=LOC)
    assert not {"company_name", "name", "domain", "url", "website"} & set(FinancingEventCandidateProposal.model_fields)


def test_event_level_evidence_is_required():
    with pytest.raises(ValidationError):
        FinancingEventCandidateProposal(company_id=COMPANY)
    with pytest.raises(ValidationError):
        FinancingEventCandidateProposal(company_id=COMPANY, event_evidence=None)


def test_each_amount_semantics_and_date_kind_appears_at_most_once():
    a = ProposedAmount(semantics=AmountSemantics.AMOUNT_SOLD, money=Money.from_decimal("1", "USD"), evidence=LOC)
    with pytest.raises(InvalidInputError):
        FinancingEventCandidateProposal(company_id=COMPANY, event_evidence=LOC, amounts=(a, a))
    d = ProposedFinancingDate(kind=FinancingDateKind.FILING_DATE, time=EventTime.of_day(2026, 1, 2), evidence=LOC)
    with pytest.raises(InvalidInputError):
        FinancingEventCandidateProposal(company_id=COMPANY, event_evidence=LOC, dates=(d, d))


def test_offering_and_sold_are_simultaneously_representable_and_stay_distinct():
    offered = ProposedAmount(semantics=AmountSemantics.OFFERING_AMOUNT, money=Money.from_decimal("10000000", "USD"), evidence=LOC)
    sold = ProposedAmount(semantics=AmountSemantics.AMOUNT_SOLD, money=Money.from_decimal("7000000", "USD"), evidence=LOC)
    proposal = FinancingEventCandidateProposal(company_id=COMPANY, event_evidence=LOC, amounts=(offered, sold))
    by_semantics = {a.semantics: a.money.minor_units for a in proposal.amounts}
    assert by_semantics == {AmountSemantics.OFFERING_AMOUNT: 1_000_000_000, AmountSemantics.AMOUNT_SOLD: 700_000_000}


def test_a_proposal_rejects_confidence_and_other_unknown_fields():
    for extra in ("confidence", "model", "verified_round_amount", "funding_amount", "event_date", "amount"):
        with pytest.raises(ValidationError):
            FinancingEventCandidateProposal(company_id=COMPANY, event_evidence=LOC, **{extra: 1})


# ---------------- dates keep their precision

def test_dates_keep_the_precision_the_source_gave_and_are_never_collapsed():
    year = ProposedFinancingDate(kind=FinancingDateKind.FIRST_SALE_DATE, time=EventTime.of_year(2026), evidence=LOC)
    month = ProposedFinancingDate(kind=FinancingDateKind.ANNOUNCEMENT_DATE, time=EventTime.of_month(2026, 3), evidence=LOC)
    day = ProposedFinancingDate(kind=FinancingDateKind.FILING_DATE, time=EventTime.of_day(2026, 4, 2), evidence=LOC)
    assert (year.time.precision, month.time.precision, day.time.precision) == (
        EventTimePrecision.YEAR, EventTimePrecision.MONTH, EventTimePrecision.DAY)
    assert not year.time.is_exact and not month.time.is_exact                    # a year is not "Jan 1", a month is not "the 1st"
    with pytest.raises(DomainError):
        EventTime(precision=EventTimePrecision.YEAR, start=EventTime.of_month(2026, 3).start)   # cannot overclaim a March
