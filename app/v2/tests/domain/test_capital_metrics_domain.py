"""Pure tests: the Capital metric engine. No database, no network."""

import uuid
from datetime import datetime, timezone
from fractions import Fraction

import pytest
from pydantic import ValidationError

from app.v2.domain.capital_metrics import (
    METRIC_DATE_PRECEDENCE,
    CapitalConcentration,
    CapitalEventInput,
    CapitalMetricsDiagnostics,
    choose_metric_date,
    compute_capital_metrics,
)
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.financing import FinancingDateKind, Money, Stage
from app.v2.domain.time import EventTime

MARKET = uuid.uuid4()
TV = "venturegps_taxonomy.v1"


def dt(y, m=1, d=1):
    return datetime(y, m, d, tzinfo=timezone.utc)


def event(company=None, metric_date=None, kind=None, amount=None, stage=Stage.UNKNOWN):
    return CapitalEventInput(financing_event_id=uuid.uuid4(), company_id=company or uuid.uuid4(),
                             metric_date=metric_date, metric_date_kind=kind, verified_round_amount=amount, stage=stage)


def usd(v):
    return Money.from_decimal(v, "USD")


def run(events, start=dt(2026, 1, 1), end=dt(2027, 1, 1)):
    return compute_capital_metrics(events, market_id=MARKET, taxonomy_version=TV, period_start=start, period_end=end)


# ---------------- metric date policy

def test_precedence_is_announcement_then_first_sale_then_filing():
    assert METRIC_DATE_PRECEDENCE == (FinancingDateKind.ANNOUNCEMENT_DATE, FinancingDateKind.FIRST_SALE_DATE, FinancingDateKind.FILING_DATE)


def test_announcement_date_wins_when_present():
    dates = {FinancingDateKind.ANNOUNCEMENT_DATE: EventTime.of_day(2026, 3, 1), FinancingDateKind.FIRST_SALE_DATE: EventTime.of_day(2026, 2, 1)}
    kind, time = choose_metric_date(dates)
    assert kind is FinancingDateKind.ANNOUNCEMENT_DATE and time.start == dt(2026, 3, 1)


def test_first_sale_date_is_the_fallback_when_no_announcement():
    dates = {FinancingDateKind.FIRST_SALE_DATE: EventTime.of_day(2026, 2, 1), FinancingDateKind.FILING_DATE: EventTime.of_day(2026, 4, 1)}
    kind, _ = choose_metric_date(dates)
    assert kind is FinancingDateKind.FIRST_SALE_DATE


def test_filing_date_is_the_last_resort():
    kind, _ = choose_metric_date({FinancingDateKind.FILING_DATE: EventTime.of_day(2026, 4, 1)})
    assert kind is FinancingDateKind.FILING_DATE


def test_no_usable_date_returns_none_never_fabricated():
    assert choose_metric_date({}) is None


def test_observed_time_is_not_part_of_the_choice_at_all():
    # the pure engine's vocabulary has no concept of observed_time; only the three FinancingDateKind values exist
    assert set(FinancingDateKind) == {FinancingDateKind.FIRST_SALE_DATE, FinancingDateKind.FILING_DATE, FinancingDateKind.ANNOUNCEMENT_DATE}


def test_a_capital_event_input_with_a_date_but_no_kind_or_vice_versa_is_refused():
    with pytest.raises(DomainError):
        CapitalEventInput(financing_event_id=uuid.uuid4(), company_id=uuid.uuid4(), metric_date=dt(2026, 1, 1))
    with pytest.raises(DomainError):
        CapitalEventInput(financing_event_id=uuid.uuid4(), company_id=uuid.uuid4(), metric_date_kind=FinancingDateKind.FILING_DATE)


# ---------------- period boundaries

