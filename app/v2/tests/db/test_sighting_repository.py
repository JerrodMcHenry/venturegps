"""Sighting persistence primitives, and the direct-SQL protection of v2.observation_sighting."""

import inspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.v2.domain.errors import InvalidInputError
from app.v2.domain.sighting import Sighting, StoredSighting
from app.v2.repositories import observations as obs_repo
from app.v2.repositories import sightings as repo
from app.v2.repositories.errors import NotFoundError
from app.v2.tests.db.evidence_helpers import OBSERVED, count, fetch_row, make_observation, refused, register_source, store_payload

pytestmark = pytest.mark.db


@pytest.fixture
def world(migrated_db):
    source = register_source(migrated_db)
    digest = store_payload(migrated_db, b"evidence")
    observation = obs_repo.store_observation(migrated_db, make_observation(digest, source_record_identifier="rec-1")).stored
    return migrated_db, source, digest, observation


def sighting(**overrides):
    base = dict(observed_time=OBSERVED, collector_id="admin:user_2abc", collection_version="manual_upload.v1", acquisition_key="run_1")
    base.update(overrides)
    return Sighting(**base)


# ---------------- repository behavior

def test_store_and_read_back(world):
    db, _, _, observation = world
    result = repo.store_sighting(db, observation.id, sighting())
    assert result.created is True and isinstance(result.stored, StoredSighting)
    assert result.stored.sighting == sighting() and result.stored.observation_id == observation.id
    assert repo.get_sighting_by_id(db, result.stored.id) == result.stored
    assert repo.find_sighting(db, observation.id, "run_1") == result.stored


def test_the_same_acquisition_key_is_idempotent_and_returns_the_existing_sighting(world):
    db, _, _, observation = world
    first = repo.store_sighting(db, observation.id, sighting())
    again = repo.store_sighting(db, observation.id, sighting(observed_time=OBSERVED + timedelta(hours=5), collector_id="admin:other"))
    assert (first.created, again.created) == (True, False)
    assert again.stored == first.stored and again.stored.sighting.observed_time == OBSERVED  # not rewritten
    assert count(db, "observation_sighting") == 1


def test_a_new_key_for_the_same_observation_is_a_new_sighting_even_at_the_same_time(world):
    db, _, _, observation = world
    a = repo.store_sighting(db, observation.id, sighting(acquisition_key="run_1")).stored
    b = repo.store_sighting(db, observation.id, sighting(acquisition_key="run_2")).stored                       # same observed_time
    c = repo.store_sighting(db, observation.id, sighting(acquisition_key="run_3", observed_time=OBSERVED + timedelta(hours=1))).stored
    assert len({a.id, b.id, c.id}) == 3


def test_the_same_key_may_be_used_for_different_observations(world):
    db, _, digest, observation = world
    other = obs_repo.store_observation(db, make_observation(digest, source_record_identifier="rec-2")).stored
    a = repo.store_sighting(db, observation.id, sighting(acquisition_key="run_42")).stored
    b = repo.store_sighting(db, other.id, sighting(acquisition_key="run_42")).stored   # one collection run, many records
    assert a.id != b.id


def test_listing_is_ordered_by_observed_time_then_id_even_when_recorded_out_of_order(world):
    db, _, _, observation = world
    late = repo.store_sighting(db, observation.id, sighting(acquisition_key="late", observed_time=OBSERVED + timedelta(hours=2))).stored
    early = repo.store_sighting(db, observation.id, sighting(acquisition_key="early", observed_time=OBSERVED - timedelta(hours=2))).stored
    tie_a = repo.store_sighting(db, observation.id, sighting(acquisition_key="tie_a", observed_time=OBSERVED)).stored
    tie_b = repo.store_sighting(db, observation.id, sighting(acquisition_key="tie_b", observed_time=OBSERVED)).stored
    assert [s.id for s in repo.list_sightings(db, observation.id)] == [early.id, tie_a.id, tie_b.id, late.id]
    assert late.id < early.id  # recorded first, observed last: the listing follows observed_time


def test_lookups_of_missing_things(world):
    db, _, _, observation = world
    assert repo.get_sighting_by_id(db, 999) is None
    assert repo.find_sighting(db, observation.id, "nope") is None
    assert repo.list_sightings(db, 999) == []


def test_a_sighting_needs_an_existing_observation(world):
    db = world[0]
    with pytest.raises(NotFoundError) as info:
        repo.store_sighting(db, 999999, sighting())
    assert info.value.code == "observation_not_found" and count(db, "observation_sighting") == 0


