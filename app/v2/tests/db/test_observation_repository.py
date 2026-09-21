"""Observation persistence: evidence round trip, temporal mapping, dedup identity, lineage."""

import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.v2.domain.content import MediaAgreement, MediaType
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.observation import Observation, StoredObservation
from app.v2.domain.time import EventTime, EventTimePrecision
from app.v2.repositories import observations as repo
from app.v2.repositories.errors import NotFoundError
from app.v2.tests.db.evidence_helpers import (
    OBSERVED,
    count,
    fetch_row,
    make_observation,
    register_source,
    store_payload,
    tamper_payload,
)

pytestmark = pytest.mark.db

PLUS_2 = timezone(timedelta(hours=2))


@pytest.fixture
def world(migrated_db):
    """A registered source and a stored payload."""
    source = register_source(migrated_db)
    return migrated_db, source, store_payload(migrated_db, b"exact evidence bytes")


# ---------------- persistence and round trip

def test_a_valid_observation_persists_and_round_trips_into_the_domain_model(world):
    db, source, digest = world
    original = make_observation(
        digest, source_record_identifier="0001193125-26-000123", event_time=EventTime.of_month(2026, 8),
        declared_media_type="text/html", sniffed_media_type=MediaType.TEXT_HTML,
        collection_version="sec_feed.v3", collector_id="collector:sec_edgar@v1",
    )
    result = repo.store_observation(db, original)
    assert result.created is True
    stored = result.stored
    assert isinstance(stored, StoredObservation) and stored.observation == original
    assert stored.source_id == source.id and stored.id >= 1
    assert repo.get_observation_by_id(db, stored.id) == stored


def test_collection_version_collector_and_media_metadata_are_preserved(world):
    db, _, digest = world
    obs = make_observation(digest, collection_version="manual_upload.v12", collector_id="admin:user_2abc",
                           declared_media_type="application/json", sniffed_media_type=MediaType.TEXT_PLAIN)
    loaded = repo.store_observation(db, obs).stored.observation
    assert (loaded.collection_version, loaded.collector_id) == ("manual_upload.v12", "admin:user_2abc")
    assert (loaded.declared_media_type, loaded.sniffed_media_type) == ("application/json", MediaType.TEXT_PLAIN)


def test_media_mismatch_is_derived_from_the_stored_values_not_stored(world):
    db, _, digest = world
    conflict = repo.store_observation(db, make_observation(digest, source_record_identifier="a", declared_media_type="application/pdf",
                                                           sniffed_media_type=MediaType.TEXT_HTML)).stored.observation
    assert conflict.media_agreement is MediaAgreement.CONFLICT and conflict.media_type_mismatch is True
    unknown = repo.store_observation(db, make_observation(digest, source_record_identifier="b", declared_media_type="text/html",
                                                          sniffed_media_type=MediaType.UNKNOWN)).stored.observation
    assert unknown.media_agreement is MediaAgreement.UNVERIFIED and unknown.media_type_mismatch is False
    row = fetch_row(db, "observation", "source_record_identifier = 'a'", {})
    assert not {"media_agreement", "media_type_mismatch"} & set(row)


def test_a_missing_observation_is_none(migrated_db):
    assert repo.get_observation_by_id(migrated_db, 99999) is None
    assert repo.find_observation(migrated_db, "sec_edgar", None, "0" * 64) is None


@pytest.mark.parametrize("bad", [0, -1, "1", None, True, 1.0])
def test_get_by_id_validates_its_argument(migrated_db, bad):
    with pytest.raises(InvalidInputError):
        repo.get_observation_by_id(migrated_db, bad)


def test_store_requires_an_observation(world):
    with pytest.raises(InvalidInputError):
        repo.store_observation(world[0], {"source_key": "sec_edgar"})


# ---------------- source and payload relationships

def test_an_unregistered_source_is_reported_as_not_found(world):
    db, _, digest = world
    with pytest.raises(NotFoundError) as info:
        repo.store_observation(db, make_observation(digest, source_key="unregistered_source"))
    assert info.value.code == "source_not_found" and count(db, "observation") == 0


def test_a_missing_payload_is_reported_as_not_found_and_stores_nothing(world):
    db, _, _ = world
    with pytest.raises(NotFoundError) as info:
        repo.store_observation(db, make_observation("a" * 64))
    assert info.value.code == "raw_payload_not_found" and count(db, "observation") == 0


# ---------------- temporal semantics

def test_unknown_event_time_persists_as_null_and_reads_back_as_none(world):
    db, _, digest = world
    stored = repo.store_observation(db, make_observation(digest)).stored
    assert stored.observation.event_time is None
    row = fetch_row(db, "observation", "id = :i", {"i": stored.id})
    assert row["event_time"] is None and row["event_time_precision"] is None


def test_exact_event_time_persists_with_microseconds_and_normalized_to_utc(world):
    db, _, digest = world
    event = EventTime.at_instant(datetime(2026, 3, 5, 14, 22, 7, 123456, tzinfo=PLUS_2))
    stored = repo.store_observation(db, make_observation(digest, event_time=event)).stored
    assert stored.observation.event_time == event
    assert stored.observation.event_time.start == datetime(2026, 3, 5, 12, 22, 7, 123456, tzinfo=timezone.utc)
    assert fetch_row(db, "observation", "id = :i", {"i": stored.id})["event_time_precision"] == "instant"


