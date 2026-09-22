"""
The Capital Signal engine. PURE: no database, no network, no environment, no AI, no wall clock. Deterministic
inputs -> a deterministic, typed result. Built entirely on top of app.v2.domain.capital_metrics (Increment 12):
this module never re-derives market attribution, verified-amount handling, stage handling, date policy or
currency policy -- it only compares CapitalMetrics objects the caller already computed with that engine, once per
window, against a canonical Market's own history.

    CapitalMetrics (current window) + CapitalMetrics x8 (historical windows, from app.v2.repositories.capital_signal)
        -> compute_capital_signal()
        -> CapitalSignal

WHAT CAPITAL SIGNAL MEASURES: current observable financing activity relative to a Market's OWN historical Capital
activity. It is NOT startup quality, market attractiveness, an investment recommendation, a prediction, a
valuation, or a success probability. It never compares one Market against another.

WINDOWS: the current window is a trailing 30-day half-open interval [as_of - 30d, as_of), matching the
[period_start, period_end) convention of app.v2.domain.capital_metrics. The historical baseline is exactly
HISTORICAL_WINDOW_COUNT (8) prior windows of the SAME 30-day duration, constructed by walking strictly backward
from the current window's start with no gap and no overlap:

    H8 = [as_of-270d, as_of-240d)  ...  H2 = [as_of-90d, as_of-60d)  H1 = [as_of-60d, as_of-30d)  C = [as_of-30d, as_of)

No historical window ever reaches as_of - 30d (the current window's start), so no historical window can ever
include data the current window also covers, and none can include data occurring on or after `as_of`. `as_of` is
always an explicit argument; nothing here ever reads a wall clock, so the same inputs always produce the same
windows and the same signal.

MINIMUM HISTORY (why 8 windows / 3 non-zero): a Market with one historical financing does not have a meaningful
baseline, but a Market that has genuinely never seen more than a couple of financings in 8 months is still
LEGITIMATE data (zero is an observation, not a missing one -- see app.v2.domain.capital_metrics's own docstring
for the same principle applied per-event). The two are told apart like this: HISTORICAL_WINDOW_COUNT (8) is fixed
structural coverage -- we always look at exactly 8 windows, regardless of what is in them. Within those 8 windows,
a metric is trusted for comparison only if at least MIN_HISTORICAL_NONZERO_WINDOWS (3) of them are non-zero for
that metric. Fewer than 3 non-zero observations makes an 8-bucket distribution too degenerate to characterize a
market's typical activity (a single non-zero data point among seven zeros would trivially rank as an all-time
high with only one real number of evidence behind it), so the result is `insufficient_data` -- never silently
downgraded to `stable`. `stable` means: there IS enough evidence, and current activity is historically ordinary.

METHODOLOGY -- PERCENTILE RANK (capital_signal.v1): the current value's position among the 8 historical values,
using the standard mean-rank tie handling (`(strictly-less + ties/2) / 8`), computed exactly with `fractions.
Fraction` (never a float). Percentile rank was chosen over mean/standard-deviation or a raw growth-rate threshold
because:
  - it is ROBUST TO OUTLIERS BY CONSTRUCTION: one $250M historical round only shifts where it sits in the
    ORDERING, never the scale of comparison the way a mean or standard deviation would;
  - it needs no distributional assumption (no claim of normality) and degrades gracefully on zero-variance or
    all-zero history (current == every historical value -> the exact midpoint, 1/2 -> stable);
  - it is directly explainable without translation: "current financing activity stands above N/8 of the last 8
    30-day windows" is the percentile rank itself, not a derived score;
  - it works identically for integer counts (Financing Activity, Companies Funded) and integer money (minor
    units), with no unit conversion.
Direction bands (symmetric, chosen for round explainability, not tuned to any specific market):

    percentile_rank >= 9/10   strong_increase      (at or above the top of the last 8 windows)
    7/10 <= rank <  9/10      increase
    3/10 <= rank <  7/10      stable               (the broad, ordinary middle)
    1/10 <= rank <  3/10      decrease
    rank <  1/10               strong_decrease

COMPONENTS THAT VOTE in the overall signal: Financing Activity, Companies Funded, and Capital Deployed -- ONE
component PER CURRENCY (a currency with insufficient history never fabricates a direction, and currencies are
NEVER combined -- Increment 12's no-FX invariant is preserved exactly; see app.v2.domain.capital_metrics).

CAPITAL CONCENTRATION IS CONTEXTUAL ONLY AND NEVER VOTES. Higher concentration is not "positive" Capital activity
and lower concentration is not "negative" Capital activity -- it is a different axis (how spread out deployed
capital is), so it gets its own vocabulary (ConcentrationTrend: more_concentrated / less_concentrated / stable /
insufficient_data), never CapitalDirection's increase/decrease, so it structurally cannot be misread as a Capital
Signal vote.

OVERALL AGGREGATION is AGREEMENT-BASED, never a weighted average (a methodology that let one large number dominate
a weighted score is exactly what this avoids -- see `_aggregate_overall`):
  - components with `insufficient_data` do not vote; if NONE of the voting components has a direction, the whole
    signal is `insufficient_data`;
  - if the voting components that DO have a direction include both an up (increase/strong_increase) and a down
    (decrease/strong_decrease), the signal is `mixed` -- a real disagreement, never forced into a fake single
    answer;
  - if every voting component points up, the signal is `strong_increase` only when EVERY voting component is
    itself `strong_increase` (unanimous strong agreement); otherwise `increase`. One giant financing round showing
    up as `strong_increase` in Capital Deployed while Financing Activity and Companies Funded are merely flat or
    down can never alone produce `strong_increase`, and if they are down it produces `mixed`, not `increase`.
    Symmetric rule for `strong_decrease` / `decrease`.
  - if every voting component is `stable` (and none is up or down), the signal is `stable`.

METHODOLOGY VERSION: `capital_signal.v1`. A future methodology change must introduce `capital_signal.v2` and
compute alongside it, never silently reinterpret v1's stored/reported results.
"""

