"""Concurrent starts and lifecycle races: the database constraints are the final authority."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.v2.domain.errors import InvariantViolationError
from app.v2.repositories import processing_attempts as repo
from app.v2.repositories.errors import ConflictError
from app.v2.tests.db.evidence_helpers import count, ingest_one

pytestmark = pytest.mark.db

PROC, V1 = "fin_extractor", "fin_extractor.v1"
THREADS = 16


@pytest.fixture
def world(migrated_db):
    return migrated_db, ingest_one(migrated_db).observation.id


def outcomes(pool_fn, n=THREADS):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(pool_fn, range(n)))


def try_start(db, oid, version=V1, proc=PROC):
    def call(_):
        try:
            return repo.start_processing(db, oid, proc, version)
        except ConflictError as exc:
            return exc
    return call


def test_concurrent_starts_for_one_observation_and_processor_yield_exactly_one_active_attempt(world):
    db, oid = world
    results = outcomes(try_start(db, oid))
    winners = [r for r in results if not isinstance(r, ConflictError)]
    assert len(winners) == 1 and winners[0].attempt_number == 1
    assert all(isinstance(r, ConflictError) and r.code == "attempt_already_active" for r in results if r is not winners[0])
    assert count(db, "processing_attempt") == 1
    assert [a.attempt_number for a in repo.list_processing_attempts(db, oid)] == [1]


def test_concurrent_retries_after_a_failure_produce_a_single_next_attempt(world):
    db, oid = world
    repo.mark_failed(db, repo.start_processing(db, oid, PROC, V1).id, "timeout")
    results = outcomes(try_start(db, oid))
    assert sum(not isinstance(r, ConflictError) for r in results) == 1
    history = repo.list_processing_attempts(db, oid)
    assert [(a.attempt_number, a.status.value) for a in history] == [(1, "failed"), (2, "processing")]


def test_repeated_fail_and_retry_cycles_never_duplicate_or_skip_numbers(world):
    db, oid = world
    for expected in range(1, 6):
        wins = [r for r in outcomes(try_start(db, oid), n=8) if not isinstance(r, ConflictError)]
        assert len(wins) == 1 and wins[0].attempt_number == expected
        repo.mark_failed(db, wins[0].id, "timeout")
    assert [a.attempt_number for a in repo.list_processing_attempts(db, oid)] == [1, 2, 3, 4, 5]


def test_different_processors_start_concurrently_without_interference(world):
    db, oid = world
    procs = [f"proc_{i}" for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        started = list(pool.map(lambda p: repo.start_processing(db, oid, p, f"{p}.v1"), procs))
    assert sorted(a.processor_id for a in started) == sorted(procs) and {a.attempt_number for a in started} == {1}


def test_concurrent_starts_across_different_observations_do_not_serialise_into_conflicts(migrated_db):
    ids = [ingest_one(migrated_db, record_id=f"r{i}", key=f"k{i}").observation.id for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        started = list(pool.map(lambda oid: repo.start_processing(migrated_db, oid, PROC, V1), ids))
    assert len({a.observation_id for a in started}) == 8 and {a.attempt_number for a in started} == {1}


def test_a_start_that_bypasses_the_row_lock_still_cannot_create_a_duplicate(world):
    """The lock is convenience; the constraints are the authority. Two raw inserts race for attempt 1."""
    db, oid = world
    barrier = threading.Barrier(2)
    sql = text("INSERT INTO v2.processing_attempt (observation_id, processor_id, processor_version, attempt_number, status, lease_expires_at) "
               "VALUES (:o, 'fin_extractor', 'fin_extractor.v1', 1, 'processing', now() + interval '5 minutes')")

    def raw(_):
        barrier.wait(timeout=10)
        try:
            with db.begin() as conn:
                conn.execute(sql, {"o": oid})
            return "ok"
        except IntegrityError as exc:
            return exc.orig.diag.constraint_name

    results = outcomes(raw, n=2)
    assert results.count("ok") == 1
    assert [r for r in results if r != "ok"][0] in ("uq_processing_attempt_number", "uq_processing_attempt_one_active")
    assert count(db, "processing_attempt") == 1


def test_a_racing_finish_and_renewals_end_in_one_consistent_terminal_state(world):
    db, oid = world
    attempt = repo.start_processing(db, oid, PROC, V1)

    def act(i):
        try:
            return repo.mark_processed(db, attempt.id) if i == 0 else repo.renew_lease(db, attempt.id, lease_seconds=60)
        except InvariantViolationError as exc:
            return exc.code

    results = outcomes(act, n=12)
    final = repo.get_processing_attempt(db, attempt.id)
    assert final.status.value == "processed" and final.lease_expires_at is None and final.reason_code is None
    assert all(r == "illegal_transition" or hasattr(r, "attempt_number") for r in results)   # late renewals are refused, never corrupt


def test_concurrent_expiry_failures_transition_exactly_once(world):
    db, oid = world
    attempt = repo.start_processing(db, oid, PROC, V1)
    far = datetime.now(timezone.utc) + timedelta(days=1)

    def fail(_):
        try:
            return repo.fail_expired_attempt(db, attempt.id, as_of=far)
        except InvariantViolationError as exc:
            return exc.code

    results = outcomes(fail, n=10)
    assert sum(hasattr(r, "attempt_number") for r in results) == 1 and results.count("illegal_transition") == 9
    assert repo.get_processing_attempt(db, attempt.id).reason_code == "lease_expired"