def test_period_is_half_open_inclusive_start_exclusive_end():
    e_start = event(metric_date=dt(2026, 1, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE)
    e_end = event(metric_date=dt(2027, 1, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE)
    result = run([e_start, e_end], start=dt(2026, 1, 1), end=dt(2027, 1, 1))
    assert result.financing_activity == 1 and result.diagnostics.events_excluded_outside_period == 1


def test_a_missing_date_is_excluded_regardless_of_period():
    e = event(metric_date=None)
    result = run([e])
    assert result.financing_activity == 0 and result.diagnostics.events_excluded_missing_date == 1
    assert result.diagnostics.events_excluded_outside_period == 0


def test_period_start_after_end_is_refused():
    with pytest.raises(InvalidInputError):
        run([], start=dt(2027, 1, 1), end=dt(2026, 1, 1))


def test_an_empty_period_start_equals_end_is_legitimate_and_empty():
    result = run([event(metric_date=dt(2026, 6, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE)], start=dt(2026, 1, 1), end=dt(2026, 1, 1))
    assert result.financing_activity == 0


# ---------------- financing activity / companies funded

def test_financing_activity_counts_qualifying_canonical_events():
    result = run([event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE) for _ in range(3)])
    assert result.financing_activity == 3


def test_companies_funded_counts_distinct_companies_not_events():
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    events = [event(company=c1, metric_date=dt(2026, m, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE) for m in (2, 4, 6)]
    events.append(event(company=c2, metric_date=dt(2026, 5, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE))
    result = run(events)
    assert result.financing_activity == 4 and result.companies_funded == 2


def test_one_canonical_event_counts_once_no_matter_how_many_sources_supported_it():
    # the pure engine only ever sees ONE CapitalEventInput per canonical FinancingEvent; multi-candidate support is
    # a repository-layer concern (Increment 11), verified again with real data in test_capital_metrics_repository.py
    e = event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE)
    assert run([e]).financing_activity == 1


# ---------------- capital deployed

def test_verified_amounts_are_summed_exactly_with_no_float():
    events = [event(metric_date=dt(2026, m, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=usd(v)) for m, v in ((2, "10000000"), (4, "7500000"))]
    result = run(events)
    assert result.capital_deployed_by_currency["USD"].minor_units == 1_750_000_000
    assert type(result.capital_deployed_by_currency["USD"].minor_units) is int


def test_a_canonical_event_without_verified_amount_still_counts_as_activity_but_contributes_no_money():
    e = event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=None)
    result = run([e])
    assert result.financing_activity == 1 and result.capital_deployed_by_currency == {}
    assert result.diagnostics.events_without_verified_amount == 1


# ---------------- multi-currency

def test_usd_and_eur_are_never_summed_together():
    events = [event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=usd("50000000")),
              event(metric_date=dt(2026, 3, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=Money.from_decimal("8000000", "EUR"))]
    result = run(events)
    assert result.capital_deployed_by_currency["USD"].minor_units == 5_000_000_000
    assert result.capital_deployed_by_currency["EUR"].minor_units == 800_000_000
    assert set(result.capital_deployed_by_currency) == {"USD", "EUR"}


def test_no_fx_conversion_surface_exists():
    import app.v2.domain.capital_metrics as m
    assert not any("fx" in n.lower() or "exchange_rate" in n.lower() or "convert" in n.lower() for n in dir(m))


# ---------------- concentration

def test_concentration_is_largest_over_total_exact():
    events = [event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=usd(v)) for v in ("60000000", "40000000")]
    result = run(events)
    assert result.capital_concentration_by_currency["USD"].share == Fraction(3, 5)


def test_concentration_is_computed_per_currency_independently():
    events = [event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=usd("60000000")),
              event(metric_date=dt(2026, 3, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=usd("40000000")),
              event(metric_date=dt(2026, 4, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=Money.from_decimal("8000000", "EUR"))]
    result = run(events)
    assert result.capital_concentration_by_currency["USD"].share == Fraction(3, 5)
    assert result.capital_concentration_by_currency["EUR"].share == Fraction(1, 1)


def test_no_verified_capital_means_concentration_is_absent_never_a_divide_by_zero():
    e = event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=None)
    result = run([e])
    assert result.capital_concentration_by_currency == {}


def test_concentration_cannot_be_constructed_with_zero_total_or_largest_exceeding_total():
    with pytest.raises(ValidationError):
        CapitalConcentration(largest_minor_units=0, total_minor_units=0)
    with pytest.raises(InvariantViolationError):
        CapitalConcentration(largest_minor_units=100, total_minor_units=50)


# ---------------- stage distribution

def test_canonical_stages_are_counted_and_missing_stage_is_unknown():
    events = [event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, stage=Stage.SEED),
              event(metric_date=dt(2026, 3, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, stage=Stage.SERIES_A),
              event(metric_date=dt(2026, 4, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, stage=Stage.UNKNOWN)]
    result = run(events)
    assert result.stage_distribution == {Stage.SEED: 1, Stage.SERIES_A: 1, Stage.UNKNOWN: 1}
    assert result.diagnostics.events_without_known_stage == 1


def test_stage_is_never_inferred_from_amount():
    e = event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=usd("900000000"), stage=Stage.UNKNOWN)
    result = run([e])
    assert result.stage_distribution == {Stage.UNKNOWN: 1}


# ---------------- diagnostics consistency

def test_diagnostics_counts_are_internally_consistent():
    events = [event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE),
              event(metric_date=None), event(metric_date=dt(2030, 1, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE)]
    result = run(events)
    d = result.diagnostics
    assert d.events_considered == d.events_included + d.events_excluded_missing_date + d.events_excluded_outside_period == 3
    with pytest.raises(InvariantViolationError):
        CapitalMetricsDiagnostics(events_considered=5, events_included=1, events_excluded_missing_date=1, events_excluded_outside_period=1,
                                  events_without_verified_amount=0, events_without_known_stage=0)
    with pytest.raises(InvariantViolationError):
        CapitalMetricsDiagnostics(events_considered=1, events_included=1, events_excluded_missing_date=0, events_excluded_outside_period=0,
                                  events_without_verified_amount=2, events_without_known_stage=0)


def test_no_score_or_signal_field_exists_on_the_result():
    result = run([])
    for banned in ("score", "signal", "trend", "increase", "decrease", "good", "bad", "commentary"):
        assert not hasattr(result, banned)


# ---------------- purity

def test_the_engine_is_deterministic_same_inputs_same_outputs():
    events = [event(metric_date=dt(2026, 2, 1), kind=FinancingDateKind.ANNOUNCEMENT_DATE, amount=usd("1000000"), stage=Stage.SEED)]
    assert run(list(events)) == run(list(events))


def test_the_pure_module_imports_no_db_network_or_ai():
    import app.v2.domain.capital_metrics as m
    import inspect
    source = inspect.getsource(m)
    for banned in ("sqlalchemy", "psycopg", "requests", "httpx", "socket", "openai", "anthropic", "os.environ"):
        assert banned not in source
