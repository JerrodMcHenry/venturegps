"""
v2.company_candidate / v2.company_candidate_identifier protected against DIRECT SQL:
evidence must exist in the stored bytes, only PROCESSING attempts receive candidates,
rows are immutable, time is the database's.
"""

import hashlib

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.v2.repositories import processing_attempts as attempts
from app.v2.tests.db.candidate_fakes import PAGE, PROC, V1
from app.v2.tests.db.evidence_helpers import count, fetch_row, ingest_one, refused

pytestmark = pytest.mark.db

NAME_START = PAGE.index(b"Acme Robotics")
NAME_END = NAME_START + len(b"Acme Robotics")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def world(migrated_db):
    observation = ingest_one(migrated_db, payload=PAGE).observation
    attempt = attempts.start_processing(migrated_db, observation.id, PROC, V1)
    return migrated_db, observation, attempt


def insert_candidate(db, attempt_id, *, ordinal=1, name="Acme Robotics", start=NAME_START, end=NAME_END, hash_=None, extra=""):
    hash_ = hash_ if hash_ is not None else sha(PAGE[start:end])
    sql = (f"INSERT INTO v2.company_candidate (processing_attempt_id, candidate_ordinal, proposed_name, name_evidence_start, "
           f"name_evidence_end, name_evidence_hash{', created_at' if extra else ''}) VALUES (:a, :o, :n, :s, :e, :h{', :c' if extra else ''}) RETURNING id")
    params = dict(a=attempt_id, o=ordinal, n=name, s=start, e=end, h=hash_)
    if extra:
        params["c"] = extra
    with db.begin() as conn:
        return conn.execute(text(sql), params).scalar()


def insert_identifier(db, candidate_id, *, ordinal=1, type_="domain", value="acmerobotics.com", start=None, end=None, hash_=None):
    if start is None:
        start = PAGE.lower().index(b"acmerobotics.com")
        end = start + len(b"acmerobotics.com")
    hash_ = hash_ if hash_ is not None else sha(PAGE[start:end])
    with db.begin() as conn:
        return conn.execute(text("INSERT INTO v2.company_candidate_identifier (candidate_id, identifier_ordinal, identifier_type, identifier_value, "
                                 "evidence_start, evidence_end, evidence_hash) VALUES (:c, :o, :t, :v, :s, :e, :h) RETURNING id"),
                            dict(c=candidate_id, o=ordinal, t=type_, v=value, s=start, e=end, h=hash_)).scalar()


def rejected(db, sql_or_callable, params=None, exc=IntegrityError):
    with pytest.raises(exc) as info:
        if callable(sql_or_callable):
            sql_or_callable()
        else:
            with db.begin() as conn:
                conn.execute(text(sql_or_callable), params or {})
    orig = info.value.orig
    diag = getattr(orig, "diag", None)
    return (getattr(diag, "constraint_name", None) or getattr(diag, "column_name", None) or ""), str(orig)


# ---------------- the happy path and the database-owned clock

def test_a_valid_candidate_and_identifier_can_be_inserted_directly(world):
    db, _, attempt = world
    cid = insert_candidate(db, attempt.id)
    insert_identifier(db, cid)
    assert count(db, "company_candidate") == 1 and count(db, "company_candidate_identifier") == 1


def test_created_at_is_the_database_clock_even_when_the_caller_supplies_one(world):
    db, _, attempt = world
    cid = insert_candidate(db, attempt.id, extra="2001-01-01T00:00:00+00:00")
    assert fetch_row(db, "company_candidate", "id = :i", {"i": cid})["created_at"].year >= 2026


# ---------------- evidence must exist in the immutable payload

@pytest.mark.parametrize("start, end", [(len(PAGE) - 3, len(PAGE) + 5), (len(PAGE) + 10, len(PAGE) + 20)])
def test_out_of_range_name_evidence_is_rejected_by_the_database(world, start, end):
    db, _, attempt = world
    _, message = rejected(db, lambda: insert_candidate(db, attempt.id, start=start, end=end, hash_="a" * 64))
    assert "name evidence does not match the stored payload bytes" in message and count(db, "company_candidate") == 0


