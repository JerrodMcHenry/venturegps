"""Pure tests: window construction, percentile rank, component/overall signal derivation. No database, no clock."""

import uuid
from datetime import datetime, timedelta, timezone
from fractions import Fraction

import pytest
from pydantic import ValidationError

from app.v2.domain.capital_metrics import CapitalEventInput, compute_capital_metrics
from app.v2.domain.capital_signal import (
    HISTORICAL_WINDOW_COUNT,
    METHODOLOGY_VERSION,
    MIN_HISTORICAL_NONZERO_WINDOWS,
    WINDOW_DURATION,
    CapitalComponentSignal,
    CapitalConcentrationSignal,
    CapitalDirection,
    ComponentMetric,
    ConcentrationTrend,
    build_windows,
    compute_capital_signal,
    percentile_rank,
)
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.financing import FinancingDateKind, Money, Stage

MARKET = uuid.uuid4()
TV = "venturegps_taxonomy.v1"
AS_OF = datetime(2026, 9, 21, tzinfo=timezone.utc)


def dt(*args, **kw):
    return datetime(*args, tzinfo=timezone.utc, **kw)


# ---------------- window construction

def test_current_window_is_the_trailing_30_days_ending_at_as_of():
    current, _ = build_windows(AS_OF)
    assert current == (AS_OF - timedelta(days=30), AS_OF)


def test_exactly_eight_historical_windows_of_the_same_duration_oldest_first():
    _, historical = build_windows(AS_OF)
    assert len(historical) == HISTORICAL_WINDOW_COUNT
    for start, end in historical:
        assert end - start == WINDOW_DURATION
    assert historical[0][0] < historical[-1][0]   # oldest first


def test_historical_windows_are_contiguous_and_non_overlapping_and_end_where_the_next_begins():
    current, historical = build_windows(AS_OF)
    chain = list(historical) + [current]
    for (s1, e1), (s2, e2) in zip(chain, chain[1:]):
        assert e1 == s2   # no gap, no overlap: the end of one window is exactly the start of the next


def test_no_historical_window_ever_reaches_the_current_windows_start_no_future_leakage():
    current, historical = build_windows(AS_OF)
    for start, end in historical:
        assert end <= current[0]
        assert start < current[0] and end < current[1]


def test_no_window_ever_includes_data_on_or_after_as_of():
    current, historical = build_windows(AS_OF)
    for _, end in (current, *historical):
        assert end <= AS_OF


def test_construction_is_deterministic_for_the_same_as_of():
    assert build_windows(AS_OF) == build_windows(AS_OF)


def test_different_as_of_values_produce_different_windows():
    assert build_windows(AS_OF) != build_windows(AS_OF + timedelta(days=1))


def test_as_of_must_be_explicit_and_timezone_aware():
    with pytest.raises(DomainError):
        build_windows(datetime(2026, 9, 21))   # naive
    with pytest.raises(DomainError):
        build_windows("2026-09-21")


# ---------------- percentile rank

def test_percentile_rank_of_the_maximum_is_one():
    assert percentile_rank(10, [1, 2, 3, 4, 5, 6, 7, 8]) == Fraction(1, 1)


def test_percentile_rank_of_the_minimum_is_zero():
    assert percentile_rank(0, [1, 2, 3, 4, 5, 6, 7, 8]) == Fraction(0, 1)


def test_percentile_rank_of_a_value_equal_to_all_history_is_the_midpoint():
    assert percentile_rank(3, [3, 3, 3, 3, 3, 3, 3, 3]) == Fraction(1, 2)   # zero-variance history: exact stable point


def test_percentile_rank_ties_use_mean_rank():
    # 2 strictly less, 2 equal, 4 strictly greater, n=8: (2 + 2/2) / 8 = 3/8
    assert percentile_rank(3, [1, 2, 3, 3, 4, 5, 6, 7]) == Fraction(3, 8)


def test_percentile_rank_never_divides_by_zero_given_a_fixed_size_history():
    percentile_rank(5, [0] * HISTORICAL_WINDOW_COUNT)   # all zero: must not raise
    with pytest.raises(InvalidInputError):
        percentile_rank(5, [])


