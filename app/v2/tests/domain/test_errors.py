from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.v2.domain import content, observation, processing, source, versions
from app.v2.domain.errors import (
    DomainError,
    InvalidInputError,
    InvariantViolationError,
    UnsupportedInputError,
    as_domain_error,
)
from app.v2.domain.observation import Observation
from app.v2.domain.processing import ProcessingStatus
from app.v2.domain.source import Source
from app.v2.domain.time import EventTime, ensure_utc
from app.v2.observations import hashing, media
from app.v2.tests.domain.factories import make_observation

SECRET = "SECRET-PAYLOAD-Zq93"


def test_hierarchy_has_three_distinct_kinds():
    for kind in (InvalidInputError, UnsupportedInputError, InvariantViolationError):
        assert issubclass(kind, DomainError)
    assert not issubclass(InvalidInputError, UnsupportedInputError)
    assert not issubclass(UnsupportedInputError, InvariantViolationError)
    assert not issubclass(DomainError, ValueError)  # so pydantic does not swallow them into ValidationError


def test_errors_carry_a_stable_code_and_message():
    error = InvalidInputError("some_code", "static message")
    assert (error.code, error.message) == ("some_code", "static message")
    assert str(error) == "some_code: static message"


def test_the_three_kinds_are_actually_used_for_their_purpose():
    with pytest.raises(InvalidInputError):
        versions.validate_version_id("bad")
    with pytest.raises(UnsupportedInputError):
        source.validate_source_url("ftp://example.com/x")
    with pytest.raises(InvariantViolationError):
        processing.assert_transition(ProcessingStatus.FAILED, ProcessingStatus.PROCESSING)


VALIDATORS = [
    versions.validate_version_id,
    content.validate_content_hash,
    content.normalize_declared_media_type,
    source.validate_source_key,
    source.validate_source_name,
    source.validate_source_url,
    observation.validate_observation_type,
    observation.validate_collector_id,
    observation.validate_source_record_identifier,
    ensure_utc,
    hashing.compute_content_hash,
    media.sniff_media_type,
]


@pytest.mark.parametrize("validator", VALIDATORS, ids=lambda f: f.__name__)
# Each value is invalid for every validator below (NUL/newline), yet carries the secret.
@pytest.mark.parametrize("hostile", [f"{SECRET}\n\x00", f"https://user:{SECRET}@evil.example/{SECRET}\x00", (SECRET * 200) + "\x00"])
def test_error_messages_never_echo_the_offending_value(validator, hostile):
    with pytest.raises(DomainError) as info:
        validator(hostile)
    for text in (str(info.value), repr(info.value), info.value.message, info.value.code, *map(str, info.value.args)):
        assert SECRET not in text


def test_pydantic_structural_errors_do_not_echo_input_values():
    with pytest.raises(ValidationError) as info:
        Source(source_key=SECRET.encode(), name=SECRET.encode(), source_type=SECRET, collection_method=SECRET, is_active=SECRET)
    assert SECRET not in str(info.value)
    with pytest.raises(ValidationError) as info:
        EventTime(precision=SECRET, start=SECRET)
    assert SECRET not in str(info.value)


def test_as_domain_error_keeps_only_field_paths_and_kinds():
    with pytest.raises(ValidationError) as info:
        Source(source_key=SECRET.encode(), name="ok", source_type=SECRET, collection_method=SECRET, is_active=True, **{SECRET + "_key": SECRET})
    converted = as_domain_error(info.value)
    assert isinstance(converted, InvalidInputError) and converted.code == "invalid_structure"
    assert SECRET not in str(converted)
    assert "source_key" in converted.message


def test_missing_fields_convert_to_invalid_input():
    with pytest.raises(ValidationError) as info:
        Observation()
    assert "observed_time" in as_domain_error(info.value).message


def test_naive_datetime_in_a_model_field_is_a_domain_error_not_hidden():
    with pytest.raises(InvalidInputError):
        make_observation(observed_time=datetime(2025, 1, 1))
