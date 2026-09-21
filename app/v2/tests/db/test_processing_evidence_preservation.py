"""Processing never touches evidence: Source, RawPayload, Observation and ObservationSighting stay byte-identical."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.v2.ingestion.service import ingest_evidence
from app.v2.repositories import observations as obs_repo
from app.v2.repositories import processing_attempts as repo
from app.v2.repositories import sightings as sight_repo
from app.v2.tests.db.evidence_helpers import evidence_snapshot, ingest_one, make_command, register_source

pytestmark = pytest.mark.db

PROC = "fin_extractor"


@pytest.fixture
def world(migrated_db):
    a = ingest_one(migrated_db, record_id="rec-1", payload=b"first evidence", key="run_1")
    ingest_one(migrated_db, record_id="rec-1", payload=b"first evidence", key="run_2")      # a second sighting of the same observation
    b = ingest_one(migrated_db, record_id="rec-2", payload=b"second evidence", key="run_1")
    return migrated_db, a.observation.id, b.observation.id


def test_a_full_processing_lifecycle_leaves_all_evidence_byte_identical(world):
    db, first, second = world
    before = evidence_snapshot(db)
    assert len(before["observation"]) == 2 and len(before["observation_sighting"]) == 3

    a1 = repo.start_processing(db, first, PROC, "fin_extractor.v1")
    repo.renew_lease(db, a1.id)
    repo.mark_failed(db, a1.id, "parse_error", "unexpected_eof")
    a2 = repo.start_processing(db, first, PROC, "fin_extractor.v1")
    repo.mark_processed(db, a2.id)
    a3 = repo.start_processing(db, first, PROC, "fin_extractor.v2")                          # reprocessing under a later version
    repo.fail_expired_attempt(db, a3.id, as_of=datetime.now(timezone.utc) + timedelta(days=1))
    q = repo.start_processing(db, second, PROC, "fin_extractor.v1")
    repo.mark_quarantined(db, q.id, "media_type_mismatch")
    repo.start_processing(db, second, "second_proc", "second_proc.v1")                       # left PROCESSING

    assert evidence_snapshot(db) == before
    assert len(repo.list_processing_attempts(db, first)) == 3 and len(repo.list_processing_attempts(db, second)) == 2


def test_observations_and_sightings_read_back_identically_after_processing(world):
    db, first, _ = world
    observation_before = obs_repo.get_observation_by_id(db, first)
    sightings_before = sight_repo.list_sightings(db, first)
    lineage_before = obs_repo.get_observation_lineage(db, first)
    repo.mark_processed(db, repo.start_processing(db, first, PROC, "fin_extractor.v1").id)
    assert obs_repo.get_observation_by_id(db, first) == observation_before
    assert sight_repo.list_sightings(db, first) == sightings_before
    assert obs_repo.get_observation_lineage(db, first) == lineage_before


def test_the_observation_still_has_no_processing_status(world):
    db, first, _ = world
    repo.start_processing(db, first, PROC, "fin_extractor.v1")
    with db.connect() as conn:
        columns = {r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name='observation'"))}
    assert not any(w in c for c in columns for w in ("status", "attempt", "processing", "lease"))
    assert not hasattr(obs_repo.get_observation_by_id(db, first).observation, "processing_status")


def test_evidence_can_still_be_ingested_and_re_sighted_while_processing_history_exists(world):
    db, first, _ = world
    attempt = repo.start_processing(db, first, PROC, "fin_extractor.v1")
    before = repo.get_processing_attempt(db, attempt.id)
    result = ingest_evidence(db, make_command(source_record_identifier="rec-1", payload_bytes=b"first evidence", acquisition_key="run_3"))
    assert result.sighting_created and result.observation.id == first
    assert repo.get_processing_attempt(db, attempt.id) == before                              # ingestion does not touch processing history
    assert len(sight_repo.list_sightings(db, first)) == 3


def test_processing_history_is_independent_per_observation(world):
    db, first, second = world
    repo.mark_processed(db, repo.start_processing(db, first, PROC, "fin_extractor.v1").id)
    assert repo.list_unprocessed_observation_ids(db, PROC) == [second]
    assert repo.get_latest_attempt(db, second, PROC) is None


def test_processing_does_not_require_or_change_the_sources_active_state(world):
    from app.v2.repositories import sources
    db, first, _ = world
    sources.deactivate_source(db, "sec_edgar")
    before = evidence_snapshot(db)
    repo.mark_processed(db, repo.start_processing(db, first, PROC, "fin_extractor.v1").id)   # historical evidence remains processable
    assert evidence_snapshot(db) == before