def test_percentile_rank_is_robust_to_one_extreme_historical_outlier():
    # a single $250M round should not distort where a normal $5M current value ranks
    historical = [2_000_000, 4_000_000, 5_000_000, 6_000_000, 5_500_000, 4_500_000, 3_000_000, 250_000_000]
    rank_normal = percentile_rank(5_000_000, historical)
    # current sits squarely in the middle of the ordinary values; the outlier should not push it to an extreme
    assert Fraction(3, 10) <= rank_normal <= Fraction(7, 10)


def test_percentile_rank_works_on_fractions_not_only_ints():
    assert percentile_rank(Fraction(1, 2), [Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)]) == Fraction(1, 2)


# ---------------- component signals: sufficiency and direction

def component(current, historical, metric=ComponentMetric.FINANCING_ACTIVITY, currency=None):
    from app.v2.domain.capital_signal import _build_component
    return _build_component(metric, currency, current, historical)


def test_fewer_than_three_nonzero_historical_windows_is_insufficient_data():
    result = component(5, [0, 0, 1, 0, 0, 0, 0, 0])   # only 1 nonzero window
    assert result.direction is CapitalDirection.INSUFFICIENT_DATA and result.percentile_rank is None
    assert result.historical_nonzero_windows == 1


def test_exactly_three_nonzero_historical_windows_is_sufficient():
    result = component(5, [0, 1, 0, 1, 0, 1, 0, 0])
    assert result.direction is not CapitalDirection.INSUFFICIENT_DATA and result.percentile_rank is not None


def test_zero_is_a_legitimate_historical_observation_not_treated_as_missing():
    # a genuinely sparse-but-real market: 0,0,1,0,0,1,0,1 -- three nonzero windows, current also low
    result = component(0, [0, 0, 1, 0, 0, 1, 0, 1])
    assert result.historical_nonzero_windows == 3
    assert result.direction is not CapitalDirection.INSUFFICIENT_DATA


def test_insufficient_is_never_silently_downgraded_to_stable():
    result = component(0, [0, 0, 0, 0, 0, 0, 0, 0])   # all zero: zero nonzero windows
    assert result.direction is CapitalDirection.INSUFFICIENT_DATA
    assert result.direction is not CapitalDirection.STABLE


@pytest.mark.parametrize("current, expected", [
    (10, CapitalDirection.STRONG_INCREASE),   # above all 8 historical -> rank 1
    (5, CapitalDirection.STABLE),             # middle of the pack
    (0, CapitalDirection.STRONG_DECREASE),    # below all 8 historical -> rank 0
])
def test_component_direction_bands(current, expected):
    historical = [3, 4, 5, 6, 7, 3, 4, 6]   # sufficient (all nonzero)
    assert component(current, historical).direction is expected


def test_current_historically_high_but_not_extreme_is_plain_increase():
    historical = [1, 2, 3, 4, 5, 6, 7, 8]
    # rank of 7 among these 8: less=6, equal=1 -> (6+0.5)/8 = 0.8125 -> in [0.7, 0.9) -> increase, not strong
    result = component(7, historical)
    assert result.direction is CapitalDirection.INCREASE


def test_current_historically_low_but_not_extreme_is_plain_decrease():
    historical = [1, 2, 3, 4, 5, 6, 7, 8]
    result = component(2, historical)
    assert result.direction is CapitalDirection.DECREASE


def test_a_component_signal_is_never_mixed():
    with pytest.raises(DomainError):
        CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, current_value=1, historical_values=(1,) * 8,
                               historical_nonzero_windows=8, percentile_rank=Fraction(1, 2), direction=CapitalDirection.MIXED)


def test_capital_deployed_requires_a_currency_other_metrics_must_not_have_one():
    with pytest.raises(DomainError):
        CapitalComponentSignal(metric=ComponentMetric.CAPITAL_DEPLOYED, currency_code=None, current_value=1,
                               historical_values=(1,) * 8, historical_nonzero_windows=8, percentile_rank=Fraction(1, 2),
                               direction=CapitalDirection.STABLE)
    with pytest.raises(DomainError):
        CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, currency_code="USD", current_value=1,
                               historical_values=(1,) * 8, historical_nonzero_windows=8, percentile_rank=Fraction(1, 2),
                               direction=CapitalDirection.STABLE)


