"""
The Capital metric engine. PURE: no database, no network, no environment, no AI. Deterministic inputs -> a
deterministic, typed result. See app.v2.repositories.capital_metrics for the query layer that assembles
CapitalEventInput from canonical data and calls compute_capital_metrics().

    canonical FinancingEvents (primary-attributed to a Market under a taxonomy version)
        -> CapitalEventInput (immutable, this module)
        -> compute_capital_metrics()
        -> CapitalMetrics (typed, this module)

WHAT QUALIFIES (decided by the caller/repository, not here -- this module trusts its inputs, but re-derives period
membership itself so the policy is testable without a database):
  - the canonical FinancingEvent's Company has a PRIMARY classification into the requested Market under the
    requested taxonomy version (secondary NEVER attributes Capital; that is enforced upstream, in the query)
  - it is NOT required to have a verified_round_amount, a known stage, or a known financing type: those may be
    absent and the event still counts toward Financing Activity / Companies Funded
  - it IS required to have a usable canonical METRIC DATE inside the requested period (see below); otherwise it is
    excluded, and the exclusion is visible in `diagnostics`, never silently dropped

METRIC DATE POLICY (documented, not fabricated): a FinancingEvent may hold up to three canonical semantic dates
(first_sale_date, filing_date, announcement_date; see app.v2.domain.financing). The metric date is chosen by
PRECEDENCE, never averaged or invented:

    1. announcement_date   the most durable public signal that a financing occurred and roughly when
    2. first_sale_date     the most legally precise date when available, but Form D filings lag or are absent for
                           many rounds and are not always canonically accepted
    3. filing_date         administrative/regulatory; least representative of when capital actually moved, used
                           only as a last resort

`Observation.observed_time` (when VentureGPS's collector saw the evidence) is NEVER used as a financing date: it is
a different clock and mixing them would silently misdate real capital activity. A FinancingEvent with none of the
three canonical dates has no metric date and is excluded from every period-based metric (never assigned a
fabricated date). Period comparison uses EventTime.start -- the canonical UTC instant the source's precision
resolves to (e.g. a year-precision date compares as its Jan 1 00:00 UTC start); the ORIGINAL precision is preserved
on the input and is never itself used to narrow or widen inclusion.

PERIOD: half-open [period_start, period_end) -- period_start is included, period_end is excluded. period_start must
not be after period_end (an equal start/end is a legitimate, always-empty period).

MONEY: Capital Deployed sums ONLY `verified_round_amount` -- never offering_amount, amount_sold or
announced_round_amount (those are candidate-level proposals/evidence, not accepted canonical truth). Amounts are
NEVER summed across currencies (no FX): every money-shaped result is keyed by ISO-4217 currency code, and a period
containing only EUR financings never contributes to a USD total. Arithmetic is exact integer minor-unit addition;
no float appears anywhere in this module.

CONCENTRATION: `largest verified_round_amount / total verified_round_amount`, per currency, expressed EXACTLY as
(largest_minor_units, total_minor_units) rather than a rounded ratio -- `.share` (a `fractions.Fraction`) is exact
and reduces automatically. A currency with no verified capital in the period has NO entry (never a divide-by-zero,
never a fabricated zero).

STAGE DISTRIBUTION: counts only, keyed by the canonical Stage enum (including UNKNOWN for events with no accepted
canonical stage). Shares are deliberately NOT computed here: financing_activity and each count are both integers,
and a share is one exact division a caller can make without this module choosing a rounding policy for it.
"""

from collections.abc import Mapping, Sequence
from uuid import UUID

from pydantic import Field, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.financing import FinancingDateKind, Money, Stage
from app.v2.domain.time import EventTime, UtcDatetime
from app.v2.domain.versions import VersionId

# Precedence, most to least preferred. Documented above; this tuple IS the policy.
METRIC_DATE_PRECEDENCE: tuple[FinancingDateKind, ...] = (
    FinancingDateKind.ANNOUNCEMENT_DATE, FinancingDateKind.FIRST_SALE_DATE, FinancingDateKind.FILING_DATE,
)

# Identifies which version of this methodology (window qualification, date precedence, verified-amount and
# currency policy) produced a CapitalMetrics result -- an additive identifier (Increment 14), not a methodology
# change. A future rule change here must introduce capital_metrics.v2 alongside this, never silently reinterpret
# what a capital_metrics.v1 result meant.
METHODOLOGY_VERSION = "capital_metrics.v1"


def choose_metric_date(dates: Mapping[FinancingDateKind, EventTime]) -> tuple[FinancingDateKind, EventTime] | None:
    """The metric date and which kind produced it, by METRIC_DATE_PRECEDENCE, or None if the event has no usable
    canonical date. Never fabricates a date; never falls back to anything outside `dates`."""
    for kind in METRIC_DATE_PRECEDENCE:
        if kind in dates:
            return kind, dates[kind]
    return None


class CapitalEventInput(DomainModel):
    """One qualifying canonical FinancingEvent, already reduced to exactly what the pure engine needs. `metric_date`
    is None when the event has no usable canonical date (it will be excluded, never fabricated)."""

    financing_event_id: UUID
    company_id: UUID
    metric_date: UtcDatetime | None = None
    metric_date_kind: FinancingDateKind | None = None   # which of the three dates was chosen; None iff metric_date is None
    verified_round_amount: Money | None = None
    stage: Stage = Stage.UNKNOWN

    @model_validator(mode="after")
    def _date_and_kind_are_paired(self) -> "CapitalEventInput":
        if (self.metric_date is None) != (self.metric_date_kind is None):
            raise InvalidInputError("metric_date_kind_mismatch", "metric_date and metric_date_kind must be both present or both absent")
        return self


