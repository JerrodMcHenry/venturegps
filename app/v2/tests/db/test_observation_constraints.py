"""Direct-SQL protection of v2.observation: integrity CHECKs, foreign keys, dedup indexes, recorded_time."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.v2.tests.db.evidence_helpers import (
    count,
    fetch_row,
    insert_observation_sql,
    insert_payload_sql,
    refused,
    register_source,
)

pytestmark = pytest.mark.db


@pytest.fixture
def base(migrated_db):
    source = register_source(migrated_db)
    return migrated_db, source.id, insert_payload_sql(migrated_db, b"evidence")


def rejected(db, sid, digest, **overrides):
    """Attempt a direct insert with overrides; return the violated constraint (or column) name."""
    values = dict(source_id=sid, observation_type="filing_document", observed_time=datetime(2026, 9, 21, tzinfo=timezone.utc),
                  collection_version="manual_upload.v1", collector_id="admin:user_2abc", content_hash=digest, sniffed_media_type="text/plain")
    values.update(overrides)
    cols = ", ".join(values)
    binds = ", ".join(f":{k}" for k in values)
    diag, _ = refused(db, f"INSERT INTO v2.observation ({cols}) VALUES ({binds})", values, exc=IntegrityError)
    return diag.constraint_name or diag.column_name


# ---------------- foreign keys

def test_a_source_must_exist(base):
    db, _, digest = base
    assert rejected(db, 999999, digest) == "fk_observation_source_id_source"


def test_a_payload_must_exist(base):
    db, source_id, _ = base
    assert rejected(db, source_id, "f" * 64) == "fk_observation_content_hash_raw_payload"


@pytest.mark.parametrize("column", ["source_id", "observation_type", "observed_time", "collection_version",
                                    "collector_id", "content_hash", "sniffed_media_type"])
def test_not_null_columns(base, column):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, **{column: None}) == column


# ---------------- event time storage

@pytest.mark.parametrize("event_time, precision", [("2025-03-01T00:00:00+00:00", None), (None, "year")])
def test_event_time_and_precision_must_be_paired(base, event_time, precision):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, event_time=event_time, event_time_precision=precision) == "ck_observation_event_time_paired"


@pytest.mark.parametrize("precision", ["week", "Year", "", "exact"])
def test_unknown_precision_values_are_rejected(base, precision):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, event_time="2025-01-01T00:00:00+00:00", event_time_precision=precision) == "ck_observation_event_time_precision_allowed"


@pytest.mark.parametrize(
    "precision, event_time",
    [
        ("year", "2025-03-01T00:00:00+00:00"), ("year", "2025-01-02T00:00:00+00:00"), ("year", "2025-01-01T00:00:01+00:00"),
        ("month", "2025-03-05T00:00:00+00:00"), ("month", "2025-03-01T10:00:00+00:00"),
        ("day", "2025-03-05T10:00:00+00:00"), ("day", "2025-03-05T00:00:00.000001+00:00"),
        ("day", "2025-03-05T00:00:00+02:00"),  # 22:00 UTC the day before: not a UTC day start
    ],
)
def test_a_precision_cannot_claim_more_detail_than_it_has(base, precision, event_time):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, event_time=event_time, event_time_precision=precision) == "ck_observation_event_time_start_matches_precision"


@pytest.mark.parametrize(
    "precision, event_time",
    [("instant", "2025-03-05T14:22:07.123456+00:00"), ("day", "2025-03-05T00:00:00+00:00"), ("month", "2025-03-01T00:00:00+00:00"),
     ("year", "2025-01-01T00:00:00+00:00"), ("day", "2025-03-05T02:00:00+02:00")],
)
def test_canonical_starts_are_accepted(base, precision, event_time):
    db, source_id, digest = base
    row = fetch_row(db, "observation", "id = :i", {"i": insert_observation_sql(db, source_id, digest, event_time=event_time, event_time_precision=precision)})
    assert row["event_time_precision"] == precision


def test_no_event_time_is_valid_and_event_time_may_follow_observed_time(base):
    db, source_id, digest = base
    insert_observation_sql(db, source_id, digest)
    insert_observation_sql(db, source_id, digest, source_record_identifier="future", observed_time="2020-01-01T00:00:00+00:00",
                           event_time="2030-01-01T00:00:00+00:00", event_time_precision="instant")


# ---------------- recorded_time is the database's

def test_caller_supplied_recorded_time_is_overwritten(base):
    db, source_id, digest = base
    row = fetch_row(db, "observation", "id = :i", {"i": insert_observation_sql(db, source_id, digest, recorded_time="1999-01-01T00:00:00+00:00")})
    assert row["recorded_time"].year >= 2026 and row["recorded_time"] != row["observed_time"]


def test_an_explicit_null_recorded_time_is_replaced_by_the_database_clock_not_rejected(base):
    db, source_id, digest = base
    row = fetch_row(db, "observation", "id = :i", {"i": insert_observation_sql(db, source_id, digest, recorded_time=None)})
    assert row["recorded_time"] is not None and row["recorded_time"].year >= 2026


def test_recorded_time_defaults_when_omitted(base):
    db, source_id, digest = base
    assert fetch_row(db, "observation", "id = :i", {"i": insert_observation_sql(db, source_id, digest)})["recorded_time"].tzinfo is not None


# ---------------- other shapes

@pytest.mark.parametrize("value", ["", "A", "a", "Filing", "filing document", "1x", "x" * 65])
def test_observation_type_shape(base, value):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, observation_type=value) == "ck_observation_observation_type_shape"


@pytest.mark.parametrize("value", ["manual_upload", "manual.v0", "Manual.v1", "manual.v01", "manual.v1\n", "", "x" * 65 + ".v1"])
def test_collection_version_shape(base, value):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, collection_version=value) == "ck_observation_collection_version_shape"


@pytest.mark.parametrize("value", ["", " admin", "admin user", "-admin", "x" * 129, "admïn", "a\nb"])
def test_collector_id_shape(base, value):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, collector_id=value) == "ck_observation_collector_id_shape"


@pytest.mark.parametrize("value", ["", "x" * 513, "a\nb", "a\x01b"])
def test_source_record_identifier_validity(base, value):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, source_record_identifier=value) == "ck_observation_source_record_identifier_valid"


@pytest.mark.parametrize("value", ["image/png", "TEXT/PLAIN", "text", "", "unknown ", "application/octet-stream"])
def test_sniffed_media_type_is_the_stored_vocabulary(base, value):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, sniffed_media_type=value) == "ck_observation_sniffed_media_type_allowed"


@pytest.mark.parametrize("value", ["Text/HTML", "texthtml", "text/", "/html", "text/html; charset=utf-8", "", "a/" + "b" * 300])
def test_declared_media_type_shape(base, value):
    db, source_id, digest = base
    assert rejected(db, source_id, digest, declared_media_type=value) == "ck_observation_declared_media_type_shape"


def test_declared_media_type_may_be_absent_or_outside_our_vocabulary(base):
    db, source_id, digest = base
    insert_observation_sql(db, source_id, digest, declared_media_type=None)
    insert_observation_sql(db, source_id, digest, source_record_identifier="x", declared_media_type="image/svg+xml")


def test_every_stored_sniffed_value_is_accepted_including_unknown(base):
    db, source_id, digest = base
    for i, value in enumerate(("text/plain", "text/html", "application/json", "application/pdf", "unknown")):
        insert_observation_sql(db, source_id, digest, source_record_identifier=f"r{i}", sniffed_media_type=value)


# ---------------- dedup indexes

def test_duplicate_identity_with_a_record_identifier_is_rejected_by_the_database(base):
    db, source_id, digest = base
    insert_observation_sql(db, source_id, digest, source_record_identifier="rec-1")
    assert rejected(db, source_id, digest, source_record_identifier="rec-1") == "uq_observation_dedup_with_record_id"


def test_duplicate_identity_without_a_record_identifier_is_rejected_by_the_database(base):
    db, source_id, digest = base
    insert_observation_sql(db, source_id, digest)
    assert rejected(db, source_id, digest) == "uq_observation_dedup_without_record_id"  # ordinary UNIQUE would have allowed this


def test_the_identity_differs_by_source_record_identifier_and_bytes(base):
    db, source_id, digest = base
    other_source = register_source(db, "greenhouse_jobs").id
    other_payload = insert_payload_sql(db, b"different evidence")
    for kwargs in (dict(), dict(source_record_identifier="a"), dict(source_record_identifier="b")):
        insert_observation_sql(db, source_id, digest, **kwargs)
    insert_observation_sql(db, other_source, digest)
    insert_observation_sql(db, source_id, other_payload)
    assert count(db, "observation") == 5