def test_a_wrong_evidence_hash_is_rejected_by_the_database(world):
    db, _, attempt = world
    _, message = rejected(db, lambda: insert_candidate(db, attempt.id, hash_="0" * 64))
    assert "does not match the stored payload bytes" in message


def test_evidence_from_a_different_payload_is_rejected_by_the_database(world):
    db, _, attempt = world
    other = b"<html><body><h1>Zeta Labs LLC</h1></body></html>"
    start = other.index(b"Zeta Labs")
    rejected(db, lambda: insert_candidate(db, attempt.id, name="Zeta Labs", start=start, end=start + 9, hash_=sha(other[start:start + 9])))


def test_a_one_byte_shift_is_rejected_by_the_database(world):
    db, _, attempt = world
    rejected(db, lambda: insert_candidate(db, attempt.id, start=NAME_START + 1, end=NAME_END + 1, hash_=sha(PAGE[NAME_START:NAME_END])))


def test_identifier_evidence_is_verified_by_the_database_too(world):
    db, _, attempt = world
    cid = insert_candidate(db, attempt.id)
    _, message = rejected(db, lambda: insert_identifier(db, cid, hash_="0" * 64))
    assert "identifier: evidence does not match" in message or "evidence does not match the stored payload bytes" in message
    rejected(db, lambda: insert_identifier(db, cid, start=len(PAGE) - 2, end=len(PAGE) + 9, hash_="a" * 64))
    assert count(db, "company_candidate_identifier") == 0


def test_the_database_verifies_multibyte_byte_offsets(migrated_db):
    from app.v2.tests.db.candidate_fakes import MULTIBYTE
    observation = ingest_one(migrated_db, payload=MULTIBYTE).observation
    attempt = attempts.start_processing(migrated_db, observation.id, PROC, V1)
    start = MULTIBYTE.index(b"Acme")
    end = start + 4
    with migrated_db.begin() as conn:
        conn.execute(text("INSERT INTO v2.company_candidate (processing_attempt_id, candidate_ordinal, proposed_name, name_evidence_start, name_evidence_end, name_evidence_hash) "
                          "VALUES (:a, 1, 'Acme', :s, :e, :h)"), dict(a=attempt.id, s=start, e=end, h=sha(MULTIBYTE[start:end])))
    char_start = MULTIBYTE.decode().index("Acme")
    rejected(migrated_db, "INSERT INTO v2.company_candidate (processing_attempt_id, candidate_ordinal, proposed_name, name_evidence_start, name_evidence_end, name_evidence_hash) "
                          "VALUES (:a, 2, 'Acme', :s, :e, :h)", dict(a=attempt.id, s=char_start, e=char_start + 4, h=sha(b"Acme")))


# ---------------- only PROCESSING attempts receive candidates (database backstop)

@pytest.mark.parametrize("finish", [
    lambda db, a: attempts.mark_processed(db, a.id),
    lambda db, a: attempts.mark_failed(db, a.id, "some_failure"),
    lambda db, a: attempts.mark_quarantined(db, a.id, "some_quarantine"),
])
def test_a_terminal_attempt_cannot_receive_candidates_by_direct_sql(world, finish):
    db, _, attempt = world
    cid = insert_candidate(db, attempt.id)
    finish(db, attempt)
    _, message = rejected(db, lambda: insert_candidate(db, attempt.id, ordinal=2))
    assert "only be added while the attempt is processing" in message
    _, message = rejected(db, lambda: insert_identifier(db, cid))
    assert "identifiers can only be added while the attempt is processing" in message
    assert count(db, "company_candidate") == 1 and count(db, "company_candidate_identifier") == 0


def test_the_attempt_must_exist(world):
    db, _, _ = world
    name, _ = rejected(db, lambda: insert_candidate(db, 999999))
    assert name == "fk_company_candidate_processing_attempt_id_processing_attempt"


def test_the_candidate_must_exist_for_an_identifier(world):
    db, _, _ = world
    name, _ = rejected(db, lambda: insert_identifier(db, 999999))
    assert name == "fk_company_candidate_identifier_candidate_id_company_candidate"


