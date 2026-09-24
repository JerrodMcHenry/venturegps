"""StoredSource: the persisted wrapper around the (unchanged) Source model."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.source import CollectionMethod, Source, SourceType, StoredSource

T0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def make_source(**overrides):
    base = dict(source_key="sec_edgar", name="SEC EDGAR", source_type=SourceType.GOVERNMENT_REGULATORY,
                collection_method=CollectionMethod.API, is_active=True)
    base.update(overrides)
    return Source(**base)


def make_stored(**overrides):
    base = dict(id=1, source=make_source(), recorded_time=T0, updated_time=T0)
    base.update(overrides)
    return StoredSource(**base)


def test_the_accepted_source_model_is_unchanged():
    # Revision 0011 (Increment 18.5) intentionally added is_test: bool = False -- additive, defaulted, every
    # existing call site unaffected. This closed-set assertion is updated to include it on purpose.
    assert set(Source.model_fields) == {"source_key", "name", "source_type", "collection_method", "url", "is_active", "is_test"}
    assert "id" not in Source.model_fields and "created_at" not in Source.model_fields


def test_stored_source_wraps_a_source_with_id_and_times():
    stored = make_stored(id=42, updated_time=T0 + timedelta(hours=1))
    assert stored.id == 42 and stored.source == make_source()
    assert stored.updated_time > stored.recorded_time


def test_updated_time_may_equal_recorded_time_but_never_precede_it():
    assert make_stored(updated_time=T0).updated_time == T0
    with pytest.raises(InvariantViolationError) as info:
        make_stored(updated_time=T0 - timedelta(seconds=1))
    assert info.value.code == "updated_before_recorded"


@pytest.mark.parametrize("bad", [0, -1, "1", 1.0, None, True])
def test_id_must_be_a_positive_integer(bad):
    with pytest.raises(ValidationError):
        make_stored(id=bad)


def test_times_must_be_aware_and_are_normalized_to_utc():
    with pytest.raises(InvalidInputError) as info:
        make_stored(recorded_time=datetime(2026, 1, 1), updated_time=datetime(2026, 1, 2))
    assert info.value.code == "naive_datetime"
    plus2 = timezone(timedelta(hours=2))
    stored = make_stored(recorded_time=datetime(2026, 9, 21, 14, tzinfo=plus2), updated_time=datetime(2026, 9, 21, 15, tzinfo=plus2))
    assert stored.recorded_time == T0 and stored.recorded_time.tzinfo is timezone.utc


def test_stored_source_is_immutable_closed_and_requires_a_real_source():
    stored = make_stored()
    with pytest.raises(ValidationError):
        stored.id = 2
    with pytest.raises(ValidationError):
        make_stored(unexpected=1)
    with pytest.raises(ValidationError):
        make_stored(source={"source_key": "sec_edgar"})
    assert hash(stored) == hash(make_stored())
