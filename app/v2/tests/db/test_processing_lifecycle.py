"""Processing-attempt lifecycle through the repository."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.processing import ProcessingStatus
from app.v2.domain.processing_attempt import DEFAULT_LEASE_SECONDS, LEASE_EXPIRED_REASON, StoredProcessingAttempt
from app.v2.repositories import observations as obs_repo
from app.v2.repositories import processing_attempts as repo
from app.v2.repositories.errors import ConflictError, NotFoundError
from app.v2.tests.db.evidence_helpers import count, fetch_row, ingest_one

pytestmark = pytest.mark.db

PROC = "fin_extractor"
V1, V2, V3 = "fin_extractor.v1", "fin_extractor.v2", "fin_extractor.v3"
P, D, F, Q = (ProcessingStatus.PROCESSING, ProcessingStatus.PROCESSED, ProcessingStatus.FAILED, ProcessingStatus.QUARANTINED)


@pytest.fixture
def world(migrated_db):
    return migrated_db, ingest_one(migrated_db).observation


def row(db, attempt_id):
    return fetch_row(db, "processing_attempt", "id = :i", {"i": attempt_id})


# ---------------- start

def test_the_first_attempt_is_number_one_and_processing(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    assert isinstance(a, StoredProcessingAttempt)
    assert (a.attempt_number, a.status, a.processor_id, a.processor_version) == (1, P, PROC, V1)
    assert a.finished_at is None and a.reason_code is None and a.detail_code is None
    assert repo.get_processing_attempt(db, a.id) == a


def test_started_at_and_the_lease_come_from_the_database_clock(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    assert a.started_at.tzinfo is timezone.utc and abs(datetime.now(timezone.utc) - a.started_at) < timedelta(minutes=5)
    assert timedelta(seconds=DEFAULT_LEASE_SECONDS - 5) < a.lease_expires_at - a.started_at <= timedelta(seconds=DEFAULT_LEASE_SECONDS + 5)
    custom = repo.start_processing(db, observation.id, "other_proc", "other_proc.v1", lease_seconds=42)
    assert timedelta(seconds=37) < custom.lease_expires_at - custom.started_at <= timedelta(seconds=47)


def test_the_api_takes_no_caller_chosen_timestamps():
    import inspect
    for fn in (repo.start_processing, repo.renew_lease, repo.mark_processed, repo.mark_failed, repo.mark_quarantined):
        assert not {"started_at", "finished_at", "lease_expires_at", "now"} & set(inspect.signature(fn).parameters), fn.__name__


def test_the_observation_must_exist(migrated_db):
    with pytest.raises(NotFoundError) as info:
        repo.start_processing(migrated_db, 999999, PROC, V1)
    assert info.value.code == "observation_not_found"
    assert count(migrated_db, "processing_attempt") == 0


@pytest.mark.parametrize(
    "kwargs, error",
    [
        (dict(observation_id=0), InvalidInputError), (dict(observation_id="1"), InvalidInputError),
        (dict(processor_id="Bad Id"), InvalidInputError), (dict(processor_id="x"), InvalidInputError),
        (dict(processor_version="fin_extractor"), InvalidInputError), (dict(processor_version="fin_extractor.v0"), InvalidInputError),
        (dict(processor_version="other_processor.v1"), InvalidInputError),          # the version must belong to the processor
        (dict(lease_seconds=0), InvalidInputError), (dict(lease_seconds=10**9), InvalidInputError), (dict(lease_seconds=2.5), InvalidInputError),
    ],
)
def test_start_validates_its_arguments(world, kwargs, error):
    db, observation = world
    args = dict(observation_id=observation.id, processor_id=PROC, processor_version=V1)
    args.update(kwargs)
    with pytest.raises(error):
        repo.start_processing(db, args.pop("observation_id"), args.pop("processor_id"), args.pop("processor_version"), **args)


def test_an_observation_with_no_attempt_is_collected_and_derived_not_stored(world):
    db, observation = world
    assert repo.list_unprocessed_observation_ids(db, PROC) == [observation.id]
    assert repo.list_processing_attempts(db, observation.id) == [] and repo.get_latest_attempt(db, observation.id, PROC) is None
    repo.start_processing(db, observation.id, PROC, V1)
    assert repo.list_unprocessed_observation_ids(db, PROC) == []                        # it has history for this processor now
    assert repo.list_unprocessed_observation_ids(db, "other_proc") == [observation.id]  # ...but not for another one


def test_unprocessed_listing_is_ordered_and_bounded(migrated_db):
    ids = [ingest_one(migrated_db, record_id=f"r{i}", key=f"k{i}").observation.id for i in range(5)]
    assert repo.list_unprocessed_observation_ids(migrated_db, PROC) == ids
    assert repo.list_unprocessed_observation_ids(migrated_db, PROC, limit=2) == ids[:2]
    for bad in (0, 1001, "5", None, True):
        with pytest.raises(InvalidInputError):
            repo.list_unprocessed_observation_ids(migrated_db, PROC, limit=bad)


def test_an_active_attempt_blocks_another_start_for_the_same_processor(world):
    db, observation = world
    repo.start_processing(db, observation.id, PROC, V1)
    for version in (V1, V2):
        with pytest.raises(ConflictError) as info:
            repo.start_processing(db, observation.id, PROC, version)
        assert info.value.code == "attempt_already_active"
    assert len(repo.list_processing_attempts(db, observation.id)) == 1


def test_different_processors_are_independent(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    b = repo.start_processing(db, observation.id, "other_proc", "other_proc.v1")
    assert (a.attempt_number, b.attempt_number) == (1, 1) and a.id != b.id


# ---------------- success

def test_processing_to_processed(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    done = repo.mark_processed(db, a.id)
    assert done.status is D and done.id == a.id and done.attempt_number == 1
    assert done.finished_at is not None and done.finished_at >= a.started_at
    assert done.lease_expires_at is None and done.reason_code is None and done.detail_code is None
    assert done.started_at == a.started_at and repo.get_processing_attempt(db, a.id) == done


def test_a_processed_attempt_is_terminal_and_cannot_change_again(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    done = repo.mark_processed(db, a.id)
    for call in (lambda: repo.mark_processed(db, a.id), lambda: repo.mark_failed(db, a.id, "late_failure"),
                 lambda: repo.mark_quarantined(db, a.id, "late_quarantine"), lambda: repo.renew_lease(db, a.id),
                 lambda: repo.fail_expired_attempt(db, a.id, as_of=datetime.now(timezone.utc) + timedelta(days=1))):
        with pytest.raises(InvariantViolationError) as info:
            call()
        assert info.value.code == "illegal_transition"
    assert repo.get_processing_attempt(db, a.id) == done


# ---------------- failure

def test_processing_to_failed_with_a_reason_and_optional_detail(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    failed = repo.mark_failed(db, a.id, "parse_error", "unexpected_eof")
    assert failed.status is F and (failed.reason_code, failed.detail_code) == ("parse_error", "unexpected_eof")
    assert failed.finished_at is not None and failed.lease_expires_at is None
    bare = repo.mark_failed(db, repo.start_processing(db, observation.id, "second_proc", "second_proc.v1").id, "timeout")
    assert bare.detail_code is None


@pytest.mark.parametrize("reason", ["", "Bad Reason", "Traceback (most recent call last):", "x" * 65, None, 5, "line\nbreak", "the company raised $5M"])
def test_failure_metadata_is_bounded_machine_codes_only(world, reason):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    with pytest.raises(InvalidInputError):
        repo.mark_failed(db, a.id, reason)
    with pytest.raises(InvalidInputError):
        repo.mark_quarantined(db, a.id, reason)
    with pytest.raises(InvalidInputError):
        repo.mark_failed(db, a.id, "valid_reason", reason if reason is not None else "Not Valid")
    assert repo.get_processing_attempt(db, a.id).status is P  # nothing changed


def test_retry_after_failure_is_a_new_attempt_and_the_old_row_is_untouched(world):
    db, observation = world
    first = repo.start_processing(db, observation.id, PROC, V1)
    failed = repo.mark_failed(db, first.id, "parse_error")
    before = row(db, first.id)
    retry = repo.start_processing(db, observation.id, PROC, V1)
    assert retry.attempt_number == 2 and retry.id != first.id and retry.status is P
    assert row(db, first.id) == before and repo.get_processing_attempt(db, first.id) == failed
    assert [a.status for a in repo.list_processing_attempts(db, observation.id)] == [F, P]


def test_a_failed_attempt_never_becomes_processing_again(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    repo.mark_failed(db, a.id, "parse_error")
    with pytest.raises(InvariantViolationError):
        repo.renew_lease(db, a.id)
    with pytest.raises(InvariantViolationError):
        repo.mark_processed(db, a.id)


# ---------------- quarantine

def test_processing_to_quarantined_and_it_is_not_retried_automatically(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    q = repo.mark_quarantined(db, a.id, "media_type_mismatch", "declared_pdf_sniffed_html")
    assert q.status is Q and q.reason_code == "media_type_mismatch" and q.finished_at is not None and q.lease_expires_at is None
    with pytest.raises(InvariantViolationError) as info:
        repo.start_processing(db, observation.id, PROC, V1)                  # same version: not auto-retried
    assert info.value.code == "retry_not_allowed"
    assert len(repo.list_processing_attempts(db, observation.id)) == 1
    for call in (lambda: repo.mark_failed(db, a.id, "again"), lambda: repo.mark_processed(db, a.id), lambda: repo.renew_lease(db, a.id)):
        with pytest.raises(InvariantViolationError):
            call()
    assert repo.get_processing_attempt(db, a.id) == q


# ---------------- reprocessing under a later version

def test_a_processed_observation_is_reprocessed_only_by_a_later_version(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V2)
    repo.mark_processed(db, a.id)
    for version in (V2, V1):
        with pytest.raises(InvariantViolationError) as info:
            repo.start_processing(db, observation.id, PROC, version)
        assert info.value.code == "retry_not_allowed"
    later = repo.start_processing(db, observation.id, PROC, V3)
    assert (later.attempt_number, later.processor_version, later.status) == (2, V3, P)


def test_a_quarantined_observation_can_be_reprocessed_by_a_later_version(world):
    db, observation = world
    repo.mark_quarantined(db, repo.start_processing(db, observation.id, PROC, V1).id, "unsupported_format")
    assert repo.start_processing(db, observation.id, PROC, V2).attempt_number == 2


def test_versions_are_preserved_and_numbering_is_linear_per_observation_and_processor(world):
    db, observation = world
    a1 = repo.mark_failed(db, repo.start_processing(db, observation.id, PROC, V1).id, "timeout")
    a2 = repo.mark_processed(db, repo.start_processing(db, observation.id, PROC, V1).id)
    a3 = repo.start_processing(db, observation.id, PROC, V2)                 # later version: attempt 3, history untouched
    other = repo.mark_processed(db, repo.start_processing(db, observation.id, "second_proc", "second_proc.v1").id)
    assert [(a.attempt_number, a.processor_version, a.status) for a in repo.list_processing_attempts(db, observation.id, PROC)] == [
        (1, V1, F), (2, V1, D), (3, V2, P)]
    assert repo.get_processing_attempt(db, a1.id) == a1 and repo.get_processing_attempt(db, a2.id) == a2
    assert other.attempt_number == 1                                          # numbering is per processor_id
    assert repo.get_latest_attempt(db, observation.id, PROC) == a3
    assert [(a.processor_id, a.attempt_number) for a in repo.list_processing_attempts(db, observation.id)] == [
        (PROC, 1), (PROC, 2), (PROC, 3), ("second_proc", 1)]


def test_history_reads(world):
    db, observation = world
    assert repo.get_processing_attempt(db, 999) is None
    with pytest.raises(InvalidInputError):
        repo.get_processing_attempt(db, 0)
    with pytest.raises(InvalidInputError):
        repo.list_processing_attempts(db, observation.id, "Bad Id")


# ---------------- leases

def test_a_lease_can_be_renewed_while_processing_and_only_the_lease_changes(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1, lease_seconds=30)
    renewed = repo.renew_lease(db, a.id, lease_seconds=600)
    assert renewed.lease_expires_at > a.lease_expires_at + timedelta(minutes=8)
    assert renewed.model_copy(update={"lease_expires_at": a.lease_expires_at}) == a


def test_renewal_never_shortens_a_lease(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1, lease_seconds=600)
    assert repo.renew_lease(db, a.id, lease_seconds=1).lease_expires_at == a.lease_expires_at


def test_renewal_of_a_terminal_or_unknown_attempt_fails_clearly(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1)
    repo.mark_failed(db, a.id, "timeout")
    with pytest.raises(InvariantViolationError) as info:
        repo.renew_lease(db, a.id)
    assert info.value.code == "illegal_transition"
    with pytest.raises(NotFoundError):
        repo.renew_lease(db, 999999)


def test_an_expired_lease_alone_does_not_change_the_row_and_the_attempt_can_still_be_renewed_or_finished(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1, lease_seconds=1)
    time.sleep(1.3)
    still = repo.get_processing_attempt(db, a.id)
    assert still == a and still.status is P                                    # expiry did not mutate anything
    assert still.is_lease_expired(datetime.now(timezone.utc)) is True
    assert repo.renew_lease(db, a.id, lease_seconds=60).lease_expires_at > datetime.now(timezone.utc)   # a late worker may renew
    assert repo.mark_processed(db, a.id).status is D


def test_an_expired_attempt_is_failed_explicitly_with_the_lease_expired_reason(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1, lease_seconds=1)
    time.sleep(1.3)
    failed = repo.fail_expired_attempt(db, a.id)                               # database clock
    assert failed.status is F and failed.reason_code == LEASE_EXPIRED_REASON == "lease_expired"
    assert failed.detail_code is None and failed.lease_expires_at is None and failed.finished_at is not None
    assert repo.start_processing(db, observation.id, PROC, V1).attempt_number == 2   # and it can now be retried


def test_a_live_lease_cannot_be_failed_as_expired(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1, lease_seconds=600)
    with pytest.raises(InvariantViolationError) as info:
        repo.fail_expired_attempt(db, a.id)
    assert info.value.code == "lease_not_expired" and repo.get_processing_attempt(db, a.id) == a


def test_expiry_can_be_evaluated_against_a_supplied_clock_for_deterministic_tests(world):
    db, observation = world
    a = repo.start_processing(db, observation.id, PROC, V1, lease_seconds=300)
    with pytest.raises(InvariantViolationError) as info:
        repo.fail_expired_attempt(db, a.id, as_of=a.lease_expires_at - timedelta(seconds=1))
    assert info.value.code == "lease_not_expired"
    assert repo.get_processing_attempt(db, a.id) == a
    failed = repo.fail_expired_attempt(db, a.id, as_of=a.lease_expires_at)      # boundary: at expiry counts as expired
    assert failed.reason_code == "lease_expired"
    with pytest.raises(InvalidInputError):
        repo.fail_expired_attempt(db, a.id, as_of=datetime(2026, 1, 1))         # a naive clock is refused


def test_failing_an_unknown_or_already_finished_attempt(world):
    db, observation = world
    with pytest.raises(NotFoundError) as info:
        repo.fail_expired_attempt(db, 999999)
    assert info.value.code == "attempt_not_found"
    a = repo.start_processing(db, observation.id, PROC, V1)
    repo.mark_processed(db, a.id)
    with pytest.raises(InvariantViolationError) as info:
        repo.fail_expired_attempt(db, a.id, as_of=datetime.now(timezone.utc) + timedelta(days=1))
    assert info.value.code == "illegal_transition"


# ---------------- surface and transactions

def test_the_repository_exposes_exactly_the_lifecycle_and_history_operations():
    import inspect
    public = {n for n, v in vars(repo).items() if callable(v) and not n.startswith("_") and getattr(v, "__module__", "") == repo.__name__}
    assert public == {"start_processing", "renew_lease", "mark_processed", "mark_failed", "mark_quarantined", "fail_expired_attempt",
                      "get_processing_attempt", "list_processing_attempts", "get_latest_attempt", "list_unprocessed_observation_ids"}
    source = inspect.getsource(repo).lower()
    assert "delete(" not in source and "delete from" not in source and "observation_table).values" not in source


def test_a_connection_joins_the_callers_transaction(world):
    db, observation = world
    with db.connect() as conn:
        txn = conn.begin()
        a = repo.start_processing(conn, observation.id, PROC, V1)
        repo.mark_processed(conn, a.id)
        assert repo.get_latest_attempt(conn, observation.id, PROC).status is D
        txn.rollback()
    assert repo.get_latest_attempt(db, observation.id, PROC) is None
