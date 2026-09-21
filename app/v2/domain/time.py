"""
Temporal semantics. Four DIFFERENT clocks, deliberately not interchangeable:

  event_time     when the real-world event happened, IF KNOWN, with an explicit
                 precision (EventTime below). Unknown is represented by None.
  observed_time  when VentureGPS's collection observed the information
                 (a UTC datetime, always explicit on an Observation).
  recorded_time  when VentureGPS persisted the record. Assigned by the
                 database, never accepted from source content, so it is not
                 part of the pure Observation.
  updated_time   only for objects that are legitimately mutable (later, e.g.
                 a Source's metadata). Not used by immutable evidence.

All datetimes are timezone-aware and normalized to UTC. Naive datetimes are
rejected, never guessed to be UTC. Nothing here compares event_time with
observed_time: an event can be known to be later than its observation
(announced), earlier, or unknown.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, ValidationInfo, model_validator

from app.v2.domain.base import DomainModel
from app.v2.domain.errors import InvalidInputError


def ensure_utc(value: object, *, field: str = "datetime") -> datetime:
    """Return `value` as a UTC-aware datetime, or raise InvalidInputError.
    `field` is a developer-supplied label, never untrusted content."""
    if not isinstance(value, datetime):
        raise InvalidInputError("not_a_datetime", f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidInputError("naive_datetime", f"{field} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise InvalidInputError("datetime_out_of_range", f"{field} cannot be represented in UTC") from None


def _utc_validator(value: object, info: ValidationInfo) -> datetime:
    return ensure_utc(value, field=info.field_name or "datetime")


UtcDatetime = Annotated[datetime, AfterValidator(_utc_validator)]


class EventTimePrecision(str, Enum):
    INSTANT = "instant"  # an exact timestamp
    DAY = "day"
    MONTH = "month"
    YEAR = "year"


class EventTime(DomainModel):
    """When an event happened, with the precision we actually know.

    `start` is the canonical START OF THE PERIOD the source described, in UTC.
    It is NOT the event's date unless precision is INSTANT: for YEAR precision
    `start` is Jan 1 00:00 UTC because that is where the year-long period
    begins, and `precision` says the event date within it is unknown.

    A value that claims more detail than its precision allows is rejected
    (YEAR with a March start, DAY with a time of day), so an EventTime can
    never assert information the source did not give. Build them with the
    constructors, which take only what is actually known.
    """

    precision: EventTimePrecision
    start: UtcDatetime

    @model_validator(mode="after")
    def _start_carries_no_finer_detail_than_precision(self) -> "EventTime":
        s = self.start
        if self.precision is EventTimePrecision.INSTANT:
            return self
        at_midnight = (s.hour, s.minute, s.second, s.microsecond) == (0, 0, 0, 0)
        canonical = {
            EventTimePrecision.DAY: at_midnight,
            EventTimePrecision.MONTH: at_midnight and s.day == 1,
            EventTimePrecision.YEAR: at_midnight and s.day == 1 and s.month == 1,
        }[self.precision]
        if not canonical:
            raise InvalidInputError(
                "precision_overclaims", "start carries finer detail than the stated precision"
            )
        return self

    @property
    def is_exact(self) -> bool:
        return self.precision is EventTimePrecision.INSTANT

    @classmethod
    def at_instant(cls, instant: datetime) -> "EventTime":
        return cls(precision=EventTimePrecision.INSTANT, start=instant)

    @classmethod
    def of_day(cls, year: int, month: int, day: int) -> "EventTime":
        return cls(precision=EventTimePrecision.DAY, start=_utc_date(year, month, day))

    @classmethod
    def of_month(cls, year: int, month: int) -> "EventTime":
        return cls(precision=EventTimePrecision.MONTH, start=_utc_date(year, month, 1))

    @classmethod
    def of_year(cls, year: int) -> "EventTime":
        return cls(precision=EventTimePrecision.YEAR, start=_utc_date(year, 1, 1))


def _utc_date(year: int, month: int, day: int) -> datetime:
    for part in (year, month, day):
        if type(part) is not int:
            raise InvalidInputError("invalid_calendar_value", "year, month and day must be integers")
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        raise InvalidInputError("invalid_calendar_value", "not a valid calendar date") from None
