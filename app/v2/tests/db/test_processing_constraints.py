"""
v2.processing_attempt protected against DIRECT SQL: identity is frozen, terminal rows are
immutable, illegal state combinations are impossible, history cannot be removed.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.v2.tests.db.evidence_helpers import count, fetch_row, ingest_one, refused

pytestmark = pytest.mark.db

FUTURE = "now() + interval '5 minutes'"


@pytest.fixture
def world(migrated_db):
    first = ingest_one(migrated_db, record_id="rec-1", key="k1").observation
    second = ingest_one(migrated_db, record_id="rec-2", key="k2").observation
    return migrated_db, first.id, second.id


def insert_sql(observation_id, *, number=1, processor="fin_extractor", version=None, status="processing",
               lease=FUTURE, finished="NULL", reason="NULL", detail="NULL", started="now()"):
    version = version or f"{processor}.v1"
    return (f"INSERT INTO v2.processing_attempt (observation_id, processor_id, processor_version, attempt_number, status, "
            f"started_at, finished_at, lease_expires_at, reason_code, detail_code) VALUES "
            f"({observation_id}, '{processor}', '{version}', {number}, '{status}', {started}, {finished}, {lease}, {reason}, {detail}) RETURNING id")


def run(db, sql):
    with db.begin() as conn:
        return conn.execute(text(sql)).scalar()


def rejected(db, sql, exc=IntegrityError):
    diag, message = refused(db, sql, exc=exc)
    return (getattr(diag, "constraint_name", None) or getattr(diag, "column_name", None) or message), message


def start(db, oid, **kw):
    return run(db, insert_sql(oid, **kw))


def row(db, attempt_id):
    return fetch_row(db, "processing_attempt", "id = :i", {"i": attempt_id})


# ---------------- insert rules

def test_started_at_is_the_database_clock_even_when_the_caller_supplies_one(world):
    db, oid, _ = world
    attempt_id = start(db, oid, started="'2001-01-01T00:00:00+00:00'")
    assert row(db, attempt_id)["started_at"].year >= 2026


def test_an_attempt_must_start_in_processing(world):
    db, oid, _ = world
    for status, kwargs in (("processed", dict(lease="NULL", finished="now()")),
                           ("failed", dict(lease="NULL", finished="now()", reason="'x_reason'")),
                           ("quarantined", dict(lease="NULL", finished="now()", reason="'x_reason'"))):
        _, message = rejected(db, insert_sql(oid, status=status, **kwargs))
        assert "must start in processing" in message
    assert count(db, "processing_attempt") == 0


@pytest.mark.parametrize("kwargs", [
    dict(finished="now()"),                                   # processing but already finished
    dict(lease="NULL"),                                       # processing with no lease
    dict(reason="'x_reason'"),                                # processing with failure metadata
    dict(detail="'x_detail'"),
])
def test_invalid_processing_rows_are_rejected(world, kwargs):
    db, oid, _ = world
    # a supplied finished_at can also trip the finished-not-before-started CHECK first (started_at is stamped later)
    assert rejected(db, insert_sql(oid, **kwargs))[0] in ("ck_processing_attempt_state_shape", "ck_processing_attempt_finished_not_before_started")


# ---------------- state combinations on transition

def transition(db, oid, sql_set):
    attempt_id = start(db, oid)
    return attempt_id, rejected(db, f"UPDATE v2.processing_attempt SET {sql_set} WHERE id = {attempt_id}")


@pytest.mark.parametrize("assignment", [
    "status = 'processed'",                                                   # lease still set
    "status = 'processed', lease_expires_at = NULL, reason_code = 'x_reason'",  # processed with a failure reason
    "status = 'processed', lease_expires_at = NULL, detail_code = 'x_detail'",
    "status = 'failed', lease_expires_at = NULL",                             # failed without a reason
    "status = 'quarantined', lease_expires_at = NULL",
    "status = 'failed', reason_code = 'x_reason'",                            # failed but the lease was not cleared
    "status = 'failed', lease_expires_at = NULL, detail_code = 'only_detail'",
    "reason_code = 'x_reason'",                                               # processing with failure metadata
    "lease_expires_at = NULL",                                                # processing without a lease
    "finished_at = now()",                                                    # processing but finished
])
def test_invalid_state_combinations_are_rejected_and_change_nothing(world, assignment):
    db, oid, _ = world
    attempt_id = start(db, oid)
    before = row(db, attempt_id)
    assert rejected(db, f"UPDATE v2.processing_attempt SET {assignment} WHERE id = {attempt_id}")[0] == "ck_processing_attempt_state_shape"
    assert row(db, attempt_id) == before


def test_an_unknown_status_is_rejected(world):
    db, oid, _ = world
    attempt_id = start(db, oid)
    # the vocabulary CHECK and the state-shape CHECK (its ELSE branch) both reject it; PostgreSQL names the first it evaluates
    assert rejected(db, f"UPDATE v2.processing_attempt SET status = 'completed', lease_expires_at = NULL WHERE id = {attempt_id}")[0] in (
        "ck_processing_attempt_status_allowed", "ck_processing_attempt_state_shape")


# ---------------- legal lifecycle mutations ARE possible by SQL, with database-owned timing

@pytest.mark.parametrize("assignment, status, reason", [
    ("status = 'processed', lease_expires_at = NULL", "processed", None),
    ("status = 'failed', lease_expires_at = NULL, reason_code = 'parse_error'", "failed", "parse_error"),
    ("status = 'quarantined', lease_expires_at = NULL, reason_code = 'bad_media', detail_code = 'mismatch'", "quarantined", "bad_media"),
])
def test_a_legal_transition_by_sql_is_accepted_and_finished_at_is_the_databases(world, assignment, status, reason):
    db, oid, _ = world
    attempt_id = start(db, oid)
    run(db, f"UPDATE v2.processing_attempt SET {assignment}, finished_at = '2001-01-01T00:00:00+00:00' WHERE id = {attempt_id} RETURNING id")
    r = row(db, attempt_id)
    assert (r["status"], r["reason_code"], r["lease_expires_at"]) == (status, reason, None)
    assert r["finished_at"].year >= 2026 and r["finished_at"] >= r["started_at"]   # the caller's finished_at was ignored


def test_the_lease_may_be_renewed_forward_but_never_backward(world):
    db, oid, _ = world
    attempt_id = start(db, oid)
    before = row(db, attempt_id)["lease_expires_at"]
    run(db, f"UPDATE v2.processing_attempt SET lease_expires_at = lease_expires_at + interval '10 minutes' WHERE id = {attempt_id} RETURNING id")
    assert row(db, attempt_id)["lease_expires_at"] > before
    _, message = rejected(db, f"UPDATE v2.processing_attempt SET lease_expires_at = lease_expires_at - interval '1 hour' WHERE id = {attempt_id}")
    assert "cannot move backwards" in message


# ---------------- immutable identity

@pytest.mark.parametrize("column, new_value", [
    ("observation_id", "{other}"), ("processor_id", "'other_proc'"), ("processor_version", "'fin_extractor.v9'"),
    ("attempt_number", "7"), ("started_at", "now() - interval '1 day'"),
])
def test_identity_and_history_fields_cannot_be_rewritten(world, column, new_value):
    db, oid, other = world
    attempt_id = start(db, oid)
    before = row(db, attempt_id)
    _, message = rejected(db, f"UPDATE v2.processing_attempt SET {column} = {new_value.format(other=other)} WHERE id = {attempt_id}")
    assert f"{column} is immutable" in message
    assert row(db, attempt_id) == before


def test_the_id_cannot_be_rewritten(world):
    db, oid, _ = world
    attempt_id = start(db, oid)
    rejected(db, f"UPDATE v2.processing_attempt SET id = id + 1000 WHERE id = {attempt_id}", exc=(ProgrammingError, IntegrityError))
    assert row(db, attempt_id)["id"] == attempt_id


def test_an_immutable_change_bundled_with_a_legal_transition_rolls_the_whole_update_back(world):
    db, oid, _ = world
    attempt_id = start(db, oid)
    before = row(db, attempt_id)
    rejected(db, f"UPDATE v2.processing_attempt SET status = 'processed', lease_expires_at = NULL, attempt_number = 9 WHERE id = {attempt_id}")
    assert row(db, attempt_id) == before


# ---------------- terminal rows are immutable

@pytest.fixture(params=["processed", "failed", "quarantined"])
def terminal(request, world):
    db, oid, _ = world
    attempt_id = start(db, oid)
    reason = "" if request.param == "processed" else ", reason_code = 'first_reason', detail_code = 'first_detail'"
    run(db, f"UPDATE v2.processing_attempt SET status = '{request.param}', lease_expires_at = NULL{reason} WHERE id = {attempt_id} RETURNING id")
    return db, oid, attempt_id, request.param


@pytest.mark.parametrize("assignment", [
    "status = 'processing', lease_expires_at = now() + interval '5 minutes', finished_at = NULL, reason_code = NULL, detail_code = NULL",
    "status = 'processed', reason_code = NULL, detail_code = NULL",
    "status = 'failed', reason_code = 'changed_reason'",
    "status = 'quarantined', reason_code = 'changed_reason'",
    "reason_code = 'changed_reason'",
    "detail_code = 'changed_detail'",
    "finished_at = now()",
    "lease_expires_at = now() + interval '1 day'",
    "attempt_number = attempt_number",                       # even a no-op update
])
def test_a_terminal_attempt_cannot_be_changed_in_any_way(terminal, assignment):
    db, _, attempt_id, _ = terminal
    before = row(db, attempt_id)
    rejected(db, f"UPDATE v2.processing_attempt SET {assignment} WHERE id = {attempt_id}")
    assert row(db, attempt_id) == before


def test_an_upsert_cannot_revive_or_rewrite_a_terminal_attempt(terminal):
    db, oid, attempt_id, _ = terminal
    before = row(db, attempt_id)
    rejected(db, f"INSERT INTO v2.processing_attempt (observation_id, processor_id, processor_version, attempt_number, status, lease_expires_at) "
                 f"VALUES ({oid}, 'fin_extractor', 'fin_extractor.v1', 1, 'processing', now() + interval '1 hour') "
                 f"ON CONFLICT (observation_id, processor_id, attempt_number) DO UPDATE SET status = 'processing'")
    assert row(db, attempt_id) == before


# ---------------- shapes

@pytest.mark.parametrize("processor", ["A", "x", "Fin Extractor", "1abc", "x" * 65, "fin-extractor"])
def test_processor_id_shape(world, processor):
    db, oid, _ = world
    assert rejected(db, insert_sql(oid, processor=processor, version="fin_extractor.v1"))[0] in (
        "ck_processing_attempt_processor_id_shape", "ck_processing_attempt_processor_version_shape")


@pytest.mark.parametrize("version", ["fin_extractor", "fin_extractor.v0", "fin_extractor.v01", "Fin_extractor.v1", "other_processor.v1",
                                     "fin_extractor.v1234567", "fin_extractor.v1\n"])
def test_processor_version_shape_and_ownership(world, version):
    db, oid, _ = world
    assert rejected(db, insert_sql(oid, version=version))[0] == "ck_processing_attempt_processor_version_shape"


@pytest.mark.parametrize("number", [0, -1])
def test_attempt_numbers_start_at_one(world, number):
    db, oid, _ = world
    assert rejected(db, insert_sql(oid, number=number))[0] == "ck_processing_attempt_attempt_number_positive"


@pytest.mark.parametrize("column", ["reason_code", "detail_code"])
@pytest.mark.parametrize("value", ["Bad Code", "x", "Traceback (most recent call last)", "err\\nor", "x" * 65, "café", "UPPER", "a-b"])
def test_failure_metadata_must_be_a_bounded_machine_code(world, column, value):
    db, oid, _ = world
    attempt_id = start(db, oid)
    reason = value if column == "reason_code" else "valid_reason"
    detail = value if column == "detail_code" else "valid_detail"
    _, message = rejected(db, f"UPDATE v2.processing_attempt SET status = 'failed', lease_expires_at = NULL, "
                              f"reason_code = '{reason}', detail_code = '{detail}' WHERE id = {attempt_id}")
    assert "ck_processing_attempt_" in message or "shape" in message or "violates" in message


@pytest.mark.parametrize("column", ["observation_id", "processor_id", "processor_version", "attempt_number", "status"])
def test_not_null_columns(world, column):
    db, oid, _ = world
    values = dict(observation_id=oid, processor_id="'fin_extractor'", processor_version="'fin_extractor.v1'", attempt_number=1, status="'processing'")
    values[column] = "NULL"
    sql = (f"INSERT INTO v2.processing_attempt (observation_id, processor_id, processor_version, attempt_number, status, lease_expires_at) "
           f"VALUES ({values['observation_id']}, {values['processor_id']}, {values['processor_version']}, {values['attempt_number']}, {values['status']}, {FUTURE})")
    assert rejected(db, sql)[0] == column


def test_the_observation_must_exist(world):
    db, _, _ = world
    assert rejected(db, insert_sql(999999))[0] == "fk_processing_attempt_observation_id_observation"


# ---------------- uniqueness

def test_a_duplicate_attempt_number_is_rejected(world):
    db, oid, _ = world
    first = start(db, oid)
    run(db, f"UPDATE v2.processing_attempt SET status = 'failed', lease_expires_at = NULL, reason_code = 'x_reason' WHERE id = {first} RETURNING id")
    assert rejected(db, insert_sql(oid, number=1))[0] == "uq_processing_attempt_number"
    start(db, oid, number=2)                                              # the next number is fine


def test_a_second_active_attempt_for_the_same_observation_and_processor_is_rejected(world):
    db, oid, other = world
    start(db, oid, number=1)
    assert rejected(db, insert_sql(oid, number=2))[0] == "uq_processing_attempt_one_active"
    start(db, oid, number=1, processor="second_proc")        # another processor: fine
    start(db, other, number=1)                               # another observation: fine


def test_after_a_terminal_state_the_next_active_attempt_is_allowed(world):
    db, oid, _ = world
    first = start(db, oid, number=1)
    run(db, f"UPDATE v2.processing_attempt SET status = 'processed', lease_expires_at = NULL WHERE id = {first} RETURNING id")
    start(db, oid, number=2, version="fin_extractor.v2")
    assert count(db, "processing_attempt") == 2


# ---------------- history cannot be removed

def test_delete_and_truncate_are_blocked(world):
    db, oid, _ = world
    attempt_id = start(db, oid)
    before = row(db, attempt_id)
    _, message = rejected(db, "DELETE FROM v2.processing_attempt")
    assert "is append-only: DELETE is not permitted" in message
    rejected(db, f"DELETE FROM v2.processing_attempt WHERE id = {attempt_id}")
    # Since Increment 8 candidates reference attempts: PostgreSQL's FK rule refuses a plain TRUNCATE first,
    # and with CASCADE the append-only trigger is what stops it.
    _, message = rejected(db, "TRUNCATE v2.processing_attempt", exc=DBAPIError)
    assert "referenced in a foreign key constraint" in message
    _, message = rejected(db, "TRUNCATE v2.processing_attempt CASCADE")
    assert "is append-only: TRUNCATE is not permitted" in message
    assert row(db, attempt_id) == before


def test_an_observation_with_processing_history_cannot_be_removed(world):
    db, oid, _ = world
    start(db, oid)
    rejected(db, f"DELETE FROM v2.observation WHERE id = {oid}")                   # the observation's own append-only trigger
    rejected(db, "TRUNCATE v2.observation", exc=DBAPIError)                        # PostgreSQL's FK rule: attempts (and sightings) reference it
    assert count(db, "observation") == 2 and count(db, "processing_attempt") == 1