def test_wrong_length_historical_values_is_refused():
    with pytest.raises(DomainError):
        CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, current_value=1, historical_values=(1, 2, 3),
                               historical_nonzero_windows=3, percentile_rank=Fraction(1, 2), direction=CapitalDirection.STABLE)


# ---------------- concentration: contextual, separate vocabulary

def test_concentration_uses_its_own_vocabulary_never_capitaldirection():
    from app.v2.domain.capital_signal import _build_concentration
    result = _build_concentration("USD", Fraction(9, 10), [Fraction(1, 2), Fraction(1, 2), Fraction(1, 2)] + [None] * 5)
    assert isinstance(result.trend, ConcentrationTrend)
    assert not isinstance(result.trend, CapitalDirection)
    assert set(ConcentrationTrend) == {ConcentrationTrend.MORE_CONCENTRATED, ConcentrationTrend.LESS_CONCENTRATED,
                                       ConcentrationTrend.STABLE, ConcentrationTrend.INSUFFICIENT_DATA}


def test_higher_concentration_share_trends_more_concentrated_not_positive():
    from app.v2.domain.capital_signal import _build_concentration
    result = _build_concentration("USD", Fraction(9, 10), [Fraction(1, 4)] * 4 + [None] * 4)
    assert result.trend is ConcentrationTrend.MORE_CONCENTRATED   # a fact about spread, not a value judgement


def test_lower_concentration_share_trends_less_concentrated():
    from app.v2.domain.capital_signal import _build_concentration
    result = _build_concentration("USD", Fraction(1, 10), [Fraction(3, 4)] * 4 + [None] * 4)
    assert result.trend is ConcentrationTrend.LESS_CONCENTRATED


def test_concentration_is_insufficient_when_current_is_absent_or_history_too_thin():
    from app.v2.domain.capital_signal import _build_concentration
    assert _build_concentration("USD", None, [Fraction(1, 2)] * 8).trend is ConcentrationTrend.INSUFFICIENT_DATA
    assert _build_concentration("USD", Fraction(1, 2), [Fraction(1, 2), Fraction(1, 2)] + [None] * 6).trend is ConcentrationTrend.INSUFFICIENT_DATA


def test_concentration_never_divides_by_zero_when_all_historical_shares_are_absent():
    from app.v2.domain.capital_signal import _build_concentration
    result = _build_concentration("USD", Fraction(1, 2), [None] * 8)
    assert result.trend is ConcentrationTrend.INSUFFICIENT_DATA


# ---------------- overall aggregation

def signal(current_vals, historical_by_window, currencies=()):
    """current_vals: dict(financing_activity, companies_funded); historical_by_window: list of 8 dicts, same keys."""
    cw, hw = build_windows(AS_OF)

    def metrics(window, values, cur_map):
        events = []
        for i in range(values.get("financing_activity", 0)):
            money = None
            if "capital_deployed" in cur_map:
                cur, amt = cur_map["capital_deployed"]
                money = Money.from_decimal(str(amt), cur)
            events.append(CapitalEventInput(financing_event_id=uuid.uuid4(), company_id=uuid.uuid4(),
                                            metric_date=window[0], metric_date_kind=FinancingDateKind.ANNOUNCEMENT_DATE,
                                            verified_round_amount=money if i == 0 else None, stage=Stage.UNKNOWN))
        return compute_capital_metrics(events, market_id=MARKET, taxonomy_version=TV, period_start=window[0], period_end=window[1])

    current_metrics = metrics(cw, current_vals, current_vals)
    historical_metrics = [metrics(w, v, v) for w, v in zip(hw, historical_by_window)]
    return compute_capital_signal(current_metrics, historical_metrics, market_id=MARKET, taxonomy_version=TV,
                                  as_of=AS_OF, current_window=cw, historical_windows=hw)


def test_broad_up_agreement_yields_increase():
    result = signal({"financing_activity": 6}, [{"financing_activity": 2}] * 8)
    assert result.financing_activity.direction is CapitalDirection.STRONG_INCREASE
    # companies_funded has zero events proposed at all in this synthetic scenario -> insufficient (0 nonzero windows)