@pytest.mark.parametrize(
    "event, precision, start",
    [
        (EventTime.of_day(2025, 3, 5), "day", datetime(2025, 3, 5, tzinfo=timezone.utc)),
        (EventTime.of_month(2025, 3), "month", datetime(2025, 3, 1, tzinfo=timezone.utc)),
        (EventTime.of_year(2025), "year", datetime(2025, 1, 1, tzinfo=timezone.utc)),
    ],
)
def test_day_month_and_year_precision_persist_with_their_precision(world, event, precision, start):
    db, _, digest = world
    stored = repo.store_observation(db, make_observation(digest, event_time=event)).stored
    row = fetch_row(db, "observation", "id = :i", {"i": stored.id})
    assert (row["event_time_precision"], row["event_time"]) == (precision, start)
    loaded = repo.get_observation_by_id(db, stored.id).observation.event_time
    assert loaded == event and loaded.precision is EventTimePrecision(precision) and loaded.is_exact is False


def test_a_year_only_event_is_still_year_precision_after_storage_not_a_january_first(world):
    db, _, digest = world
    stored = repo.store_observation(db, make_observation(digest, event_time=EventTime.of_year(2025))).stored
    assert stored.observation.event_time != EventTime.at_instant(datetime(2025, 1, 1, tzinfo=timezone.utc))


def test_observed_time_is_preserved_and_normalized_to_utc(world):
    db, _, digest = world
    stored = repo.store_observation(db, make_observation(digest, observed_time=datetime(2026, 9, 21, 14, 0, 0, 500, tzinfo=PLUS_2))).stored
    assert stored.observation.observed_time == datetime(2026, 9, 21, 12, 0, 0, 500, tzinfo=timezone.utc)
    assert stored.observation.observed_time.tzinfo is timezone.utc


def test_recorded_time_is_database_assigned_and_independent_of_the_other_times(world):
    db, _, digest = world
    long_ago = datetime(2001, 1, 1, tzinfo=timezone.utc)
    stored = repo.store_observation(db, make_observation(digest, observed_time=long_ago, event_time=EventTime.of_year(1999))).stored
    assert stored.recorded_time > long_ago and stored.recorded_time.tzinfo is timezone.utc
    assert abs(datetime.now(timezone.utc) - stored.recorded_time) < timedelta(minutes=5)
    assert "recorded_time" not in inspect.signature(repo.store_observation).parameters and "recorded_time" not in Observation.model_fields


@pytest.mark.parametrize("years_apart", [-30, 0, 30])
def test_event_time_is_not_required_to_precede_observed_time(world, years_apart):
    db, _, digest = world
    event = EventTime.at_instant(OBSERVED + timedelta(days=365 * years_apart))
    stored = repo.store_observation(db, make_observation(digest, event_time=event, source_record_identifier=str(years_apart))).stored
    assert stored.observation.event_time == event and stored.observation.observed_time == OBSERVED


# ---------------- no processing state, no AI, no interpretation

def test_the_observation_model_and_table_carry_no_processing_ai_or_company_fields(world):
    db, _, digest = world
    stored = repo.store_observation(db, make_observation(digest)).stored
    row = fetch_row(db, "observation", "id = :i", {"i": stored.id})
    assert set(row) == {"id", "source_id", "source_record_identifier", "observation_type", "event_time", "event_time_precision",
                        "observed_time", "recorded_time", "collection_version", "collector_id", "content_hash",
                        "declared_media_type", "sniffed_media_type"}
    assert not hasattr(stored, "processing_status") and not hasattr(stored.observation, "processing_status")


# ---------------- dedup identity

def test_the_same_dedup_identity_returns_the_same_unmodified_observation(world):
    db, _, digest = world
    first = repo.store_observation(db, make_observation(digest, source_record_identifier="rec-1"))
    again = repo.store_observation(db, make_observation(
        digest, source_record_identifier="rec-1", observed_time=OBSERVED + timedelta(days=1), collector_id="admin:someone_else"))
    assert (first.created, again.created) == (True, False)
    assert again.stored == first.stored                       # the existing evidence, untouched
    assert again.stored.observation.observed_time == OBSERVED  # the later acquisition did not overwrite it
    assert count(db, "observation") == 1


def test_the_same_payload_from_a_different_source_is_a_different_observation(world):
    db, source, digest = world
    other = register_source(db, "greenhouse_jobs")
    a = repo.store_observation(db, make_observation(digest, source_record_identifier="rec-1")).stored
    b = repo.store_observation(db, make_observation(digest, source_key="greenhouse_jobs", source_record_identifier="rec-1")).stored
    assert a.id != b.id and {a.source_id, b.source_id} == {source.id, other.id}
    assert count(db, "raw_payload") == 1  # one shared payload, two observations