@pytest.mark.parametrize("bad", [0, -1, "1", None, True, 1.0])
def test_ids_are_validated(world, bad):
    db = world[0]
    for call in (lambda: repo.store_sighting(db, bad, sighting()), lambda: repo.get_sighting_by_id(db, bad),
                 lambda: repo.list_sightings(db, bad), lambda: repo.find_sighting(db, bad, "k")):
        with pytest.raises(InvalidInputError):
            call()


def test_store_requires_a_sighting_and_find_validates_the_key(world):
    db, _, _, observation = world
    with pytest.raises(InvalidInputError):
        repo.store_sighting(db, observation.id, {"acquisition_key": "k"})
    with pytest.raises(InvalidInputError):
        repo.find_sighting(db, observation.id, "bad key")


def test_recorded_time_is_database_assigned(world):
    db, _, _, observation = world
    stored = repo.store_sighting(db, observation.id, sighting(observed_time=datetime(2001, 1, 1, tzinfo=timezone.utc))).stored
    assert stored.recorded_time.tzinfo is timezone.utc and stored.recorded_time > stored.sighting.observed_time
    assert abs(datetime.now(timezone.utc) - stored.recorded_time) < timedelta(minutes=5)
    assert "recorded_time" not in inspect.signature(repo.store_sighting).parameters and "recorded_time" not in Sighting.model_fields


def test_lineage_from_a_sighting_back_to_observation_payload_and_source(world):
    db, source, digest, observation = world
    stored = repo.store_sighting(db, observation.id, sighting()).stored
    lineage = obs_repo.get_observation_lineage(db, repo.get_sighting_by_id(db, stored.id).observation_id)
    assert lineage.observation == observation and lineage.source == source
    assert lineage.payload.content_hash == digest and lineage.payload.payload_bytes == b"evidence"


def test_the_repository_exposes_no_update_or_delete(world):
    public = {n for n, v in vars(repo).items() if callable(v) and not n.startswith("_") and getattr(v, "__module__", "") == repo.__name__}
    assert public == {"store_sighting", "get_sighting_by_id", "find_sighting", "list_sightings", "SightingStoreResult"}
    text_ = inspect.getsource(repo).lower()
    assert "delete(" not in text_ and "delete from" not in text_ and "update(" not in text_ and "do_update" not in text_


def test_a_connection_joins_the_callers_transaction(world):
    db, _, _, observation = world
    with db.connect() as conn:
        txn = conn.begin()
        repo.store_sighting(conn, observation.id, sighting(acquisition_key="txn"))
        assert repo.find_sighting(conn, observation.id, "txn") is not None
        txn.rollback()
    assert repo.find_sighting(db, observation.id, "txn") is None


# ---------------- direct SQL: constraints

def raw_insert(db, observation_id, **overrides):
    values = dict(observation_id=observation_id, observed_time=OBSERVED, collector_id="admin:user_2abc",
                  collection_version="manual_upload.v1", acquisition_key="run_x")
    values.update(overrides)
    cols = ", ".join(values)
    binds = ", ".join(f":{k}" for k in values)
    with db.begin() as conn:
        return conn.execute(text(f"INSERT INTO v2.observation_sighting ({cols}) VALUES ({binds}) RETURNING id"), values).scalar()


def raw_rejected(db, observation_id, **overrides):
    try:
        raw_insert(db, observation_id, **overrides)
    except IntegrityError as exc:
        return exc.orig.diag.constraint_name or exc.orig.diag.column_name
    raise AssertionError("insert was accepted")


def test_an_observation_must_exist(world):
    assert raw_rejected(world[0], 999999) == "fk_observation_sighting_observation_id_observation"


@pytest.mark.parametrize("column", ["observation_id", "observed_time", "collector_id", "collection_version", "acquisition_key"])
def test_not_null_columns(world, column):
    db, _, _, observation = world
    assert raw_rejected(db, None if column == "observation_id" else observation.id, **({} if column == "observation_id" else {column: None})) == column


@pytest.mark.parametrize("value", ["", " admin", "admin user", "-admin", "x" * 129, "admïn", "a\nb"])
def test_collector_id_shape(world, value):
    db, _, _, observation = world
    assert raw_rejected(db, observation.id, collector_id=value) == "ck_observation_sighting_collector_id_shape"


@pytest.mark.parametrize("value", ["manual_upload", "manual.v0", "Manual.v1", "manual.v1\n", ""])
def test_collection_version_shape(world, value):
    db, _, _, observation = world
    assert raw_rejected(db, observation.id, collection_version=value) == "ck_observation_sighting_collection_version_shape"


@pytest.mark.parametrize("value", ["", "-x", ".x", "has space", "tab\t", "new\nline", "x" * 129, "café", "a#b"])
def test_acquisition_key_shape(world, value):
    db, _, _, observation = world
    assert raw_rejected(db, observation.id, acquisition_key=value) == "ck_observation_sighting_acquisition_key_shape"