from collections.abc import Sequence
from datetime import timedelta
from fractions import Fraction
from enum import Enum
from uuid import UUID

from pydantic import Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.capital_metrics import CapitalMetrics
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.time import UtcDatetime, ensure_utc
from app.v2.domain.versions import VersionId

METHODOLOGY_VERSION = "capital_signal.v1"

WINDOW_DURATION = timedelta(days=30)
HISTORICAL_WINDOW_COUNT = 8
MIN_HISTORICAL_NONZERO_WINDOWS = 3

_STRONG_UP = Fraction(9, 10)
_UP = Fraction(7, 10)
_DOWN = Fraction(3, 10)
_STRONG_DOWN = Fraction(1, 10)


class CapitalDirection(str, Enum):
    STRONG_INCREASE = "strong_increase"
    INCREASE = "increase"
    STABLE = "stable"
    DECREASE = "decrease"
    STRONG_DECREASE = "strong_decrease"
    INSUFFICIENT_DATA = "insufficient_data"
    MIXED = "mixed"   # ONLY ever legal on the OVERALL result; a component signal is never mixed (see StoredCapitalComponentSignal)


_UP_DIRECTIONS = frozenset({CapitalDirection.INCREASE, CapitalDirection.STRONG_INCREASE})
_DOWN_DIRECTIONS = frozenset({CapitalDirection.DECREASE, CapitalDirection.STRONG_DECREASE})


class ComponentMetric(str, Enum):
    FINANCING_ACTIVITY = "financing_activity"
    COMPANIES_FUNDED = "companies_funded"
    CAPITAL_DEPLOYED = "capital_deployed"


class ConcentrationTrend(str, Enum):
    """Deliberately a SEPARATE vocabulary from CapitalDirection: concentration moving up or down is not itself
    Capital activity increasing or decreasing (see module docstring)."""

    MORE_CONCENTRATED = "more_concentrated"
    LESS_CONCENTRATED = "less_concentrated"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


def build_windows(as_of) -> tuple[tuple[UtcDatetime, UtcDatetime], tuple[tuple[UtcDatetime, UtcDatetime], ...]]:
    """(current_window, historical_windows) as [start, end) pairs. historical_windows is OLDEST FIRST. `as_of` is
    always explicit; this function never reads a wall clock."""
    as_of = ensure_utc(as_of, field="as_of")
    current_end = as_of
    current_start = current_end - WINDOW_DURATION
    historical: list[tuple[UtcDatetime, UtcDatetime]] = []
    end = current_start
    for _ in range(HISTORICAL_WINDOW_COUNT):
        start = end - WINDOW_DURATION
        historical.append((start, end))
        end = start
    historical.reverse()
    return (current_start, current_end), tuple(historical)


