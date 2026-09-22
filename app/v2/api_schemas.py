"""
Read-only HTTP response schemas for the Capital Intelligence API (Increment 14).

These are plain `pydantic.BaseModel`s, deliberately NOT `app.v2.domain.base.DomainModel`: DomainModel exists to
validate untrusted INPUT (strict, frozen, hides values in errors); these types exist to serialize already-trusted
OUTPUT to JSON, and need ordinary pydantic JSON encoding.

EXACTNESS: every quantity that came from `Money.minor_units` or a `fractions.Fraction` is serialized as a
DECIMAL STRING, never a JSON number and never a float -- large minor-unit amounts can exceed the 2^53
JavaScript-safe-integer limit, and floats cannot represent an exact fraction at all. This rule applies uniformly
to every numeric field derived this way, whether the underlying value is a count or a currency amount, so a
client never has to know which fields are "safe" as a JSON number and which are not: NONE of them are; all are
strings. A `{numerator, denominator}` pair is the lossless representation of a `Fraction` (percentile rank,
concentration share) -- never a rounded decimal.

Stage Distribution always lists every canonical Stage (including `unknown`), zero-filled, so a client never has
to guess whether an absent key means zero or means the field was omitted.
"""

import uuid
from datetime import datetime
from fractions import Fraction

from pydantic import BaseModel

from app.v2.domain.capital_metrics import CapitalMetrics
from app.v2.domain.capital_signal import CapitalComponentSignal, CapitalConcentrationSignal, CapitalSignal, CapitalWindow
from app.v2.domain.financing import Money, Stage
from app.v2.domain.taxonomy import StoredMarket

STAGE_ORDER: tuple[Stage, ...] = (Stage.PRE_SEED, Stage.SEED, Stage.SERIES_A, Stage.SERIES_B, Stage.GROWTH, Stage.UNKNOWN)


def _int_str(value: int) -> str:
    return str(value)


def _ratio(fraction: Fraction) -> "RatioOut":
    return RatioOut(numerator=_int_str(fraction.numerator), denominator=_int_str(fraction.denominator))


def _optional_ratio(fraction: Fraction | None) -> "RatioOut | None":
    return None if fraction is None else _ratio(fraction)


def _money(money: Money) -> "MoneyOut":
    return MoneyOut(currency_code=money.currency_code, minor_units=_int_str(money.minor_units))


class MoneyOut(BaseModel):
    currency_code: str
    minor_units: str   # exact integer, decimal string -- never a JSON number, never a float


class RatioOut(BaseModel):
    """A `fractions.Fraction`, exactly: numerator / denominator. Never rounded to a decimal."""

    numerator: str
    denominator: str


