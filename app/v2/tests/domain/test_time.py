from datetime import date, datetime, timedelta, timezone, tzinfo

import pytest
from pydantic import ValidationError

from app.v2.domain.errors import InvalidInputError
from app.v2.domain.time import EventTime, EventTimePrecision, ensure_utc

PLUS_530 = timezone(timedelta(hours=5, minutes=30))


class _NoOffset(tzinfo):
    """tzinfo that is attached but knows no offset -- pseudo-aware."""
    def utcoffset(self, dt): return None
    def dst(self, dt): return None
    def tzname(self, dt): return None


# ---------------- ensure_utc

def test_naive_datetime_is_rejected_never_assumed_utc():
    with pytest.raises(InvalidInputError) as info:
        ensure_utc(datetime(2025, 1, 1, 12, 0))
    assert info.value.code == "naive_datetime"


def test_pseudo_aware_datetime_without_an_offset_is_rejected():
    with pytest.raises(InvalidInputError) as info:
        ensure_utc(datetime(2025, 1, 1, tzinfo=_NoOffset()))
    assert info.value.code == "naive_datetime"


@pytest.mark.parametrize("value", ["2025-01-01T00:00:00Z", 1735689600, None, date(2025, 1, 1), b"2025"])
def test_non_datetimes_are_rejected(value):
    with pytest.raises(InvalidInputError) as info:
        ensure_utc(value)
    assert info.value.code == "not_a_datetime"


def test_aware_datetimes_are_accepted_and_normalized_to_utc():
    result = ensure_utc(datetime(2025, 1, 1, 12, 0, tzinfo=PLUS_530))
    assert result == datetime(2025, 1, 1, 6, 30, tzinfo=timezone.utc)
    assert result.utcoffset() == timedelta(0) and result.tzinfo is timezone.utc


def test_utc_input_is_unchanged_and_instants_are_preserved():
    original = datetime(2025, 6, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)
    assert ensure_utc(original) == original
    assert ensure_utc(datetime(2025, 6, 1, 2, tzinfo=timezone(timedelta(hours=2)))) == datetime(2025, 6, 1, tzinfo=timezone.utc)


def test_out_of_range_conversion_is_a_typed_error():
    with pytest.raises(InvalidInputError) as info:
        ensure_utc(datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1))))
    assert info.value.code == "datetime_out_of_range"


# ---------------- EventTime: unknown precision is not fabricated

def test_year_only_is_not_an_exact_date():
    event = EventTime.of_year(2025)
    assert event.precision is EventTimePrecision.YEAR
    assert event.is_exact is False
    assert event.start == datetime(2025, 1, 1, tzinfo=timezone.utc)  # canonical period start, per docstring
    # ...and it is NOT the same fact as "exactly Jan 1 2025 00:00 UTC".
    assert event != EventTime.at_instant(datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert event != EventTime.of_day(2025, 1, 1) != EventTime.of_month(2025, 1)


def test_every_precision_can_be_constructed_from_only_what_is_known():
    assert EventTime.of_month(2025, 3).precision is EventTimePrecision.MONTH
    assert EventTime.of_month(2025, 3).start == datetime(2025, 3, 1, tzinfo=timezone.utc)
    assert EventTime.of_day(2025, 3, 5).precision is EventTimePrecision.DAY
    assert EventTime.of_day(2025, 3, 5).start == datetime(2025, 3, 5, tzinfo=timezone.utc)
    exact = EventTime.at_instant(datetime(2025, 3, 5, 14, 22, 7, 5, tzinfo=PLUS_530))
    assert exact.is_exact and exact.start == datetime(2025, 3, 5, 8, 52, 7, 5, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "precision, start",
    [
        (EventTimePrecision.YEAR, datetime(2025, 3, 1, tzinfo=timezone.utc)),      # a month it does not know
        (EventTimePrecision.YEAR, datetime(2025, 1, 2, tzinfo=timezone.utc)),      # a day it does not know
        (EventTimePrecision.YEAR, datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc)),
        (EventTimePrecision.MONTH, datetime(2025, 3, 5, tzinfo=timezone.utc)),
        (EventTimePrecision.MONTH, datetime(2025, 3, 1, 10, tzinfo=timezone.utc)),
        (EventTimePrecision.DAY, datetime(2025, 3, 5, 10, tzinfo=timezone.utc)),   # a time of day it does not know
        (EventTimePrecision.DAY, datetime(2025, 3, 5, 0, 0, 0, 1, tzinfo=timezone.utc)),
        (EventTimePrecision.DAY, datetime(2025, 3, 5, tzinfo=PLUS_530)),           # = 18:30 UTC the day before
    ],
)
def test_precision_cannot_claim_information_we_do_not_possess(precision, start):
    with pytest.raises(InvalidInputError) as info:
        EventTime(precision=precision, start=start)
    assert info.value.code == "precision_overclaims"


def test_naive_event_start_is_rejected():
    with pytest.raises(InvalidInputError) as info:
        EventTime(precision=EventTimePrecision.INSTANT, start=datetime(2025, 1, 1))
    assert info.value.code == "naive_datetime"


@pytest.mark.parametrize(
    "args",
    [(2025, 13, 1), (2025, 2, 30), (2025, 0, 1), (0, 1, 1), (10000, 1, 1), (2025.0, 1, 1), ("2025", 1, 1), (True, 1, 1), (2025, 1, None)],
)
def test_invalid_calendar_values_are_typed_errors(args):
    with pytest.raises(InvalidInputError) as info:
        EventTime.of_day(*args)
    assert info.value.code == "invalid_calendar_value"


def test_event_time_is_immutable_closed_and_strict():
    event = EventTime.of_year(2025)
    with pytest.raises(ValidationError):
        event.precision = EventTimePrecision.DAY
    with pytest.raises(ValidationError):
        event.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        EventTime(precision=EventTimePrecision.YEAR, start=datetime(2025, 1, 1, tzinfo=timezone.utc), extra="x")
    with pytest.raises(ValidationError):
        EventTime(precision="year", start=datetime(2025, 1, 1, tzinfo=timezone.utc))  # no silent str -> enum coercion
    with pytest.raises(ValidationError):
        EventTime(precision=EventTimePrecision.YEAR, start="2025-01-01T00:00:00+00:00")  # no str -> datetime coercion


def test_equal_event_times_hash_equal():
    assert hash(EventTime.of_year(2025)) == hash(EventTime.of_year(2025))
    assert len({EventTime.of_year(2025), EventTime.of_year(2025), EventTime.of_year(2026)}) == 2