def percentile_rank(current, historical: Sequence) -> Fraction:
    """The mean-rank percentile of `current` among `historical` (any orderable, comparable values -- ints or
    Fractions), exact. Never divides by zero: `historical` is always HISTORICAL_WINDOW_COUNT long by construction."""
    n = len(historical)
    if n == 0:
        raise InvalidInputError("empty_historical_series", "percentile rank needs at least one historical value")
    less = sum(1 for h in historical if h < current)
    equal = sum(1 for h in historical if h == current)
    return Fraction(less, n) + Fraction(equal, 2 * n)


def _direction_from_rank(rank: Fraction) -> CapitalDirection:
    if rank >= _STRONG_UP:
        return CapitalDirection.STRONG_INCREASE
    if rank >= _UP:
        return CapitalDirection.INCREASE
    if rank >= _DOWN:
        return CapitalDirection.STABLE
    if rank >= _STRONG_DOWN:
        return CapitalDirection.DECREASE
    return CapitalDirection.STRONG_DECREASE


def _concentration_trend_from_rank(rank: Fraction) -> ConcentrationTrend:
    if rank >= _UP:
        return ConcentrationTrend.MORE_CONCENTRATED
    if rank >= _DOWN:
        return ConcentrationTrend.STABLE
    return ConcentrationTrend.LESS_CONCENTRATED


class CapitalComponentSignal(DomainModel):
    """A single quantitative comparison (Financing Activity, Companies Funded, or Capital Deployed for ONE
    currency) against the Market's own 8-window history. VOTES in the overall Capital Signal unless its own
    direction is insufficient_data."""

    metric: ComponentMetric
    currency_code: str | None = None   # set iff metric is CAPITAL_DEPLOYED
    current_value: int = Field(ge=0)   # a count, or minor currency units
    historical_values: tuple[int, ...]   # exactly HISTORICAL_WINDOW_COUNT entries, oldest first; zero is legitimate data
    historical_nonzero_windows: int = Field(ge=0)
    percentile_rank: Fraction | None = None   # None iff direction is insufficient_data
    direction: CapitalDirection

    model_config = {"arbitrary_types_allowed": True}   # for Fraction; merges with DomainModel's frozen/strict/forbid config

    @model_validator(mode="after")
    def _shape_is_coherent(self) -> "CapitalComponentSignal":
        if (self.metric is ComponentMetric.CAPITAL_DEPLOYED) != (self.currency_code is not None):
            raise InvalidInputError("currency_required_for_capital_deployed", "currency_code is set iff the metric is capital_deployed")
        if len(self.historical_values) != HISTORICAL_WINDOW_COUNT:
            raise InvalidInputError("wrong_historical_window_count", f"historical_values must have exactly {HISTORICAL_WINDOW_COUNT} entries")
        if self.historical_nonzero_windows != sum(1 for h in self.historical_values if h > 0):
            raise InvariantViolationError("nonzero_count_mismatch", "historical_nonzero_windows must match historical_values")
        if self.direction is CapitalDirection.MIXED:
            raise InvalidInputError("component_cannot_be_mixed", "a single component is never mixed; only the overall signal can be")
        sufficient = self.historical_nonzero_windows >= MIN_HISTORICAL_NONZERO_WINDOWS
        if sufficient != (self.direction is not CapitalDirection.INSUFFICIENT_DATA):
            raise InvariantViolationError("sufficiency_mismatch", "direction must be insufficient_data exactly when history is insufficient")
        if sufficient != (self.percentile_rank is not None):
            raise InvariantViolationError("percentile_rank_mismatch", "percentile_rank is present exactly when the component is sufficient")
        return self

    @property
    def votes(self) -> bool:
        return self.direction is not CapitalDirection.INSUFFICIENT_DATA