class CapitalConcentration(DomainModel):
    """largest_minor_units / total_minor_units, kept exact. total_minor_units > 0 is guaranteed by construction:
    a currency with zero verified capital simply has no CapitalConcentration entry."""

    largest_minor_units: int = Field(ge=0)
    total_minor_units: int = Field(gt=0)

    @model_validator(mode="after")
    def _largest_cannot_exceed_total(self) -> "CapitalConcentration":
        if self.largest_minor_units > self.total_minor_units:
            raise InvariantViolationError("concentration_exceeds_total", "the largest amount cannot exceed the total")
        return self

    @property
    def share(self):
        from fractions import Fraction
        return Fraction(self.largest_minor_units, self.total_minor_units)


class CapitalMetricsDiagnostics(DomainModel):
    """Enough coverage information that a consumer never mistakes a partial result for a complete one."""

    events_considered: int = Field(ge=0)              # every primary-attributed canonical event, before period filtering
    events_included: int = Field(ge=0)                 # has a usable metric date AND falls inside [period_start, period_end)
    events_excluded_missing_date: int = Field(ge=0)    # no usable canonical date at all (excluded regardless of period)
    events_excluded_outside_period: int = Field(ge=0)  # has a usable date, but it falls outside the requested period
    events_without_verified_amount: int = Field(ge=0)  # subset of events_included with no verified_round_amount
    events_without_known_stage: int = Field(ge=0)      # subset of events_included with stage == UNKNOWN

    @model_validator(mode="after")
    def _counts_are_internally_consistent(self) -> "CapitalMetricsDiagnostics":
        if self.events_considered != self.events_included + self.events_excluded_missing_date + self.events_excluded_outside_period:
            raise InvariantViolationError("diagnostics_inconsistent", "considered must equal included plus the two exclusion counts")
        if self.events_without_verified_amount > self.events_included or self.events_without_known_stage > self.events_included:
            raise InvariantViolationError("diagnostics_inconsistent", "a per-included-event count cannot exceed events_included")
        return self


class CapitalMetrics(DomainModel):
    """A measurement, not a judgement: no score, no good/bad, no signal classification (Increment 12 stops here)."""

    market_id: UUID
    taxonomy_version: VersionId
    period_start: UtcDatetime
    period_end: UtcDatetime

    financing_activity: int = Field(ge=0)
    companies_funded: int = Field(ge=0)

    capital_deployed_by_currency: dict[str, Money] = {}
    capital_concentration_by_currency: dict[str, CapitalConcentration] = {}
    stage_distribution: dict[Stage, int] = {}

    diagnostics: CapitalMetricsDiagnostics

    @model_validator(mode="after")
    def _period_is_well_formed_and_counts_agree(self) -> "CapitalMetrics":
        if self.period_start > self.period_end:
            raise InvalidInputError("invalid_period", "period_start must not be after period_end")
        if self.financing_activity != self.diagnostics.events_included:
            raise InvariantViolationError("metrics_inconsistent", "financing_activity must equal diagnostics.events_included")
        if self.companies_funded > self.financing_activity:
            raise InvariantViolationError("metrics_inconsistent", "companies_funded cannot exceed financing_activity")
        if sum(self.stage_distribution.values()) not in (0, self.financing_activity):
            raise InvariantViolationError("metrics_inconsistent", "stage_distribution must account for every included event")
        return self


def compute_capital_metrics(
    inputs: Sequence[CapitalEventInput], *, market_id: UUID, taxonomy_version: str, period_start, period_end,
) -> CapitalMetrics:
    """The pure computation. `inputs` should already be exactly the canonical events primary-attributed to
    `market_id` under `taxonomy_version` (any period, any date-availability) -- this function applies the period
    policy itself so it is independently testable."""
    from app.v2.domain.time import ensure_utc

    period_start = ensure_utc(period_start, field="period_start")
    period_end = ensure_utc(period_end, field="period_end")
    if period_start > period_end:
        raise InvalidInputError("invalid_period", "period_start must not be after period_end")

    considered = list(inputs)
    included: list[CapitalEventInput] = []
    missing_date = outside_period = 0
    for event in considered:
        if event.metric_date is None:
            missing_date += 1
        elif period_start <= event.metric_date < period_end:
            included.append(event)
        else:
            outside_period += 1

    without_amount = sum(1 for e in included if e.verified_round_amount is None)
    without_stage = sum(1 for e in included if e.stage is Stage.UNKNOWN)

    deployed: dict[str, int] = {}
    largest: dict[str, int] = {}
    for event in included:
        if event.verified_round_amount is None:
            continue
        money = event.verified_round_amount
        deployed[money.currency_code] = deployed.get(money.currency_code, 0) + money.minor_units
        largest[money.currency_code] = max(largest.get(money.currency_code, 0), money.minor_units)

    stage_counts: dict[Stage, int] = {}
    for event in included:
        stage_counts[event.stage] = stage_counts.get(event.stage, 0) + 1

    return CapitalMetrics(
        market_id=market_id, taxonomy_version=taxonomy_version, period_start=period_start, period_end=period_end,
        financing_activity=len(included), companies_funded=len({e.company_id for e in included}),
        capital_deployed_by_currency={c: Money(currency_code=c, minor_units=m) for c, m in deployed.items()},
        capital_concentration_by_currency={c: CapitalConcentration(largest_minor_units=largest[c], total_minor_units=m)
                                           for c, m in deployed.items()},
        stage_distribution=stage_counts,
        diagnostics=CapitalMetricsDiagnostics(
            events_considered=len(considered), events_included=len(included), events_excluded_missing_date=missing_date,
            events_excluded_outside_period=outside_period, events_without_verified_amount=without_amount,
            events_without_known_stage=without_stage,
        ),
    )
