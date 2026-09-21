"""ingest_evidence: the deterministic workflow, end to end, against the disposable database."""

import hashlib
import inspect
import socket
from datetime import datetime, timedelta, timezone

import pytest

from app.v2.domain.content import MediaAgreement, MediaType
from app.v2.domain.errors import DomainError, InvalidInputError, UnsupportedInputError
from app.v2.domain.payload import MAX_INLINE_PAYLOAD_BYTES
from app.v2.domain.time import EventTime
from app.v2.ingestion import service
from app.v2.ingestion.errors import SourceInactiveError
from app.v2.ingestion.models import IngestionResult
from app.v2.ingestion.service import ingest_evidence
from app.v2.repositories import observations as obs_repo
from app.v2.repositories import sightings as sight_repo
from app.v2.repositories import sources as source_repo
from app.v2.repositories.errors import NotFoundError
from app.v2.tests.db.evidence_helpers import OBSERVED, count, fetch_row, make_command, register_source, table_counts

pytestmark = pytest.mark.db

PLUS_2 = timezone(timedelta(hours=2))
BYTES = b"exact evidence bytes"
ZEROS = {"raw_payload": 0, "observation": 0, "observation_sighting": 0}


@pytest.fixture
def db(migrated_db):
    register_source(migrated_db)
    return migrated_db


@pytest.fixture(autouse=True)
def no_python_level_network(monkeypatch):
    """Ingestion starts from bytes already in hand: no Python-level network use at all.
    (The database driver talks to Postgres through libpq, which does not go through these.)"""
    def boom(*a, **k):
        raise AssertionError("network access attempted during ingestion")
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, boom)
    for name in ("create_connection", "getaddrinfo", "gethostbyname"):
        monkeypatch.setattr(socket, name, boom)


def observation_row(db, observation_id):
    return fetch_row(db, "observation", "id = :i", {"i": observation_id})


# ---------------- first ingestion

def test_first_ingestion_creates_payload_observation_and_first_sighting(db):
    result = ingest_evidence(db, make_command())
    assert isinstance(result, IngestionResult)
    assert (result.payload_created, result.observation_created, result.sighting_created) == (True, True, True)
    assert result.is_replay is False and result.differences == ()
    assert table_counts(db) == {"raw_payload": 1, "observation": 1, "observation_sighting": 1}
    assert result.sighting.observation_id == result.observation.id


def test_the_hash_is_exactly_sha256_of_the_received_bytes(db):
    payload = b"\r\n\x00 exact \xff bytes \r\n"
    result = ingest_evidence(db, make_command(payload_bytes=payload))
    assert result.payload.content_hash == hashlib.sha256(payload).hexdigest() == result.observation.observation.content_hash
    assert result.payload.payload_bytes == payload
    assert obs_repo.get_observation_lineage(db, result.observation.id).payload.payload_bytes == payload


def test_the_observations_first_observed_time_is_its_first_sightings(db):
    result = ingest_evidence(db, make_command(observed_time=datetime(2026, 9, 21, 14, 0, 0, 123, tzinfo=PLUS_2)))
    expected = datetime(2026, 9, 21, 12, 0, 0, 123, tzinfo=timezone.utc)
    assert result.observation.observation.observed_time == result.sighting.sighting.observed_time == expected


def test_lineage_is_intact_from_the_sighting_to_the_source(db):
    result = ingest_evidence(db, make_command(source_record_identifier="rec-9"))
    sighting = sight_repo.get_sighting_by_id(db, result.sighting.id)
    lineage = obs_repo.get_observation_lineage(db, sighting.observation_id)
    assert lineage.observation == result.observation
    assert lineage.source.source.source_key == "sec_edgar"
    assert lineage.payload == result.payload  # hash verified on the way


def test_media_is_sniffed_from_the_bytes_and_the_declared_type_is_normalized(db):
    result = ingest_evidence(db, make_command(payload_bytes=b"<!DOCTYPE html><html>hi</html>", declared_media_type="Text/HTML; charset=UTF-8"))
    obs = result.observation.observation
    assert obs.sniffed_media_type is MediaType.TEXT_HTML and obs.declared_media_type == "text/html"
    assert obs.media_agreement is MediaAgreement.CONSISTENT