def _build_component(metric: ComponentMetric, currency_code: str | None, current_value: int, historical_values: Sequence[int]) -> CapitalComponentSignal:
    historical_values = tuple(historical_values)
    nonzero = sum(1 for h in historical_values if h > 0)
    if nonzero < MIN_HISTORICAL_NONZERO_WINDOWS:
        return CapitalComponentSignal(metric=metric, currency_code=currency_code, current_value=current_value,
                                      historical_values=historical_values, historical_nonzero_windows=nonzero,
                                      percentile_rank=None, direction=CapitalDirection.INSUFFICIENT_DATA)
    rank = percentile_rank(current_value, historical_values)
    return CapitalComponentSignal(metric=metric, currency_code=currency_code, current_value=current_value,
                                  historical_values=historical_values, historical_nonzero_windows=nonzero,
                                  percentile_rank=rank, direction=_direction_from_rank(rank))


class CapitalConcentrationSignal(DomainModel):
    """Contextual only: NEVER a vote in the overall Capital Signal (see module docstring)."""

    currency_code: str
    current_share: Fraction | None = None   # None iff no verified capital this period (concentration is absent, not zero)
    historical_shares: tuple[Fraction | None, ...]   # exactly HISTORICAL_WINDOW_COUNT entries; None where absent that window
    trend: ConcentrationTrend

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _shape_is_coherent(self) -> "CapitalConcentrationSignal":
        if len(self.historical_shares) != HISTORICAL_WINDOW_COUNT:
            raise InvalidInputError("wrong_historical_window_count", f"historical_shares must have exactly {HISTORICAL_WINDOW_COUNT} entries")
        available = [s for s in self.historical_shares if s is not None]
        sufficient = self.current_share is not None and len(available) >= MIN_HISTORICAL_NONZERO_WINDOWS
        if sufficient != (self.trend is not ConcentrationTrend.INSUFFICIENT_DATA):
            raise InvariantViolationError("sufficiency_mismatch", "trend must be insufficient_data exactly when there is not enough comparable history")
        return self


def _build_concentration(currency_code: str, current_share: Fraction | None, historical_shares: Sequence[Fraction | None]) -> CapitalConcentrationSignal:
    historical_shares = tuple(historical_shares)
    available = [s for s in historical_shares if s is not None]
    if current_share is None or len(available) < MIN_HISTORICAL_NONZERO_WINDOWS:
        trend = ConcentrationTrend.INSUFFICIENT_DATA
    else:
        trend = _concentration_trend_from_rank(percentile_rank(current_share, available))
    return CapitalConcentrationSignal(currency_code=currency_code, current_share=current_share, historical_shares=historical_shares, trend=trend)


def _aggregate_overall(voting: Sequence[CapitalComponentSignal]) -> CapitalDirection:
    determinate = [c.direction for c in voting if c.votes]
    if not determinate:
        return CapitalDirection.INSUFFICIENT_DATA
    has_up = any(d in _UP_DIRECTIONS for d in determinate)
    has_down = any(d in _DOWN_DIRECTIONS for d in determinate)
    if has_up and has_down:
        return CapitalDirection.MIXED
    if has_up:
        return CapitalDirection.STRONG_INCREASE if all(d is CapitalDirection.STRONG_INCREASE for d in determinate) else CapitalDirection.INCREASE
    if has_down:
        return CapitalDirection.STRONG_DECREASE if all(d is CapitalDirection.STRONG_DECREASE for d in determinate) else CapitalDirection.DECREASE
    return CapitalDirection.STABLE


class CapitalWindow(DomainModel):
    window_start: UtcDatetime
    window_end: UtcDatetime
    metrics: CapitalMetrics


