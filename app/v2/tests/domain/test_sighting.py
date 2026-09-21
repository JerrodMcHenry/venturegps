"""Pure Sighting domain types."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.v2.domain.errors import InvalidInputError
from app.v2.domain.sighting import Sighting, StoredSighting, validate_acquisition_key

T0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def make_sighting(**overrides):
    base = dict(observed_time=T0, collector_id="admin:user_2abc", collection_version="manual_upload.v1", acquisition_key="run_1")
    base.update(overrides)
    return Sighting(**base)


@pytest.mark.parametrize("key", ["run_1", "A", "sec_edgar:2026-09-21T10:00Z:run42", "a.b-c_d/e@f=g+h", "x" * 128])
def test_valid_acquisition_keys(key):
    assert validate_acquisition_key(key) == key


@pytest.mark.parametrize("key", ["", "-lead", ".lead", "has space", "tab\there", "new\nline", "x" * 129, "café", "a#b", None, 5, b"run"])
def test_invalid_acquisition_keys(key):
    with pytest.raises(InvalidInputError) as info:
        validate_acquisition_key(key)
    assert info.value.code == "invalid_acquisition_key"


def test_a_sighting_has_only_acquisition_facts():
    assert set(Sighting.model_fields) == {"observed_time", "collector_id", "collection_version", "acquisition_key"}
    assert set(StoredSighting.model_fields) == {"id", "observation_id", "sighting", "recorded_time"}
    for name in list(Sighting.model_fields) + list(StoredSighting.model_fields):
        assert not any(w in name for w in ("status", "payload", "bytes", "hash", "source", "ai_", "score", "company", "updated"))


def test_observed_time_is_required_aware_and_normalized():
    with pytest.raises(ValidationError):
        Sighting(collector_id="admin:x", collection_version="manual_upload.v1", acquisition_key="k")
    with pytest.raises(InvalidInputError) as info:
        make_sighting(observed_time=datetime(2026, 1, 1))
    assert info.value.code == "naive_datetime"
    s = make_sighting(observed_time=datetime(2026, 9, 21, 14, tzinfo=timezone(timedelta(hours=2))))
    assert s.observed_time == T0 and s.observed_time.tzinfo is timezone.utc


def test_collector_and_version_reuse_the_accepted_validators():
    for bad in ({"collector_id": "bad id"}, {"collection_version": "manual_upload"}, {"acquisition_key": ""}):
        with pytest.raises((InvalidInputError, ValidationError)):
            make_sighting(**bad)


def test_sighting_is_immutable_closed_and_hashable():
    s = make_sighting()
    with pytest.raises(ValidationError):
        s.observed_time = T0
    with pytest.raises(ValidationError):
        make_sighting(recorded_time=T0)          # recorded_time is not something a caller supplies
    with pytest.raises(ValidationError):
        make_sighting(content_hash="0" * 64)     # nor is anything about the payload
    assert hash(s) == hash(make_sighting()) and s != make_sighting(acquisition_key="run_2")


def test_stored_sighting_recorded_time_is_independent_of_observed_time():
    s = make_sighting()
    early = StoredSighting(id=1, observation_id=1, sighting=s, recorded_time=T0 - timedelta(days=9))
    late = StoredSighting(id=1, observation_id=1, sighting=s, recorded_time=T0 + timedelta(days=9))
    assert early.recorded_time < s.observed_time < late.recorded_time


@pytest.mark.parametrize("bad", [0, -1, "1", None, 1.0, True])
def test_stored_sighting_ids_are_positive_integers(bad):
    with pytest.raises(ValidationError):
        StoredSighting(id=bad, observation_id=1, sighting=make_sighting(), recorded_time=T0)
    with pytest.raises(ValidationError):
        StoredSighting(id=1, observation_id=bad, sighting=make_sighting(), recorded_time=T0)
