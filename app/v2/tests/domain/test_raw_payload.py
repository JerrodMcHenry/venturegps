"""Pure RawPayload / StoredObservation domain types and payload hashing helpers."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.v2.domain.errors import InvalidInputError, InvariantViolationError, UnsupportedInputError
from app.v2.domain.observation import StoredObservation
from app.v2.domain.payload import MAX_INLINE_PAYLOAD_BYTES, RawPayload, StorageKind
from app.v2.observations.hashing import build_raw_payload, compute_content_hash, verify_raw_payload
from app.v2.tests.domain.factories import make_observation

ABC_HASH = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_the_inline_limit_is_one_mib_defined_once():
    assert MAX_INLINE_PAYLOAD_BYTES == 1048576 == 1024 * 1024


def test_only_inline_storage_exists_in_phase_1():
    assert {k.value for k in StorageKind} == {"inline"}


def test_build_raw_payload_computes_the_hash_and_keeps_the_exact_bytes():
    payload = build_raw_payload(b"abc")
    assert (payload.content_hash, payload.payload_bytes, payload.size_bytes, payload.storage_kind) == (ABC_HASH, b"abc", 3, StorageKind.INLINE)


@pytest.mark.parametrize("data", [bytearray(b"abc"), memoryview(b"abc")])
def test_bytes_like_input_is_stored_as_the_same_bytes(data):
    payload = build_raw_payload(data)
    assert payload.content_hash == ABC_HASH and type(payload.payload_bytes) is bytes


def test_empty_evidence_is_permitted_and_has_the_empty_hash():
    payload = build_raw_payload(b"")
    assert payload.content_hash == EMPTY_HASH and payload.size_bytes == 0


def test_the_size_limit_is_exact_and_oversize_is_rejected_not_truncated():
    at_limit = build_raw_payload(b"x" * MAX_INLINE_PAYLOAD_BYTES)
    assert at_limit.size_bytes == MAX_INLINE_PAYLOAD_BYTES
    with pytest.raises(UnsupportedInputError) as info:
        build_raw_payload(b"x" * (MAX_INLINE_PAYLOAD_BYTES + 1))
    assert info.value.code == "payload_too_large"


@pytest.mark.parametrize("value", ["abc", None, 5, ["abc"]])
def test_text_is_not_silently_encoded(value):
    with pytest.raises(InvalidInputError) as info:
        build_raw_payload(value)
    assert info.value.code == "content_must_be_bytes"


def test_the_payload_model_is_immutable_closed_and_strict():
    payload = build_raw_payload(b"abc")
    with pytest.raises(ValidationError):
        payload.payload_bytes = b"other"
    with pytest.raises(ValidationError):
        RawPayload(content_hash=ABC_HASH, payload_bytes=b"abc", storage_kind=StorageKind.INLINE, extra=1)
    for bad in ("abc", bytearray(b"abc")):
        with pytest.raises(ValidationError):
            RawPayload(content_hash=ABC_HASH, payload_bytes=bad, storage_kind=StorageKind.INLINE)
    with pytest.raises(ValidationError):
        RawPayload(content_hash=ABC_HASH, payload_bytes=b"abc", storage_kind="inline")


def test_verification_passes_for_matching_bytes_and_hash():
    verify_raw_payload(build_raw_payload(b"\x00\xff exact \r\n"))


def test_a_hash_that_does_not_match_the_bytes_fails_loudly_without_echoing_them():
    secret = b"SECRET-PAYLOAD-Zq93"
    mismatched = RawPayload(content_hash="0" * 64, payload_bytes=secret, storage_kind=StorageKind.INLINE)
    with pytest.raises(InvariantViolationError) as info:
        verify_raw_payload(mismatched)
    assert info.value.code == "payload_hash_mismatch" and b"SECRET" not in repr(info.value).encode()


def test_a_malformed_hash_cannot_construct_a_payload():
    for bad in ("0" * 63, "G" * 64, ABC_HASH.upper(), ""):
        with pytest.raises(InvalidInputError):
            RawPayload(content_hash=bad, payload_bytes=b"abc", storage_kind=StorageKind.INLINE)


def test_the_payload_hash_is_the_content_hash_function():
    assert build_raw_payload(b"same").content_hash == compute_content_hash(b"same")


# ---------------- StoredObservation

def test_stored_observation_wraps_an_unchanged_observation():
    obs = make_observation()
    stored = StoredObservation(id=7, source_id=3, observation=obs, recorded_time=datetime(2026, 9, 22, tzinfo=timezone.utc))
    assert stored.observation == obs and (stored.id, stored.source_id) == (7, 3)
    assert set(StoredObservation.model_fields) == {"id", "source_id", "observation", "recorded_time"}  # evidence: no updated_time


def test_recorded_time_is_independent_of_observed_and_event_time():
    obs = make_observation()
    early = StoredObservation(id=1, source_id=1, observation=obs, recorded_time=obs.observed_time - timedelta(days=400))
    late = StoredObservation(id=1, source_id=1, observation=obs, recorded_time=obs.observed_time + timedelta(days=400))
    assert early.recorded_time < obs.observed_time < late.recorded_time  # no ordering is enforced


@pytest.mark.parametrize("bad", [0, -1, "1", None, 1.0, True])
def test_stored_observation_ids_are_positive_integers(bad):
    with pytest.raises(ValidationError):
        StoredObservation(id=bad, source_id=1, observation=make_observation(), recorded_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValidationError):
        StoredObservation(id=1, source_id=bad, observation=make_observation(), recorded_time=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_stored_observation_is_immutable_and_rejects_naive_recorded_time():
    stored = StoredObservation(id=1, source_id=1, observation=make_observation(), recorded_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValidationError):
        stored.recorded_time = datetime(2027, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(InvalidInputError):
        StoredObservation(id=1, source_id=1, observation=make_observation(), recorded_time=datetime(2026, 1, 1))