class CapitalSignal(DomainModel):
    """The overall, deterministic Capital Signal for one Market, under one taxonomy version, as of one instant.
    Measures observable financing activity relative to the Market's OWN history -- never a quality judgement, a
    recommendation, or a prediction."""

    market_id: UUID
    taxonomy_version: VersionId
    as_of: UtcDatetime
    methodology_version: str = METHODOLOGY_VERSION

    current_window: CapitalWindow
    historical_windows: tuple[CapitalWindow, ...]   # exactly HISTORICAL_WINDOW_COUNT, oldest first

    financing_activity: CapitalComponentSignal
    companies_funded: CapitalComponentSignal
    capital_deployed: tuple[CapitalComponentSignal, ...]      # one per currency observed in the current or historical windows
    capital_concentration: tuple[CapitalConcentrationSignal, ...]   # one per currency; contextual, never voted

    overall: CapitalDirection

    @model_validator(mode="after")
    def _overall_matches_independent_recomputation(self) -> "CapitalSignal":
        if len(self.historical_windows) != HISTORICAL_WINDOW_COUNT:
            raise InvalidInputError("wrong_historical_window_count", f"historical_windows must have exactly {HISTORICAL_WINDOW_COUNT} entries")
        if self.methodology_version != METHODOLOGY_VERSION:
            raise InvalidInputError("unknown_methodology_version", "methodology_version must be the version this module implements")
        for currency_signal in self.capital_deployed:
            if currency_signal.metric is not ComponentMetric.CAPITAL_DEPLOYED:
                raise InvalidInputError("capital_deployed_metric_mismatch", "every entry of capital_deployed must have metric CAPITAL_DEPLOYED")
        voting = (self.financing_activity, self.companies_funded, *self.capital_deployed)
        if self.overall != _aggregate_overall(voting):
            raise InvariantViolationError("overall_mismatch", "overall must equal the deterministic aggregation of the voting components")
        return self


def compute_capital_signal(
    current_metrics: CapitalMetrics, historical_metrics: Sequence[CapitalMetrics], *, market_id: UUID,
    taxonomy_version: str, as_of, current_window: tuple, historical_windows: Sequence[tuple],
) -> CapitalSignal:
    """The pure aggregation entry point. `current_metrics`/`historical_metrics` must already be computed by
    app.v2.domain.capital_metrics.compute_capital_metrics for exactly `current_window`/`historical_windows`
    (see app.v2.repositories.capital_signal, which builds these); this function never queries anything."""
    if len(historical_metrics) != HISTORICAL_WINDOW_COUNT or len(historical_windows) != HISTORICAL_WINDOW_COUNT:
        raise InvalidInputError("wrong_historical_window_count", f"exactly {HISTORICAL_WINDOW_COUNT} historical windows/metrics are required")
    as_of = ensure_utc(as_of, field="as_of")

    financing_activity = _build_component(ComponentMetric.FINANCING_ACTIVITY, None, current_metrics.financing_activity,
                                          [m.financing_activity for m in historical_metrics])
    companies_funded = _build_component(ComponentMetric.COMPANIES_FUNDED, None, current_metrics.companies_funded,
                                        [m.companies_funded for m in historical_metrics])

    currencies = set(current_metrics.capital_deployed_by_currency) | {c for m in historical_metrics for c in m.capital_deployed_by_currency}
    capital_deployed = tuple(
        _build_component(ComponentMetric.CAPITAL_DEPLOYED, currency,
                         current_metrics.capital_deployed_by_currency.get(currency).minor_units if currency in current_metrics.capital_deployed_by_currency else 0,
                         [m.capital_deployed_by_currency.get(currency).minor_units if currency in m.capital_deployed_by_currency else 0 for m in historical_metrics])
        for currency in sorted(currencies)
    )
    capital_concentration = tuple(
        _build_concentration(currency,
                             current_metrics.capital_concentration_by_currency.get(currency).share if currency in current_metrics.capital_concentration_by_currency else None,
                             [m.capital_concentration_by_currency.get(currency).share if currency in m.capital_concentration_by_currency else None for m in historical_metrics])
        for currency in sorted(currencies)
    )

    voting = (financing_activity, companies_funded, *capital_deployed)
    overall = _aggregate_overall(voting)

    return CapitalSignal(
        market_id=market_id, taxonomy_version=taxonomy_version, as_of=as_of,
        current_window=CapitalWindow(window_start=current_window[0], window_end=current_window[1], metrics=current_metrics),
        historical_windows=tuple(CapitalWindow(window_start=w[0], window_end=w[1], metrics=m) for w, m in zip(historical_windows, historical_metrics)),
        financing_activity=financing_activity, companies_funded=companies_funded, capital_deployed=capital_deployed,
        capital_concentration=capital_concentration, overall=overall,
    )