# ---------------- shapes and uniqueness

def test_the_ordinal_is_unique_per_attempt_and_positive(world):
    db, observation, attempt = world
    insert_candidate(db, attempt.id, ordinal=1)
    assert rejected(db, lambda: insert_candidate(db, attempt.id, ordinal=1))[0] == "uq_company_candidate_ordinal"
    for bad in (0, -1, 1001):
        assert rejected(db, lambda bad=bad: insert_candidate(db, attempt.id, ordinal=bad))[0] == "ck_company_candidate_ordinal_range"
    other = attempts.start_processing(db, observation.id, "other_finder", "other_finder.v1")
    insert_candidate(db, other.id, ordinal=1)                                     # ordinals are scoped to the attempt


def test_the_name_is_not_unique_it_is_not_identity(world):
    db, _, attempt = world
    insert_candidate(db, attempt.id, ordinal=1)
    insert_candidate(db, attempt.id, ordinal=2)                                    # same name, same evidence: still two candidates
    assert count(db, "company_candidate") == 2


@pytest.mark.parametrize("name", ["", " Acme Robotics", "Acme Robotics ", "Acme\nRobotics", "x" * 301])
def test_the_name_shape(world, name):
    db, _, attempt = world
    assert rejected(db, lambda: insert_candidate(db, attempt.id, name=name))[0] == "ck_company_candidate_proposed_name_valid"


@pytest.mark.parametrize("start, end", [(-1, 5), (5, 5), (9, 5), (0, 4097)])
def test_a_malformed_span_is_rejected(world, start, end):
    db, _, attempt = world
    # The BEFORE INSERT evidence trigger runs ahead of the CHECKs and refuses these first; the CHECK is the second layer.
    name, message = rejected(db, lambda: insert_candidate(db, attempt.id, start=start, end=end, hash_="a" * 64))
    assert name == "ck_company_candidate_name_evidence_span" or "does not match the stored payload bytes" in message or "span is malformed" in message
    assert count(db, "company_candidate") == 0


@pytest.mark.parametrize("bad", ["A" * 64, "a" * 63, "g" * 64, ""])
def test_a_malformed_evidence_hash_is_rejected(world, bad):
    db, _, attempt = world
    name, message = rejected(db, lambda: insert_candidate(db, attempt.id, hash_=bad))
    assert name == "ck_company_candidate_name_evidence_hash_shape" or "does not match the stored payload bytes" in message
    assert count(db, "company_candidate") == 0


def test_identifier_vocabulary_and_value_shapes(world):
    db, _, attempt = world
    cid = insert_candidate(db, attempt.id)
    assert rejected(db, lambda: insert_identifier(db, cid, type_="email", value="a@b.co"))[0] == "ck_company_candidate_identifier_type_allowed"
    for bad in ("Example.com", "example", "a_b.com", "https://acme.com", "-a.com", "a..com"):
        assert rejected(db, lambda bad=bad: insert_identifier(db, cid, value=bad))[0] == "ck_company_candidate_identifier_value_valid"
    for bad in ("ftp://acme.com", "acme.com", "https://u:p@acme.com", "https://acme.com/a b", "https:///x"):
        assert rejected(db, lambda bad=bad: insert_identifier(db, cid, type_="website_url", value=bad))[0] == "ck_company_candidate_identifier_value_valid"


def test_duplicate_identifier_values_and_ordinals_are_rejected(world):
    db, _, attempt = world
    cid = insert_candidate(db, attempt.id)
    insert_identifier(db, cid)
    assert rejected(db, lambda: insert_identifier(db, cid, ordinal=2))[0] == "uq_company_candidate_identifier_value"
    assert rejected(db, lambda: insert_identifier(db, cid, ordinal=1, value="www.acmerobotics.com"))[0] in (
        "uq_company_candidate_identifier_ordinal", "ck_company_candidate_identifier_value_valid")


# ---------------- append-only: UPDATE / DELETE / TRUNCATE

@pytest.fixture
def stored(world):
    db, _, attempt = world
    cid = insert_candidate(db, attempt.id)
    iid = insert_identifier(db, cid)
    return db, attempt, cid, iid