def test_recorded_times_are_database_owned(db):
    old = datetime(2001, 1, 1, tzinfo=timezone.utc)
    result = ingest_evidence(db, make_command(observed_time=old))
    for recorded in (result.observation.recorded_time, result.sighting.recorded_time):
        assert recorded > old and abs(datetime.now(timezone.utc) - recorded) < timedelta(minutes=5)
    assert "recorded_time" not in inspect.signature(ingest_evidence).parameters


def test_event_time_unknown_and_precision_are_preserved(db):
    unknown = ingest_evidence(db, make_command(source_record_identifier="a"))
    year = ingest_evidence(db, make_command(source_record_identifier="b", event_time=EventTime.of_year(2025)))
    assert unknown.observation.observation.event_time is None
    assert year.observation.observation.event_time == EventTime.of_year(2025) and not year.observation.observation.event_time.is_exact
    assert fetch_row(db, "observation", "id = :i", {"i": year.observation.id})["event_time_precision"] == "year"


# ---------------- repeat identical evidence

def test_repeat_identical_evidence_reuses_payload_and_observation_and_adds_a_sighting(db):
    first = ingest_evidence(db, make_command(acquisition_key="run_1", observed_time=OBSERVED))
    before = observation_row(db, first.observation.id)
    second = ingest_evidence(db, make_command(acquisition_key="run_2", observed_time=OBSERVED + timedelta(hours=1)))

    assert (second.payload_created, second.observation_created, second.sighting_created) == (False, False, True)
    assert second.observation == first.observation and second.payload == first.payload
    assert second.sighting.id != first.sighting.id and second.differences == ()
    assert table_counts(db) == {"raw_payload": 1, "observation": 1, "observation_sighting": 2}
    assert observation_row(db, first.observation.id) == before   # the Observation row is untouched, byte for byte


def test_the_first_observed_time_never_moves_on_repeat_acquisition(db):
    first = ingest_evidence(db, make_command(acquisition_key="run_1", observed_time=OBSERVED))
    for i, hours in enumerate((1, 24, 24 * 30), start=2):
        ingest_evidence(db, make_command(acquisition_key=f"run_{i}", observed_time=OBSERVED + timedelta(hours=hours)))
    stored = obs_repo.get_observation_by_id(db, first.observation.id)
    assert stored.observation.observed_time == OBSERVED and stored.recorded_time == first.observation.recorded_time
    times = [s.sighting.observed_time for s in sight_repo.list_sightings(db, first.observation.id)]
    assert times == [OBSERVED + timedelta(hours=h) for h in (0, 1, 24, 24 * 30)]


def test_the_shared_payload_row_is_never_touched_by_repeats(db):
    first = ingest_evidence(db, make_command())
    before = fetch_row(db, "raw_payload", "content_hash = :h", {"h": first.payload.content_hash})
    ingest_evidence(db, make_command(acquisition_key="run_2"))
    assert fetch_row(db, "raw_payload", "content_hash = :h", {"h": first.payload.content_hash}) == before


def test_metadata_differences_are_reported_but_the_existing_observation_stays_canonical(db):
    first = ingest_evidence(db, make_command(observation_type="filing_document", collector_id="admin:one"))
    before = observation_row(db, first.observation.id)
    again = ingest_evidence(db, make_command(
        acquisition_key="run_2", observation_type="press_release", collector_id="admin:two", event_time=EventTime.of_year(2020),
        declared_media_type="application/pdf", collection_version="manual_upload.v2"))
    assert again.observation == first.observation and again.observation_created is False
    assert set(again.differences) == {"observation.observation_type", "observation.collector_id", "observation.event_time",
                                      "observation.declared_media_type", "observation.collection_version"}
    assert observation_row(db, first.observation.id) == before
    # the new acquisition's own facts live on its sighting
    assert again.sighting.sighting.collector_id == "admin:two" and again.sighting.sighting.collection_version == "manual_upload.v2"


