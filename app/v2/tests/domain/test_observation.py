from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.v2.domain.content import MediaAgreement, MediaType
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.observation import Observation
from app.v2.domain.time import EventTime
from app.v2.tests.domain.factories import GOOD_HASH, OBSERVED, make_observation, observation_kwargs

PLUS_2 = timezone(timedelta(hours=2))


def test_minimal_observation_and_every_optional_field_defaults_to_unknown():
    obs = make_observation()
    assert obs.event_time is None
    assert obs.source_record_identifier is None
    assert obs.declared_media_type is None
    assert Observation.model_fields["event_time"].default is None
    assert Observation.model_fields["declared_media_type"].default is None
    assert Observation.model_fields["source_record_identifier"].default is None


def test_observation_has_exactly_the_evidence_fields_and_no_processing_ai_or_persistence_fields():
    assert set(Observation.model_fields) == {
        "source_key", "source_record_identifier", "observation_type", "event_time", "observed_time",
        "collection_version", "collector_id", "content_hash", "declared_media_type", "sniffed_media_type",
    }
    banned = {"status", "processing_status", "attempt", "attempt_number", "state", "confidence", "score",
              "ai_model", "model", "prompt", "recorded_time", "updated_time", "created_time", "id",
              "raw", "raw_payload", "payload", "content"}
    assert not (set(Observation.model_fields) & banned)
    assert not hasattr(make_observation(), "processing_status")


def test_observation_is_immutable_closed_and_hashable():
    obs = make_observation()
    for field, value in (("content_hash", GOOD_HASH), ("observed_time", OBSERVED), ("event_time", None)):
        with pytest.raises(ValidationError):
            setattr(obs, field, value)
    with pytest.raises(ValidationError):
        make_observation(status="processed")
    with pytest.raises(ValidationError):
        make_observation(processing_status="processed")
    assert hash(obs) == hash(make_observation()) and obs == make_observation()
    assert obs != make_observation(source_record_identifier="x")


# ---------------- time

def test_observed_time_is_required():
    kwargs = observation_kwargs()
    del kwargs["observed_time"]
    with pytest.raises(ValidationError):
        Observation(**kwargs)
    with pytest.raises(ValidationError):
        make_observation(observed_time=None)


def test_naive_observed_time_is_rejected_and_aware_is_normalized_to_utc():
    with pytest.raises(InvalidInputError) as info:
        make_observation(observed_time=datetime(2026, 1, 1, 12))
    assert info.value.code == "naive_datetime"
    obs = make_observation(observed_time=datetime(2026, 1, 1, 12, tzinfo=PLUS_2))
    assert obs.observed_time == datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    assert obs.observed_time.tzinfo is timezone.utc


def test_event_time_is_optional_and_never_manufactured():
    obs = make_observation()
    assert obs.event_time is None
    assert make_observation(event_time=None).event_time is None


@pytest.mark.parametrize(
    "event_time",
    [
        EventTime.of_year(2020),                                           # long before the observation
        EventTime.of_year(2099),                                           # announced, in the future
        EventTime.at_instant(OBSERVED),                                    # the same instant
        EventTime.at_instant(OBSERVED + timedelta(days=30)),
        EventTime.of_month(2026, 9),
    ],
)
def test_event_time_and_observed_time_are_independent(event_time):
    obs = make_observation(event_time=event_time)
    assert obs.event_time == event_time and obs.observed_time == OBSERVED  # neither derived from the other


def test_year_precision_event_is_carried_as_year_precision():
    obs = make_observation(event_time=EventTime.of_year(2025))
    assert obs.event_time.precision.value == "year" and not obs.event_time.is_exact


def test_event_time_must_be_an_event_time_not_a_bare_datetime():
    with pytest.raises(ValidationError):
        make_observation(event_time=datetime(2025, 1, 1, tzinfo=timezone.utc))


# ---------------- validated identifiers

@pytest.mark.parametrize("value", [GOOD_HASH.upper(), GOOD_HASH[:-1], "", "xyz", GOOD_HASH + "a", None, 5])
def test_content_hash_is_validated(value):
    with pytest.raises((InvalidInputError, ValidationError)):
        make_observation(content_hash=value)


@pytest.mark.parametrize("value", ["manual_upload", "manual.v0", "Manual.v1", "manual.v1\n", "", None, 1])
def test_collection_version_is_validated(value):
    with pytest.raises((InvalidInputError, ValidationError)):
        make_observation(collection_version=value)


@pytest.mark.parametrize("value", ["filing_document", "ab", "job_posting_snapshot"])
def test_observation_type_accepts_slugs(value):
    assert make_observation(observation_type=value).observation_type == value