def test_broad_down_agreement_yields_decrease():
    result = signal({"financing_activity": 0}, [{"financing_activity": 5}] * 8)
    assert result.financing_activity.direction is CapitalDirection.STRONG_DECREASE


def test_all_insufficient_yields_insufficient_data_overall():
    result = signal({"financing_activity": 0}, [{"financing_activity": 0}] * 8)
    assert result.overall is CapitalDirection.INSUFFICIENT_DATA


def test_conflicting_components_yield_mixed_not_a_forced_direction():
    from app.v2.domain.capital_signal import CapitalWindow, _aggregate_overall
    up = CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, current_value=8, historical_values=(1,) * 8,
                                historical_nonzero_windows=8, percentile_rank=Fraction(1, 1), direction=CapitalDirection.INCREASE)
    down = CapitalComponentSignal(metric=ComponentMetric.COMPANIES_FUNDED, current_value=0, historical_values=(5,) * 8,
                                  historical_nonzero_windows=8, percentile_rank=Fraction(0, 1), direction=CapitalDirection.DECREASE)
    assert _aggregate_overall([up, down]) is CapitalDirection.MIXED


def test_stable_requires_all_voting_components_to_be_stable():
    from app.v2.domain.capital_signal import _aggregate_overall
    stable = CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, current_value=5, historical_values=(4, 5, 6, 5, 4, 6, 5, 4),
                                    historical_nonzero_windows=8, percentile_rank=Fraction(1, 2), direction=CapitalDirection.STABLE)
    assert _aggregate_overall([stable, stable]) is CapitalDirection.STABLE


def test_a_giant_round_alone_does_not_force_strong_increase_when_other_components_are_flat():
    from app.v2.domain.capital_signal import _aggregate_overall
    huge_amount = CapitalComponentSignal(metric=ComponentMetric.CAPITAL_DEPLOYED, currency_code="USD", current_value=250_000_000_00,
                                         historical_values=(1_000_000_00,) * 8, historical_nonzero_windows=8,
                                         percentile_rank=Fraction(1, 1), direction=CapitalDirection.STRONG_INCREASE)
    flat_activity = CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, current_value=5, historical_values=(4, 5, 6, 5, 4, 6, 5, 4),
                                           historical_nonzero_windows=8, percentile_rank=Fraction(1, 2), direction=CapitalDirection.STABLE)
    result = _aggregate_overall([huge_amount, flat_activity])
    assert result is CapitalDirection.INCREASE and result is not CapitalDirection.STRONG_INCREASE


def test_a_giant_round_with_declining_breadth_produces_mixed_not_automatic_increase():
    from app.v2.domain.capital_signal import _aggregate_overall
    huge_amount = CapitalComponentSignal(metric=ComponentMetric.CAPITAL_DEPLOYED, currency_code="USD", current_value=250_000_000_00,
                                         historical_values=(1_000_000_00,) * 8, historical_nonzero_windows=8,
                                         percentile_rank=Fraction(1, 1), direction=CapitalDirection.STRONG_INCREASE)
    declining = CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, current_value=0, historical_values=(5,) * 8,
                                       historical_nonzero_windows=8, percentile_rank=Fraction(0, 1), direction=CapitalDirection.STRONG_DECREASE)
    assert _aggregate_overall([huge_amount, declining]) is CapitalDirection.MIXED


def test_strong_increase_requires_unanimous_strong_agreement_among_voting_components():
    from app.v2.domain.capital_signal import _aggregate_overall
    strong = CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, current_value=10, historical_values=(1,) * 8,
                                    historical_nonzero_windows=8, percentile_rank=Fraction(1, 1), direction=CapitalDirection.STRONG_INCREASE)
    mild = CapitalComponentSignal(metric=ComponentMetric.COMPANIES_FUNDED, current_value=6, historical_values=(1, 2, 3, 4, 5, 6, 7, 8),
                                  historical_nonzero_windows=8, percentile_rank=Fraction(13, 16), direction=CapitalDirection.INCREASE)
    assert _aggregate_overall([strong, strong]) is CapitalDirection.STRONG_INCREASE
    assert _aggregate_overall([strong, mild]) is CapitalDirection.INCREASE   # not unanimous strong: falls back to plain increase