# ---------------- idempotent replay

def test_replaying_the_exact_acquisition_creates_no_duplicate_sighting(db):
    command = make_command()
    first = ingest_evidence(db, command)
    replay = ingest_evidence(db, command)
    assert replay.sighting_created is False and replay.is_replay is True
    assert replay.sighting == first.sighting and replay.observation == first.observation and replay.payload == first.payload
    assert replay.differences == () and table_counts(db) == {"raw_payload": 1, "observation": 1, "observation_sighting": 1}


def test_a_replay_with_a_different_observed_time_returns_the_original_and_reports_it(db):
    first = ingest_evidence(db, make_command(observed_time=OBSERVED))
    replay = ingest_evidence(db, make_command(observed_time=OBSERVED + timedelta(minutes=7), collector_id="admin:retry"))
    assert replay.sighting == first.sighting and replay.sighting_created is False
    assert set(replay.differences) == {"sighting.observed_time", "sighting.collector_id", "observation.collector_id"}
    assert count(db, "observation_sighting") == 1


def test_the_same_key_for_a_different_record_is_a_new_observation_and_sighting(db):
    a = ingest_evidence(db, make_command(source_record_identifier="rec-1", acquisition_key="run_42"))
    b = ingest_evidence(db, make_command(source_record_identifier="rec-2", acquisition_key="run_42"))
    assert a.observation.id != b.observation.id and b.sighting_created is True and b.payload_created is False


# ---------------- changed evidence

def test_changed_bytes_for_the_same_record_are_new_evidence(db):
    first = ingest_evidence(db, make_command(payload_bytes=b"version one", acquisition_key="run_1"))
    second = ingest_evidence(db, make_command(payload_bytes=b"version two", acquisition_key="run_2"))
    assert (second.payload_created, second.observation_created, second.sighting_created) == (True, True, True)
    assert first.observation.id != second.observation.id and first.payload.content_hash != second.payload.content_hash
    assert table_counts(db) == {"raw_payload": 2, "observation": 2, "observation_sighting": 2}   # both states of the record are kept
    assert obs_repo.get_observation_by_id(db, first.observation.id) == first.observation          # the old one is untouched


def test_no_record_identifier_deduplicates_by_source_and_bytes(db):
    a = ingest_evidence(db, make_command(source_record_identifier=None, acquisition_key="run_1"))
    b = ingest_evidence(db, make_command(source_record_identifier=None, acquisition_key="run_2"))
    c = ingest_evidence(db, make_command(source_record_identifier="rec-1", acquisition_key="run_3"))
    assert a.observation.id == b.observation.id != c.observation.id and b.sighting_created and b.observation_created is False


# ---------------- source rules

def test_a_missing_source_is_rejected_and_nothing_is_written(db):
    with pytest.raises(NotFoundError) as info:
        ingest_evidence(db, make_command(source_key="unregistered_source"))
    assert info.value.code == "source_not_found" and table_counts(db) == ZEROS


def test_an_inactive_source_is_rejected_and_nothing_is_written(db):
    source_repo.deactivate_source(db, "sec_edgar")
    with pytest.raises(SourceInactiveError) as info:
        ingest_evidence(db, make_command())
    assert info.value.code == "source_inactive" and table_counts(db) == ZEROS


def test_deactivation_does_not_touch_or_invalidate_existing_evidence(db):
    first = ingest_evidence(db, make_command())
    snapshot = table_counts(db), observation_row(db, first.observation.id)
    source_repo.deactivate_source(db, "sec_edgar")
    assert (table_counts(db), observation_row(db, first.observation.id)) == snapshot
    lineage = obs_repo.get_observation_lineage(db, first.observation.id)     # still fully readable and verifiable
    assert lineage.source.source.is_active is False and lineage.payload.payload_bytes == BYTES
    with pytest.raises(SourceInactiveError):                                   # even a replay of old evidence is refused while inactive
        ingest_evidence(db, make_command())
    assert table_counts(db) == snapshot[0]