class MarketOut(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str


class MarketListOut(BaseModel):
    markets: list[MarketOut]
    limit: int
    offset: int
    total: int


class MarketDetailOut(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    taxonomy_versions: list[str]   # every taxonomy version currently registered SYSTEM-WIDE, not market-specific


class CapitalConcentrationAmountOut(BaseModel):
    currency_code: str
    largest_minor_units: str
    total_minor_units: str


class CapitalMetricsDiagnosticsOut(BaseModel):
    events_considered: int
    events_included: int
    events_excluded_missing_date: int
    events_excluded_outside_period: int
    events_without_verified_amount: int
    events_without_known_stage: int
    # Increment 14 coverage addition (a genuine count, never a fabricated percentage): how many canonical
    # Companies hold a PRIMARY classification into this market/taxonomy version, regardless of period. Zero here
    # -- unlike zero financing_activity -- means no companies are even classified into this market yet, which is
    # a DIFFERENT situation from "classified companies exist but had no qualifying financings this period".
    classified_company_count: int


class PeriodOut(BaseModel):
    start: datetime
    end: datetime


class CapitalMetricsBodyOut(BaseModel):
    """The reusable measurement body: standalone at the top level of the Metrics response, or embedded as
    `window.metrics` in every window of the Signal response -- one shape, never duplicated logic."""

    financing_activity: int
    companies_funded: int
    capital_deployed: list[MoneyOut]
    capital_concentration: list[CapitalConcentrationAmountOut]
    stage_distribution: dict[str, int]
    diagnostics: CapitalMetricsDiagnosticsOut


def capital_metrics_body(metrics: CapitalMetrics, classified_company_count: int) -> CapitalMetricsBodyOut:
    stages = {s.value: 0 for s in STAGE_ORDER}
    for stage, count in metrics.stage_distribution.items():
        stages[stage.value] = count
    return CapitalMetricsBodyOut(
        financing_activity=metrics.financing_activity,
        companies_funded=metrics.companies_funded,
        capital_deployed=[_money(m) for _, m in sorted(metrics.capital_deployed_by_currency.items())],
        capital_concentration=[
            CapitalConcentrationAmountOut(currency_code=currency, largest_minor_units=_int_str(c.largest_minor_units),
                                          total_minor_units=_int_str(c.total_minor_units))
            for currency, c in sorted(metrics.capital_concentration_by_currency.items())
        ],
        stage_distribution=stages,
        diagnostics=CapitalMetricsDiagnosticsOut(
            events_considered=metrics.diagnostics.events_considered, events_included=metrics.diagnostics.events_included,
            events_excluded_missing_date=metrics.diagnostics.events_excluded_missing_date,
            events_excluded_outside_period=metrics.diagnostics.events_excluded_outside_period,
            events_without_verified_amount=metrics.diagnostics.events_without_verified_amount,
            events_without_known_stage=metrics.diagnostics.events_without_known_stage,
            classified_company_count=classified_company_count,
        ),
    )


class CapitalMetricsMethodologyOut(BaseModel):
    methodology_version: str
    date_policy: str
    attribution_policy: str
    verified_amount_policy: str
    currency_policy: str


CAPITAL_METRICS_METHODOLOGY = CapitalMetricsMethodologyOut(
    methodology_version="capital_metrics.v1",
    date_policy="A FinancingEvent's period date is chosen by precedence: announcement_date, then first_sale_date, "
               "then filing_date. Observation.observed_time (when VentureGPS's collector saw the evidence) is never "
               "used. An event with none of the three canonical dates is excluded, never assigned a fabricated date.",
    attribution_policy="A financing is attributed to a Market only through its Company's PRIMARY classification "
                       "under the requested taxonomy version. SECONDARY classifications never attribute capital, so "
                       "one financing is never double-counted across Markets.",
    verified_amount_policy="Capital Deployed sums only the canonical verified_round_amount explicitly accepted "
                           "through resolution. offering_amount, amount_sold and an unaccepted announced_round_amount "
                           "never count toward it.",
    currency_policy="Amounts are never converted or summed across currencies (no FX). Each currency is reported "
                    "separately.",
)


class CapitalMetricsResponse(CapitalMetricsBodyOut):
    market: MarketOut
    taxonomy_version: str
    period: PeriodOut
    methodology: CapitalMetricsMethodologyOut = CAPITAL_METRICS_METHODOLOGY


def capital_metrics_response(market: StoredMarket, taxonomy_version: str, period_start: datetime, period_end: datetime,
                             metrics: CapitalMetrics, classified_company_count: int) -> CapitalMetricsResponse:
    body = capital_metrics_body(metrics, classified_company_count)
    return CapitalMetricsResponse(market=market_out(market), taxonomy_version=taxonomy_version,
                                  period=PeriodOut(start=period_start, end=period_end), **body.model_dump())


class ComponentSignalOut(BaseModel):
    metric: str
    currency_code: str | None
    current_value: str            # exact integer (count or minor units), decimal string
    historical_values: list[str]  # exactly 8, oldest first, decimal strings
    historical_nonzero_windows: int
    percentile_rank: RatioOut | None
    direction: str
    votes: bool


def component_signal(signal: CapitalComponentSignal) -> ComponentSignalOut:
    return ComponentSignalOut(
        metric=signal.metric.value, currency_code=signal.currency_code, current_value=_int_str(signal.current_value),
        historical_values=[_int_str(v) for v in signal.historical_values],
        historical_nonzero_windows=signal.historical_nonzero_windows, percentile_rank=_optional_ratio(signal.percentile_rank),
        direction=signal.direction.value, votes=signal.votes,
    )


class ConcentrationSignalOut(BaseModel):
    currency_code: str
    current_share: RatioOut | None
    historical_shares: list[RatioOut | None]
    trend: str


def concentration_signal(signal: CapitalConcentrationSignal) -> ConcentrationSignalOut:
    return ConcentrationSignalOut(
        currency_code=signal.currency_code, current_share=_optional_ratio(signal.current_share),
        historical_shares=[_optional_ratio(s) for s in signal.historical_shares], trend=signal.trend.value,
    )


class CapitalWindowOut(BaseModel):
    start: datetime
    end: datetime
    metrics: CapitalMetricsBodyOut


def capital_window(window: CapitalWindow, classified_company_count: int) -> CapitalWindowOut:
    return CapitalWindowOut(start=window.window_start, end=window.window_end,
                            metrics=capital_metrics_body(window.metrics, classified_company_count))


class CapitalSignalMethodologyOut(BaseModel):
    methodology_version: str
    date_policy: str
    attribution_policy: str
    verified_amount_policy: str
    currency_policy: str
    historical_window_policy: str
    minimum_history_rule: str
    comparison_method: str
    concentration_voting_policy: str
    limitations: str


CAPITAL_SIGNAL_METHODOLOGY = CapitalSignalMethodologyOut(
    methodology_version="capital_signal.v1",
    date_policy=CAPITAL_METRICS_METHODOLOGY.date_policy,
    attribution_policy=CAPITAL_METRICS_METHODOLOGY.attribution_policy,
    verified_amount_policy=CAPITAL_METRICS_METHODOLOGY.verified_amount_policy,
    currency_policy=CAPITAL_METRICS_METHODOLOGY.currency_policy,
    historical_window_policy="The current window is the trailing 30 days ending at as_of, [as_of-30d, as_of). The "
                             "historical baseline is exactly 8 prior 30-day windows of the same Market, immediately "
                             "preceding it with no gap and no overlap; no historical window can ever contain data on "
                             "or after as_of.",
    minimum_history_rule="A component is compared only if at least 3 of its 8 historical windows are non-zero; "
                         "otherwise its direction is insufficient_data, never silently reported as stable.",
    comparison_method="Percentile rank (mean-rank tie handling, computed as an exact fraction) of the current value "
                      "among the 8 historical values. Chosen for robustness to outliers and to avoid any arbitrary "
                      "growth-rate threshold.",
    concentration_voting_policy="Capital Concentration is contextual only and never votes in the overall signal: a "
                                "rise in concentration is not itself positive Capital activity, nor is a fall "
                                "negative.",
    limitations="This methodology (capital_signal.v1) is provisional: window duration, minimum-history thresholds "
               "and direction bands are documented, deterministic choices, not a claim about statistical "
               "significance, and are not a forecast, valuation or investment recommendation.",
)


class CapitalSignalResponse(BaseModel):
    market: MarketOut
    taxonomy_version: str
    as_of: datetime
    methodology_version: str

    current_window: CapitalWindowOut
    historical_windows: list[CapitalWindowOut]

    financing_activity: ComponentSignalOut
    companies_funded: ComponentSignalOut
    capital_deployed: list[ComponentSignalOut]
    capital_concentration: list[ConcentrationSignalOut]

    overall: str
    methodology: CapitalSignalMethodologyOut = CAPITAL_SIGNAL_METHODOLOGY


def market_out(market: StoredMarket) -> MarketOut:
    return MarketOut(id=market.id, slug=market.slug, display_name=market.display_name)


def capital_signal_response(market: StoredMarket, signal: CapitalSignal, classified_company_count: int) -> CapitalSignalResponse:
    return CapitalSignalResponse(
        market=market_out(market), taxonomy_version=signal.taxonomy_version, as_of=signal.as_of,
        methodology_version=signal.methodology_version,
        current_window=capital_window(signal.current_window, classified_company_count),
        historical_windows=[capital_window(w, classified_company_count) for w in signal.historical_windows],
        financing_activity=component_signal(signal.financing_activity), companies_funded=component_signal(signal.companies_funded),
        capital_deployed=[component_signal(c) for c in signal.capital_deployed],
        capital_concentration=[concentration_signal(c) for c in signal.capital_concentration],
        overall=signal.overall.value,
    )
