"""
The append-only property, demonstrated by actually attempting to break it with
direct SQL (bypassing the repositories), not by inspecting trigger definitions.
Also: evidence preserves the Source it references.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.v2.repositories import observations as obs_repo
from app.v2.tests.db.evidence_helpers import count, fetch_row, make_observation, refused, register_source, store_payload

pytestmark = pytest.mark.db


@pytest.fixture
def evidence(migrated_db):
    source = register_source(migrated_db)
    digest = store_payload(migrated_db, b"immutable evidence")
    stored = obs_repo.store_observation(migrated_db, make_observation(digest, source_record_identifier="rec-1")).stored
    return migrated_db, source, digest, stored


def snapshot(db):
    with db.connect() as conn:
        return (
            [tuple(r) for r in conn.execute(text("SELECT * FROM v2.raw_payload ORDER BY content_hash"))],
            [tuple(r) for r in conn.execute(text("SELECT * FROM v2.observation ORDER BY id"))],
            [tuple(r) for r in conn.execute(text("SELECT * FROM v2.source ORDER BY id"))],
        )


# ---------------- UPDATE

@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE v2.raw_payload SET payload_bytes = '\\x00'::bytea",
        "UPDATE v2.raw_payload SET size_bytes = size_bytes",                       # even a no-op update
        "UPDATE v2.raw_payload SET storage_kind = 'inline'",
        "UPDATE v2.raw_payload SET content_hash = repeat('a', 64)",
        "UPDATE v2.observation SET observed_time = now()",
        "UPDATE v2.observation SET source_record_identifier = 'changed'",
        "UPDATE v2.observation SET observation_type = observation_type",           # even a no-op update
        "UPDATE v2.observation SET recorded_time = '2001-01-01T00:00:00+00:00'",
        "UPDATE v2.observation SET event_time = NULL, event_time_precision = NULL",
        "UPDATE v2.observation SET sniffed_media_type = 'unknown'",
    ],
)
def test_direct_update_is_blocked_and_changes_nothing(evidence, sql):
    db = evidence[0]
    before = snapshot(db)
    _, message = refused(db, sql, exc=IntegrityError)
    assert "is append-only: UPDATE is not permitted" in message
    assert snapshot(db) == before


def test_an_upsert_cannot_be_used_to_rewrite_evidence(evidence):
    db, _, digest, stored = evidence
    before = snapshot(db)
    _, message = refused(db, "INSERT INTO v2.raw_payload (content_hash, storage_kind, size_bytes, payload_bytes) "
                             "VALUES (:h, 'inline', 1, '\\x00'::bytea) ON CONFLICT (content_hash) DO UPDATE SET payload_bytes = EXCLUDED.payload_bytes",
                         {"h": digest}, exc=IntegrityError)
    assert "append-only" in message or "check" in message.lower()
    assert snapshot(db) == before


# ---------------- DELETE

@pytest.mark.parametrize("table", ["v2.raw_payload", "v2.observation"])
def test_direct_delete_is_blocked_and_the_rows_survive(evidence, table):
    db = evidence[0]
    before = snapshot(db)
    _, message = refused(db, f"DELETE FROM {table}", exc=IntegrityError)
    assert "is append-only: DELETE is not permitted" in message
    assert snapshot(db) == before


def test_delete_with_a_predicate_is_also_blocked(evidence):
    db, _, digest, stored = evidence
    refused(db, "DELETE FROM v2.observation WHERE id = :i", {"i": stored.id}, exc=IntegrityError)
    refused(db, "DELETE FROM v2.raw_payload WHERE content_hash = :h", {"h": digest}, exc=IntegrityError)
    assert count(db, "observation") == 1 and count(db, "raw_payload") == 1


# ---------------- TRUNCATE

def test_direct_truncate_of_observation_is_blocked_by_the_append_only_trigger(evidence):
    db = evidence[0]
    before = snapshot(db)
    _, message = refused(db, "TRUNCATE v2.observation", exc=IntegrityError)  # nothing references it: only the trigger stands in the way
    assert "is append-only: TRUNCATE is not permitted" in message
    assert snapshot(db) == before


def test_direct_truncate_of_raw_payload_is_blocked_twice_over(evidence):
    db = evidence[0]
    before = snapshot(db)
    # Plain TRUNCATE: PostgreSQL's own foreign-key rule refuses first (an observation table references it).
    _, message = refused(db, "TRUNCATE v2.raw_payload", exc=DBAPIError)
    assert "referenced in a foreign key constraint" in message
    # With CASCADE the FK rule steps aside and the append-only trigger is what stops it.
    _, message = refused(db, "TRUNCATE v2.raw_payload CASCADE", exc=IntegrityError)
    assert "is append-only: TRUNCATE is not permitted" in message
    assert snapshot(db) == before


@pytest.mark.parametrize("sql", ["TRUNCATE v2.observation, v2.raw_payload", "TRUNCATE v2.raw_payload CASCADE",
                                 "TRUNCATE v2.source CASCADE", "TRUNCATE v2.observation RESTART IDENTITY"])
def test_truncate_variants_and_cascades_are_blocked_too(evidence, sql):
    db = evidence[0]
    before = snapshot(db)
    refused(db, sql, exc=(IntegrityError, DBAPIError))
    assert snapshot(db) == before


def test_truncating_the_referenced_source_is_blocked_by_its_foreign_key_or_cascade_guard(evidence):
    db = evidence[0]
    refused(db, "TRUNCATE v2.source", exc=DBAPIError)  # PostgreSQL refuses to truncate a table that evidence references
    assert count(db, "source") == 1


def test_evidence_survives_a_batch_of_attacks_in_one_go(evidence):
    db, _, digest, stored = evidence
    before = snapshot(db)
    for sql in ("UPDATE v2.observation SET collector_id = 'admin:attacker'", "DELETE FROM v2.observation",
                "TRUNCATE v2.observation", "UPDATE v2.raw_payload SET size_bytes = 0", "DELETE FROM v2.raw_payload",
                "TRUNCATE v2.raw_payload"):
        with pytest.raises(DBAPIError):
            with db.begin() as conn:
                conn.execute(text(sql))
    assert snapshot(db) == before
    assert obs_repo.get_observation_lineage(db, stored.id).payload.payload_bytes == b"immutable evidence"


# ---------------- Source preservation

def test_a_source_that_evidence_references_cannot_be_deleted(evidence):
    db, source, _, _ = evidence
    with pytest.raises(IntegrityError) as info:
        with db.begin() as conn:
            conn.execute(text("DELETE FROM v2.source WHERE id = :i"), {"i": source.id})
    assert info.value.orig.diag.constraint_name == "fk_observation_source_id_source"
    assert fetch_row(db, "source", "id = :i", {"i": source.id}) is not None


def test_a_payload_that_an_observation_references_cannot_be_deleted_even_by_disabling_nothing(evidence):
    db, _, digest, _ = evidence
    refused(db, "DELETE FROM v2.raw_payload WHERE content_hash = :h", {"h": digest}, exc=IntegrityError)
    assert count(db, "raw_payload") == 1


def test_a_source_without_evidence_is_still_removable_by_direct_sql_there_is_no_source_delete_api(migrated_db):
    """Documents the boundary: only referenced sources are protected (the repository has no delete at all)."""
    lonely = register_source(migrated_db, "lonely_source")
    with migrated_db.begin() as conn:
        conn.execute(text("DELETE FROM v2.source WHERE id = :i"), {"i": lonely.id})
    assert count(migrated_db, "source") == 0