def test_reactivation_allows_new_ingestion_and_replays(db):
    first = ingest_evidence(db, make_command())
    source_repo.deactivate_source(db, "sec_edgar")
    source_repo.reactivate_source(db, "sec_edgar")
    again = ingest_evidence(db, make_command(acquisition_key="run_2"))
    assert again.observation == first.observation and again.sighting_created is True
    assert ingest_evidence(db, make_command()).is_replay is True


# ---------------- media policy

def test_declared_and_sniffed_agreement_is_derived_and_persisted(db):
    consistent = ingest_evidence(db, make_command(source_record_identifier="a", payload_bytes=b'{"a": 1}', declared_media_type="application/json"))
    assert consistent.observation.observation.media_agreement is MediaAgreement.CONSISTENT


def test_a_declared_sniffed_conflict_still_persists_with_both_values(db):
    result = ingest_evidence(db, make_command(payload_bytes=b"<html><body>hi</body></html>", declared_media_type="application/pdf"))
    obs = result.observation.observation
    assert (obs.declared_media_type, obs.sniffed_media_type) == ("application/pdf", MediaType.TEXT_HTML)
    assert obs.media_type_mismatch is True and result.observation_created and result.sighting_created  # no quarantine, no rejection


def test_declared_type_can_never_override_the_sniffed_type(db):
    for i, (payload, declared, expected) in enumerate([
        (b"plain words", "application/json", MediaType.TEXT_PLAIN),
        (b"%PDF-1.7 ...", "text/plain", MediaType.APPLICATION_PDF),
        (b'{"a": 1}', "text/html", MediaType.APPLICATION_JSON),
        (b"\x00\x01\x02", "text/html", MediaType.UNKNOWN),
    ]):
        stored = ingest_evidence(db, make_command(source_record_identifier=f"r{i}", payload_bytes=payload, declared_media_type=declared))
        assert stored.observation.observation.sniffed_media_type is expected
        assert fetch_row(db, "observation", "id = :i", {"i": stored.observation.id})["sniffed_media_type"] == expected.value


def test_unknown_sniffed_media_is_valid_evidence(db):
    result = ingest_evidence(db, make_command(payload_bytes=b"\x89PNG\r\n\x1a\n\x00\x00", declared_media_type="image/png"))
    obs = result.observation.observation
    assert obs.sniffed_media_type is MediaType.UNKNOWN and obs.declared_media_type == "image/png"
    assert obs.media_agreement is MediaAgreement.UNVERIFIED and result.sighting_created
    empty = ingest_evidence(db, make_command(source_record_identifier="empty", payload_bytes=b""))
    assert empty.observation.observation.sniffed_media_type is MediaType.UNKNOWN and empty.payload.size_bytes == 0


def test_a_malformed_declared_media_type_is_rejected_and_nothing_is_written(db):
    with pytest.raises(InvalidInputError):
        ingest_evidence(db, make_command(declared_media_type="not a media type"))
    assert table_counts(db) == ZEROS


# ---------------- payload policy

def test_exactly_one_mib_is_accepted_and_kept_exact(db):
    data = bytes(i % 251 for i in range(MAX_INLINE_PAYLOAD_BYTES))
    result = ingest_evidence(db, make_command(payload_bytes=data))
    assert result.payload.size_bytes == MAX_INLINE_PAYLOAD_BYTES
    assert obs_repo.get_observation_lineage(db, result.observation.id).payload.payload_bytes == data


def test_more_than_one_mib_is_rejected_before_any_write(db):
    with pytest.raises(UnsupportedInputError) as info:
        ingest_evidence(db, make_command(payload_bytes=b"x" * (MAX_INLINE_PAYLOAD_BYTES + 1)))
    assert info.value.code == "payload_too_large" and table_counts(db) == ZEROS


# ---------------- out-of-order policy (A): record as-is, never rewrite