@pytest.mark.parametrize("value", ["", "a", "Filing", "filing document", "1filing", "x" * 65, None])
def test_observation_type_rejects_non_slugs(value):
    with pytest.raises((InvalidInputError, ValidationError)):
        make_observation(observation_type=value)


@pytest.mark.parametrize("value", ["admin:user_2abc", "collector:sec_edgar@v1", "manual.upload/1", "A", "x" * 128])
def test_collector_id_accepts_identities(value):
    assert make_observation(collector_id=value).collector_id == value


@pytest.mark.parametrize("value", ["", " admin", "admin user", "-admin", ".x", "x" * 129, "admïn", "a\nb", None])
def test_collector_id_rejects_malformed(value):
    with pytest.raises((InvalidInputError, ValidationError)):
        make_observation(collector_id=value)


def test_source_record_identifier_is_kept_exactly_and_bounded():
    assert make_observation(source_record_identifier="  0001193125-26-000123 ").source_record_identifier == "  0001193125-26-000123 "
    assert make_observation(source_record_identifier="x" * 512).source_record_identifier == "x" * 512
    for bad in ("", "x" * 513, "a\nb", "a\x00b"):
        with pytest.raises((InvalidInputError, ValidationError)):
            make_observation(source_record_identifier=bad)


def test_source_is_referenced_by_key_and_key_is_validated():
    assert make_observation(source_key="greenhouse_jobs").source_key == "greenhouse_jobs"
    with pytest.raises((InvalidInputError, ValidationError)):
        make_observation(source_key="Not A Key")


# ---------------- media metadata is preserved and never overridden

def test_declared_and_sniffed_media_types_are_preserved_separately():
    obs = make_observation(declared_media_type="text/html", sniffed_media_type=MediaType.APPLICATION_PDF)
    assert obs.declared_media_type == "text/html"
    assert obs.sniffed_media_type is MediaType.APPLICATION_PDF
    assert obs.media_agreement is MediaAgreement.CONFLICT and obs.media_type_mismatch is True


def test_matching_declared_and_sniffed_is_consistent_not_a_mismatch():
    obs = make_observation(declared_media_type="application/json", sniffed_media_type=MediaType.APPLICATION_JSON)
    assert obs.media_agreement is MediaAgreement.CONSISTENT and obs.media_type_mismatch is False


def test_unknown_stays_unknown_and_unverified():
    obs = make_observation(declared_media_type=None, sniffed_media_type=MediaType.UNKNOWN)
    assert obs.declared_media_type is None and obs.sniffed_media_type is MediaType.UNKNOWN
    assert obs.media_agreement is MediaAgreement.UNVERIFIED and obs.media_type_mismatch is False
    declared_only = make_observation(declared_media_type="text/html", sniffed_media_type=MediaType.UNKNOWN)
    assert declared_only.media_agreement is MediaAgreement.UNVERIFIED  # a claim we cannot check is not "consistent"


def test_mismatch_is_derived_so_it_cannot_be_stored_inconsistently():
    assert "media_type_mismatch" not in Observation.model_fields and "media_agreement" not in Observation.model_fields
    with pytest.raises(ValidationError):
        make_observation(media_type_mismatch=False, declared_media_type="text/html", sniffed_media_type=MediaType.APPLICATION_PDF)


@pytest.mark.parametrize("value", ["Text/HTML", "text/html; charset=utf-8", " text/html", "text/html "])
def test_declared_media_type_must_already_be_normalized(value):
    with pytest.raises(InvalidInputError) as info:
        make_observation(declared_media_type=value)
    assert info.value.code == "media_type_not_normalized"


@pytest.mark.parametrize("value", ["nonsense", "text/", "text/html\nX: y"])
def test_malformed_declared_media_type_is_rejected(value):
    with pytest.raises(InvalidInputError):
        make_observation(declared_media_type=value)


def test_sniffed_type_must_be_a_media_type_member():
    with pytest.raises(ValidationError):
        make_observation(sniffed_media_type="text/plain")


# ---------------- evidence identity

def test_dedup_key_is_source_record_and_content_not_time_or_collector():
    a = make_observation(source_record_identifier="rec-1")
    b = make_observation(source_record_identifier="rec-1", observed_time=OBSERVED + timedelta(days=1), collector_id="admin:someone_else")
    c = make_observation(source_record_identifier="rec-1", content_hash="a" * 64)
    d = make_observation(source_record_identifier=None)
    assert a.dedup_key == b.dedup_key and a != b
    assert a.dedup_key != c.dedup_key and a.dedup_key != d.dedup_key
    assert d.dedup_key == ("sec_edgar", None, GOOD_HASH)