def test_the_same_source_with_a_different_record_identifier_is_a_different_observation(world):
    db, _, digest = world
    a = repo.store_observation(db, make_observation(digest, source_record_identifier="rec-1")).stored
    b = repo.store_observation(db, make_observation(digest, source_record_identifier="rec-2")).stored
    assert a.id != b.id


def test_the_same_source_and_record_identifier_with_changed_payload_is_a_different_observation(world):
    db, _, digest = world
    changed = store_payload(db, b"exact evidence bytes, revised")
    a = repo.store_observation(db, make_observation(digest, source_record_identifier="rec-1")).stored
    b = repo.store_observation(db, make_observation(changed, source_record_identifier="rec-1")).stored
    assert a.id != b.id and count(db, "observation") == 2  # both states of the record are kept


def test_no_record_identifier_is_deterministic_same_source_same_bytes_is_one_observation(world):
    db, _, digest = world
    first = repo.store_observation(db, make_observation(digest, source_record_identifier=None))
    again = repo.store_observation(db, make_observation(digest, source_record_identifier=None, observed_time=OBSERVED + timedelta(hours=1)))
    assert (first.created, again.created) == (True, False) and again.stored.id == first.stored.id
    assert count(db, "observation") == 1


def test_none_is_a_value_it_never_equals_a_present_identifier_nor_another_sources_none(world):
    db, _, digest = world
    register_source(db, "greenhouse_jobs")
    none_a = repo.store_observation(db, make_observation(digest, source_record_identifier=None)).stored
    with_id = repo.store_observation(db, make_observation(digest, source_record_identifier="rec-1")).stored
    none_other_source = repo.store_observation(db, make_observation(digest, source_key="greenhouse_jobs", source_record_identifier=None)).stored
    assert len({none_a.id, with_id.id, none_other_source.id}) == 3


def test_none_with_different_bytes_is_a_different_observation(world):
    db, _, digest = world
    other = store_payload(db, b"other bytes")
    assert repo.store_observation(db, make_observation(digest)).stored.id != repo.store_observation(db, make_observation(other)).stored.id


def test_find_observation_uses_the_same_identity_including_none(world):
    db, _, digest = world
    with_id = repo.store_observation(db, make_observation(digest, source_record_identifier="rec-1")).stored
    without = repo.store_observation(db, make_observation(digest, source_record_identifier=None)).stored
    assert repo.find_observation(db, "sec_edgar", "rec-1", digest) == with_id
    assert repo.find_observation(db, "sec_edgar", None, digest) == without
    assert repo.find_observation(db, "sec_edgar", "rec-2", digest) is None
    assert repo.find_observation(db, "greenhouse_jobs", "rec-1", digest) is None


@pytest.mark.parametrize("record_id", ["rec-1", None])
def test_concurrent_storage_of_one_identity_creates_exactly_one_observation(world, record_id):
    db, _, digest = world
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: repo.store_observation(db, make_observation(digest, source_record_identifier=record_id)), range(16)))
    assert sum(r.created for r in results) == 1 and len({r.stored.id for r in results}) == 1
    assert count(db, "observation") == 1


# ---------------- lineage

def test_observation_to_payload_to_source_lineage_with_verified_hash(world):
    db, source, digest = world
    stored = repo.store_observation(db, make_observation(digest, source_record_identifier="rec-1")).stored
    lineage = repo.get_observation_lineage(db, stored.id)
    assert lineage.observation == stored
    assert lineage.source == source and lineage.source.source.source_key == stored.observation.source_key
    assert lineage.payload.content_hash == stored.observation.content_hash == digest
    assert lineage.payload.payload_bytes == b"exact evidence bytes"


def test_lineage_of_a_missing_observation_is_none(migrated_db):
    assert repo.get_observation_lineage(migrated_db, 12345) is None


def test_lineage_fails_loudly_when_the_payload_was_tampered_with(world):
    db, _, digest = world
    stored = repo.store_observation(db, make_observation(digest)).stored
    tamper_payload(db, digest, new_bytes=b"exact evidence byteX")  # same 20-byte length
    with pytest.raises(InvariantViolationError) as info:
        repo.get_observation_lineage(db, stored.id)
    assert info.value.code == "payload_hash_mismatch"


# ---------------- surface

def test_the_repository_exposes_no_update_or_delete():
    public = {n for n, v in vars(repo).items() if callable(v) and not n.startswith("_") and getattr(v, "__module__", "") == repo.__name__}
    assert public == {"store_observation", "get_observation_by_id", "find_observation", "get_observation_lineage",
                      "ObservationStoreResult", "ObservationLineage"}
    source = inspect.getsource(repo).lower()
    assert "delete(" not in source and "delete from" not in source and "update(" not in source and "do_update" not in source


def test_a_connection_joins_the_callers_transaction(world):
    db, _, digest = world
    with db.connect() as conn:
        transaction = conn.begin()
        repo.store_observation(conn, make_observation(digest, source_record_identifier="txn"))
        assert repo.find_observation(conn, "sec_edgar", "txn", digest) is not None
        transaction.rollback()
    assert repo.find_observation(db, "sec_edgar", "txn", digest) is None