def test_an_earlier_sighting_arriving_late_is_recorded_and_the_observation_is_not_rewritten(db):
    later = ingest_evidence(db, make_command(acquisition_key="run_late", observed_time=OBSERVED + timedelta(days=2)))
    before = observation_row(db, later.observation.id)
    delayed = ingest_evidence(db, make_command(acquisition_key="run_delayed", observed_time=OBSERVED))   # observed EARLIER, ingested later
    assert delayed.sighting_created is True and delayed.observation == later.observation
    assert observation_row(db, later.observation.id) == before
    assert delayed.observation.observation.observed_time == OBSERVED + timedelta(days=2)   # the first-recorded value stands
    assert delayed.sighting.sighting.observed_time < delayed.observation.observation.observed_time
    listed = sight_repo.list_sightings(db, later.observation.id)
    assert [s.sighting.acquisition_key for s in listed] == ["run_delayed", "run_late"]      # deterministic, by observed_time
    assert listed[0].id > listed[1].id                                                     # though recorded in the other order


# ---------------- command validation

def test_only_an_ingestion_command_is_accepted(db):
    with pytest.raises(InvalidInputError):
        ingest_evidence(db, {"source_key": "sec_edgar"})


def test_a_command_cannot_carry_a_hash_or_a_sniffed_type(db):
    with pytest.raises(Exception):
        make_command(content_hash="0" * 64)
    with pytest.raises(Exception):
        make_command(sniffed_media_type="text/plain")


# ---------------- transactional failure

def test_a_failure_after_the_observation_is_created_leaves_no_partial_state(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulated failure after the payload and observation were written")
    monkeypatch.setattr(service, "store_sighting", boom)
    with pytest.raises(RuntimeError):
        ingest_evidence(db, make_command())
    assert table_counts(db) == ZEROS       # not the payload, not the observation, not a sighting


def test_a_failure_while_storing_the_observation_leaves_no_payload_behind(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(service, "store_observation", boom)
    with pytest.raises(RuntimeError):
        ingest_evidence(db, make_command())
    assert table_counts(db) == ZEROS


def test_a_failure_does_not_disturb_earlier_evidence(db, monkeypatch):
    first = ingest_evidence(db, make_command(payload_bytes=b"already stored", acquisition_key="run_1"))
    monkeypatch.setattr(service, "store_sighting", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        ingest_evidence(db, make_command(payload_bytes=b"never stored", acquisition_key="run_2"))
    assert table_counts(db) == {"raw_payload": 1, "observation": 1, "observation_sighting": 1}
    assert obs_repo.get_observation_by_id(db, first.observation.id) == first.observation


def test_with_a_connection_only_the_ingestion_is_undone_not_the_callers_transaction(db, monkeypatch):
    monkeypatch.setattr(service, "store_sighting", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with db.connect() as conn:
        outer = conn.begin()
        source_repo.update_source_metadata(conn, "sec_edgar", name="Renamed inside the outer transaction")
        with pytest.raises(RuntimeError):
            ingest_evidence(conn, make_command())
        assert table_counts(conn) == ZEROS                                    # the savepoint undid the partial ingestion
        assert source_repo.get_source_by_key(conn, "sec_edgar").source.name == "Renamed inside the outer transaction"
        outer.commit()
    assert source_repo.get_source_by_key(db, "sec_edgar").source.name == "Renamed inside the outer transaction"
    assert table_counts(db) == ZEROS


def test_a_connection_call_joins_the_callers_transaction_and_can_be_rolled_back(db):
    with db.connect() as conn:
        outer = conn.begin()
        result = ingest_evidence(conn, make_command())
        assert result.sighting_created and table_counts(conn)["observation_sighting"] == 1
        outer.rollback()
    assert table_counts(db) == ZEROS


def test_no_domain_error_leaks_evidence_content(db):
    secret = b"SECRET-PAYLOAD-Zq93"
    with pytest.raises(DomainError) as info:
        ingest_evidence(db, make_command(payload_bytes=secret + b"x" * MAX_INLINE_PAYLOAD_BYTES))
    assert b"SECRET" not in repr(info.value).encode() and "SECRET" not in str(info.value)