def test_the_acquisition_identity_is_unique_per_observation_and_only_that(world):
    db, _, digest, observation = world
    raw_insert(db, observation.id, acquisition_key="run_1")
    assert raw_rejected(db, observation.id, acquisition_key="run_1") == "uq_observation_sighting_acquisition"
    # not unique on observation_id alone, nor on (observation_id, observed_time): repeated checks are legitimate
    raw_insert(db, observation.id, acquisition_key="run_2")
    raw_insert(db, observation.id, acquisition_key="run_3", observed_time=OBSERVED)
    other = obs_repo.store_observation(db, make_observation(digest, source_record_identifier="rec-2")).stored
    raw_insert(db, other.id, acquisition_key="run_1")
    assert count(db, "observation_sighting") == 4


def test_caller_supplied_or_null_recorded_time_is_replaced_by_the_database_clock(world):
    db, _, _, observation = world
    for i, value in enumerate(("1999-01-01T00:00:00+00:00", None)):
        sid = raw_insert(db, observation.id, acquisition_key=f"k{i}", recorded_time=value)
        assert fetch_row(db, "observation_sighting", "id = :i", {"i": sid})["recorded_time"].year >= 2026


# ---------------- direct SQL: append-only

@pytest.fixture
def with_sighting(world):
    db, source, digest, observation = world
    stored = repo.store_sighting(db, observation.id, sighting()).stored
    return db, source, digest, observation, stored


def snapshot(db):
    with db.connect() as conn:
        return [tuple(r) for r in conn.execute(text("SELECT * FROM v2.observation_sighting ORDER BY id"))]


@pytest.mark.parametrize("sql", [
    "UPDATE v2.observation_sighting SET observed_time = now()",
    "UPDATE v2.observation_sighting SET acquisition_key = 'changed'",
    "UPDATE v2.observation_sighting SET recorded_time = '2001-01-01T00:00:00+00:00'",
    "UPDATE v2.observation_sighting SET collector_id = collector_id",   # even a no-op update
])
def test_direct_update_is_blocked_and_changes_nothing(with_sighting, sql):
    db = with_sighting[0]
    before = snapshot(db)
    _, message = refused(db, sql, exc=IntegrityError)
    assert "v2.observation_sighting is append-only: UPDATE is not permitted" in message
    assert snapshot(db) == before


def test_an_upsert_cannot_rewrite_a_sighting(with_sighting):
    db, _, _, observation, stored = with_sighting
    before = snapshot(db)
    _, message = refused(db, "INSERT INTO v2.observation_sighting (observation_id, observed_time, collector_id, collection_version, acquisition_key) "
                             "VALUES (:o, now(), 'admin:attacker', 'manual_upload.v1', 'run_1') "
                             "ON CONFLICT (observation_id, acquisition_key) DO UPDATE SET collector_id = EXCLUDED.collector_id",
                         {"o": observation.id}, exc=IntegrityError)
    assert "append-only" in message
    assert snapshot(db) == before


def test_direct_delete_is_blocked_and_the_row_survives(with_sighting):
    db = with_sighting[0]
    before = snapshot(db)
    _, message = refused(db, "DELETE FROM v2.observation_sighting", exc=IntegrityError)
    assert "v2.observation_sighting is append-only: DELETE is not permitted" in message
    refused(db, "DELETE FROM v2.observation_sighting WHERE id = :i", {"i": with_sighting[4].id}, exc=IntegrityError)
    assert snapshot(db) == before


@pytest.mark.parametrize("sql", ["TRUNCATE v2.observation_sighting", "TRUNCATE v2.observation_sighting RESTART IDENTITY",
                                 "TRUNCATE v2.observation_sighting, v2.observation CASCADE", "TRUNCATE v2.observation CASCADE"])
def test_direct_truncate_is_blocked_once_sightings_exist(with_sighting, sql):
    db = with_sighting[0]
    before = snapshot(db)
    _, message = refused(db, sql, exc=IntegrityError)
    assert "is append-only: TRUNCATE is not permitted" in message
    assert snapshot(db) == before


def test_evidence_that_sightings_reference_cannot_be_removed(with_sighting):
    db, source, digest, observation, _ = with_sighting
    refused(db, "DELETE FROM v2.observation WHERE id = :i", {"i": observation.id}, exc=IntegrityError)   # append-only trigger
    with pytest.raises(IntegrityError) as info:
        with db.begin() as conn:
            conn.execute(text("DELETE FROM v2.source WHERE id = :i"), {"i": source.id})
    assert info.value.orig.diag.constraint_name == "fk_observation_source_id_source"
    refused(db, "TRUNCATE v2.observation", exc=DBAPIError)                                               # FK: sightings reference it
    assert count(db, "observation") == 1 and count(db, "source") == 1
