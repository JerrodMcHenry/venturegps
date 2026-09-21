"""The ingestion command: only what is known at the collection boundary; nothing computed can be supplied."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.v2.domain.errors import InvalidInputError
from app.v2.domain.time import EventTime
from app.v2.ingestion.errors import SourceInactiveError
from app.v2.ingestion.models import IngestionCommand
from app.v2.domain.errors import DomainError

OBSERVED = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def make_command(**overrides):
    base = dict(source_key="sec_edgar", observation_type="filing_document", observed_time=OBSERVED,
                collection_version="manual_upload.v1", collector_id="admin:user_2abc",
                payload_bytes=b"payload", acquisition_key="run_1")
    base.update(overrides)
    return IngestionCommand(**base)


def test_the_command_carries_exactly_the_collection_boundary_facts():
    assert set(IngestionCommand.model_fields) == {
        "source_key", "source_record_identifier", "observation_type", "event_time", "observed_time",
        "collection_version", "collector_id", "declared_media_type", "payload_bytes", "acquisition_key",
    }


def test_optional_facts_default_to_unknown():
    command = make_command()
    assert command.source_record_identifier is None and command.event_time is None and command.declared_media_type is None


@pytest.mark.parametrize(
    "field, value",
    [
        ("content_hash", "0" * 64),                # computed by the service, never supplied
        ("sniffed_media_type", "text/plain"),      # ditto
        ("recorded_time", OBSERVED),               # database-assigned
        ("processing_status", "processed"),
        ("ai_summary", "the company is X"),
        ("company_id", 7),
        ("source_id", 1),
    ],
)
def test_computed_or_out_of_scope_facts_cannot_be_supplied(field, value):
    with pytest.raises(ValidationError):
        make_command(**{field: value})


def test_payload_must_be_exact_bytes_never_text():
    for bad in ("text", bytearray(b"x"), None, 5):
        with pytest.raises(ValidationError):
            make_command(payload_bytes=bad)
    assert make_command(payload_bytes=b"").payload_bytes == b""  # empty evidence is still evidence


def test_the_payload_is_not_echoed_by_repr():
    secret = b"SECRET-PAYLOAD-Zq93"
    command = make_command(payload_bytes=secret)
    assert "SECRET" not in repr(command) and "SECRET" not in str(command)


def test_observed_time_is_required_aware_and_normalized():
    with pytest.raises(InvalidInputError):
        make_command(observed_time=datetime(2026, 1, 1))
    assert make_command(observed_time=datetime(2026, 9, 21, 14, tzinfo=timezone(timedelta(hours=2)))).observed_time == OBSERVED


def test_field_validators_are_the_accepted_domain_ones():
    for bad in ({"source_key": "Bad Key"}, {"observation_type": "Filing"}, {"collection_version": "manual"},
                {"collector_id": "bad id"}, {"acquisition_key": "bad key"}, {"source_record_identifier": ""}):
        with pytest.raises((InvalidInputError, ValidationError)):
            make_command(**bad)


def test_event_time_keeps_its_precision():
    assert make_command(event_time=EventTime.of_year(2025)).event_time.precision.value == "year"
    with pytest.raises(ValidationError):
        make_command(event_time=datetime(2025, 1, 1, tzinfo=timezone.utc))  # a bare datetime would hide the precision


def test_command_is_immutable():
    with pytest.raises(ValidationError):
        make_command().payload_bytes = b"other"


def test_source_inactive_is_a_typed_domain_error():
    assert issubclass(SourceInactiveError, DomainError)
    error = SourceInactiveError("source_inactive", "static")
    assert error.code == "source_inactive"
