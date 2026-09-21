"""Concurrent candidate persistence: replays and lifecycle races are settled by the database."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.v2.candidates.service import persist_verified_candidates
from app.v2.domain.errors import InvariantViolationError
from app.v2.repositories import company_candidates as repo
from app.v2.repositories import processing_attempts as attempts
from app.v2.repositories.errors import ConflictError
from app.v2.tests.db.candidate_fakes import PAGE, PROC, V1, FixedProposer, make_proposal
from app.v2.tests.db.evidence_helpers import count, ingest_one

pytestmark = pytest.mark.db

ACME = lambda: make_proposal(PAGE, "Acme Robotics", domain="acmerobotics.com", domain_needle=b"ACMEROBOTICS.COM", url="https://www.acmerobotics.com")
GLOBEX = lambda: make_proposal(PAGE, "Globex Corporation")


@pytest.fixture
def world(migrated_db):
    observation = ingest_one(migrated_db, payload=PAGE).observation
    return migrated_db, observation, attempts.start_processing(migrated_db, observation.id, PROC, V1)


def run_all(fn, n=16):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(fn, range(n)))


def test_concurrent_replay_of_one_batch_creates_each_candidate_exactly_once(world):
    db, _, attempt = world
    results = run_all(lambda _: repo.store_company_candidates(db, attempt.id, [ACME(), GLOBEX()]))
    assert (count(db, "company_candidate"), count(db, "company_candidate_identifier")) == (2, 2)
    assert [sum(r.created[i] for r in results) for i in (0, 1)] == [1, 1]       # exactly one writer per ordinal
    assert len({tuple(c.id for c in r.candidates) for r in results}) == 1


def test_concurrent_service_replays_are_idempotent_too(world):
    db, _, attempt = world
    results = run_all(lambda _: persist_verified_candidates(db, attempt.id, FixedProposer([ACME(), GLOBEX()])))
    assert count(db, "company_candidate") == 2 and sum(r.created_count for r in results) == 2
    listed = repo.list_company_candidates(db, attempt.id)
    assert [c.candidate_ordinal for c in listed] == [1, 2]                          # deterministic ordering preserved


def test_concurrent_conflicting_proposals_at_one_ordinal_admit_exactly_one_winner(world):
    db, _, attempt = world
    def attempt_store(i):
        try:
            return repo.store_company_candidates(db, attempt.id, [ACME() if i % 2 == 0 else GLOBEX()]).created
        except ConflictError as exc:
            return exc.code
    results = run_all(attempt_store)
    assert count(db, "company_candidate") == 1
    assert results.count((True,)) == 1 and all(r in ((True,), (False,), "candidate_ordinal_conflict") for r in results)


def test_a_transition_waits_for_an_in_flight_candidate_write_and_never_slips_between(world):
    """The candidate transaction holds the attempt FOR SHARE, so mark_processed must wait for it."""
    db, _, attempt = world
    locked, release, finished = threading.Event(), threading.Event(), {}

    def writer():
        with db.begin() as conn:
            repo.load_proposal_context(conn, attempt.id)                         # takes the FOR SHARE lock
            locked.set()
            assert release.wait(timeout=10)
            repo.store_company_candidates(conn, attempt.id, [ACME()])

    def finisher():
        finished["attempt"] = attempts.mark_processed(db, attempt.id)

    t_writer = threading.Thread(target=writer)
    t_writer.start()
    assert locked.wait(timeout=10)
    t_finisher = threading.Thread(target=finisher)
    t_finisher.start()
    time.sleep(0.6)
    assert t_finisher.is_alive() and "attempt" not in finished                   # blocked behind the candidate write
    release.set()
    t_writer.join(timeout=15)
    t_finisher.join(timeout=15)
    assert not t_writer.is_alive() and not t_finisher.is_alive()
    assert finished["attempt"].status.value == "processed" and count(db, "company_candidate") == 1


def test_once_the_attempt_is_processed_every_concurrent_writer_is_refused(world):
    db, _, attempt = world
    attempts.mark_processed(db, attempt.id)
    def try_store(_):
        try:
            return repo.store_company_candidates(db, attempt.id, [ACME()])
        except InvariantViolationError as exc:
            return exc.code
    assert set(run_all(try_store, n=12)) == {"attempt_not_processing"}
    assert count(db, "company_candidate") == 0
