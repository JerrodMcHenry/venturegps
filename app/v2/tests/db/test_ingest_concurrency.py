"""Concurrent ingestion: PostgreSQL constraints are the final authority, not check-then-insert."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from app.v2.ingestion.service import ingest_evidence
from app.v2.repositories import sightings as sight_repo
from app.v2.tests.db.evidence_helpers import OBSERVED, make_command, register_source, table_counts

pytestmark = pytest.mark.db

THREADS = 16


@pytest.fixture
def db(migrated_db):
    register_source(migrated_db)
    return migrated_db


def run_all(db, commands):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda c: ingest_evidence(db, c), commands))


def test_concurrent_replay_of_one_acquisition_creates_exactly_one_of_everything(db):
    results = run_all(db, [make_command() for _ in range(THREADS)])
    assert table_counts(db) == {"raw_payload": 1, "observation": 1, "observation_sighting": 1}
    assert sum(r.payload_created for r in results) == 1
    assert sum(r.observation_created for r in results) == 1
    assert sum(r.sighting_created for r in results) == 1
    assert len({r.sighting.id for r in results}) == 1 and len({r.observation.id for r in results}) == 1


def test_concurrent_distinct_acquisitions_of_the_same_evidence_create_distinct_sightings(db):
    commands = [make_command(acquisition_key=f"run_{i}", observed_time=OBSERVED + timedelta(minutes=i)) for i in range(THREADS)]
    results = run_all(db, commands)
    assert table_counts(db) == {"raw_payload": 1, "observation": 1, "observation_sighting": THREADS}
    assert sum(r.payload_created for r in results) == 1 and sum(r.observation_created for r in results) == 1
    assert all(r.sighting_created for r in results) and len({r.sighting.id for r in results}) == THREADS
    observation_id = results[0].observation.id
    assert len({r.observation.id for r in results}) == 1
    assert len(sight_repo.list_sightings(db, observation_id)) == THREADS


def test_the_new_observations_first_sighting_matches_it_even_under_a_race(db):
    commands = [make_command(acquisition_key=f"run_{i}", observed_time=OBSERVED + timedelta(minutes=i)) for i in range(THREADS)]
    results = run_all(db, commands)
    creator = next(r for r in results if r.observation_created)
    assert creator.observation.observation.observed_time == creator.sighting.sighting.observed_time  # first-sighting invariant
    for r in results:  # every other ingestion left the Observation exactly as the creator wrote it
        assert r.observation.observation.observed_time == creator.observation.observation.observed_time


def test_identical_bytes_for_many_records_share_one_payload(db):
    commands = [make_command(source_record_identifier=f"rec-{i}", acquisition_key="run_1") for i in range(THREADS)]
    results = run_all(db, commands)
    assert table_counts(db) == {"raw_payload": 1, "observation": THREADS, "observation_sighting": THREADS}
    assert sum(r.payload_created for r in results) == 1 and all(r.observation_created for r in results)


def test_mixed_replays_and_new_acquisitions_of_two_evidence_states(db):
    commands = []
    for i in range(THREADS):
        commands.append(make_command(payload_bytes=b"state one", acquisition_key=f"one_{i % 4}"))
        commands.append(make_command(payload_bytes=b"state two", acquisition_key=f"two_{i % 4}"))
    results = run_all(db, commands)
    assert table_counts(db) == {"raw_payload": 2, "observation": 2, "observation_sighting": 8}
    assert sum(r.observation_created for r in results) == 2 and sum(r.sighting_created for r in results) == 8


def test_a_racing_failure_leaves_no_partial_rows(db, monkeypatch):
    from app.v2.ingestion import service
    real = service.store_sighting
    def flaky(conn, observation_id, sighting):
        if sighting.acquisition_key.endswith(("1", "3", "5", "7", "9")):
            raise RuntimeError("simulated failure")
        return real(conn, observation_id, sighting)
    monkeypatch.setattr(service, "store_sighting", flaky)

    def attempt(i):
        try:
            return ingest_evidence(db, make_command(payload_bytes=f"evidence {i}".encode(), acquisition_key=f"run_{i}"))
        except RuntimeError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(10)))
    succeeded = [r for r in results if r is not None]
    assert len(succeeded) == 5
    # only complete ingestions exist: every payload/observation has its sighting; nothing else survived
    assert table_counts(db) == {"raw_payload": 5, "observation": 5, "observation_sighting": 5}