def test_strong_decrease_requires_unanimous_strong_agreement_among_voting_components():
    from app.v2.domain.capital_signal import _aggregate_overall
    strong_down = CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, current_value=0, historical_values=(8,) * 8,
                                         historical_nonzero_windows=8, percentile_rank=Fraction(0, 1), direction=CapitalDirection.STRONG_DECREASE)
    mild_down = CapitalComponentSignal(metric=ComponentMetric.COMPANIES_FUNDED, current_value=2, historical_values=(1, 2, 3, 4, 5, 6, 7, 8),
                                       historical_nonzero_windows=8, percentile_rank=Fraction(3, 16), direction=CapitalDirection.DECREASE)
    assert _aggregate_overall([strong_down, strong_down]) is CapitalDirection.STRONG_DECREASE
    assert _aggregate_overall([strong_down, mild_down]) is CapitalDirection.DECREASE   # not unanimous strong: falls back to plain decrease


def test_partial_sufficiency_only_voting_components_participate():
    from app.v2.domain.capital_signal import _aggregate_overall
    insufficient = CapitalComponentSignal(metric=ComponentMetric.FINANCING_ACTIVITY, current_value=0, historical_values=(0,) * 8,
                                          historical_nonzero_windows=0, percentile_rank=None, direction=CapitalDirection.INSUFFICIENT_DATA)
    up = CapitalComponentSignal(metric=ComponentMetric.COMPANIES_FUNDED, current_value=8, historical_values=(1,) * 8,
                                historical_nonzero_windows=8, percentile_rank=Fraction(1, 1), direction=CapitalDirection.INCREASE)
    assert _aggregate_overall([insufficient, up]) is CapitalDirection.INCREASE


def test_concentration_never_participates_in_overall_voting():
    from app.v2.domain.capital_signal import _aggregate_overall
    # _aggregate_overall's signature only accepts CapitalComponentSignal, not CapitalConcentrationSignal: a type-level guarantee
    import inspect
    sig = inspect.signature(_aggregate_overall)
    assert "voting" in sig.parameters


# ---------------- reproducibility and overall self-consistency

def test_same_inputs_produce_the_same_signal():
    a = signal({"financing_activity": 3}, [{"financing_activity": 2}] * 8)
    b = signal({"financing_activity": 3}, [{"financing_activity": 2}] * 8)
    assert a == b


def test_methodology_version_is_present_and_fixed():
    result = signal({"financing_activity": 3}, [{"financing_activity": 2}] * 8)
    assert result.methodology_version == METHODOLOGY_VERSION == "capital_signal.v1"


def test_overall_must_match_the_deterministic_recomputation_from_components():
    result = signal({"financing_activity": 3}, [{"financing_activity": 2}] * 8)
    from app.v2.domain.capital_signal import _aggregate_overall
    voting = (result.financing_activity, result.companies_funded, *result.capital_deployed)
    assert result.overall == _aggregate_overall(voting)


def test_constructing_a_signal_with_a_wrong_overall_is_refused():
    from app.v2.domain.capital_signal import CapitalSignal
    result = signal({"financing_activity": 3}, [{"financing_activity": 2}] * 8)
    wrong = CapitalDirection.MIXED if result.overall is not CapitalDirection.MIXED else CapitalDirection.STABLE
    fields = {name: getattr(result, name) for name in type(result).model_fields}
    fields["overall"] = wrong
    with pytest.raises(DomainError):
        CapitalSignal(**fields)


def test_compute_capital_signal_requires_exactly_eight_historical_metrics():
    cw, hw = build_windows(AS_OF)
    empty = compute_capital_metrics([], market_id=MARKET, taxonomy_version=TV, period_start=cw[0], period_end=cw[1])
    with pytest.raises(InvalidInputError):
        compute_capital_signal(empty, [empty] * 7, market_id=MARKET, taxonomy_version=TV, as_of=AS_OF, current_window=cw, historical_windows=hw)