def snapshot(db):
    with db.connect() as conn:
        return ([tuple(r) for r in conn.execute(text("SELECT * FROM v2.company_candidate ORDER BY id"))],
                [tuple(r) for r in conn.execute(text("SELECT * FROM v2.company_candidate_identifier ORDER BY id"))])


@pytest.mark.parametrize("sql", [
    "UPDATE v2.company_candidate SET proposed_name = 'Renamed'",
    "UPDATE v2.company_candidate SET candidate_ordinal = 9",
    "UPDATE v2.company_candidate SET name_evidence_hash = repeat('0', 64)",
    "UPDATE v2.company_candidate SET created_at = now()",
    "UPDATE v2.company_candidate SET proposed_name = proposed_name",              # even a no-op update
    "UPDATE v2.company_candidate_identifier SET identifier_value = 'other.com'",
    "UPDATE v2.company_candidate_identifier SET evidence_hash = repeat('0', 64)",
    "UPDATE v2.company_candidate_identifier SET identifier_ordinal = identifier_ordinal",
])
def test_direct_update_is_blocked_and_changes_nothing(stored, sql):
    db = stored[0]
    before = snapshot(db)
    _, message = rejected(db, sql)
    assert "is append-only: UPDATE is not permitted" in message
    assert snapshot(db) == before


@pytest.mark.parametrize("table", ["v2.company_candidate", "v2.company_candidate_identifier"])
def test_direct_delete_is_blocked_and_the_rows_survive(stored, table):
    db = stored[0]
    before = snapshot(db)
    _, message = rejected(db, f"DELETE FROM {table}")
    assert "is append-only: DELETE is not permitted" in message
    assert snapshot(db) == before


def test_truncate_is_blocked_on_both_tables(stored):
    db = stored[0]
    before = snapshot(db)
    _, message = rejected(db, "TRUNCATE v2.company_candidate_identifier")                    # nothing references it: only the trigger
    assert "is append-only: TRUNCATE is not permitted" in message
    _, message = rejected(db, "TRUNCATE v2.company_candidate", exc=DBAPIError)               # the identifier FK refuses first
    assert "referenced in a foreign key constraint" in message
    for sql in ("TRUNCATE v2.company_candidate CASCADE", "TRUNCATE v2.processing_attempt CASCADE", "TRUNCATE v2.company_candidate RESTART IDENTITY CASCADE"):
        _, message = rejected(db, sql)
        assert "is append-only: TRUNCATE is not permitted" in message
    assert snapshot(db) == before


def test_an_upsert_cannot_rewrite_a_candidate(stored):
    db, attempt, _, _ = stored
    before = snapshot(db)
    _, message = rejected(db, "INSERT INTO v2.company_candidate (processing_attempt_id, candidate_ordinal, proposed_name, name_evidence_start, name_evidence_end, name_evidence_hash) "
                              "VALUES (:a, 1, 'Acme Robotics', :s, :e, :h) ON CONFLICT (processing_attempt_id, candidate_ordinal) DO UPDATE SET proposed_name = 'Hijacked'",
                          dict(a=attempt.id, s=NAME_START, e=NAME_END, h=sha(PAGE[NAME_START:NAME_END])))
    assert "append-only" in message
    assert snapshot(db) == before


def test_the_attempt_and_evidence_a_candidate_references_cannot_be_removed(stored):
    db, attempt, cid, _ = stored
    rejected(db, f"DELETE FROM v2.processing_attempt WHERE id = {attempt.id}")
    rejected(db, "DELETE FROM v2.observation")
    assert count(db, "processing_attempt") == 1 and count(db, "company_candidate") == 1


def test_a_terminal_attempts_row_stays_immutable_with_candidates_attached(stored):
    db, attempt, _, _ = stored
    done = attempts.mark_processed(db, attempt.id)
    rejected(db, f"UPDATE v2.processing_attempt SET status = 'processing', lease_expires_at = now() + interval '1 hour', finished_at = NULL WHERE id = {attempt.id}")
    assert attempts.get_processing_attempt(db, attempt.id) == done
