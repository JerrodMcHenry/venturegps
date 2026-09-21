"""
Observation persistence: immutable evidence that a Source exposed a payload.

    store_observation(db, observation)                 -> ObservationStoreResult(stored, created)
    get_observation_by_id(db, observation_id)          -> StoredObservation | None
    find_observation(db, source_key, source_record_identifier, content_hash) -> StoredObservation | None
    get_observation_lineage(db, observation_id)        -> ObservationLineage | None

The Source must already be registered and the payload already stored
(store_raw_payload); nothing here orchestrates ingestion (that is a later
increment). Observations are append-only: no update or delete exists in this
module and the database rejects both, for every writer.

DEDUP IDENTITY = (source, source_record_identifier, content_hash), where "no
record identifier" is itself a value: two observations from one source with
no identifier and identical bytes are the SAME observation, and an
observation with no identifier never equals one that has one. Storing an
existing identity returns the existing, unmodified Observation (created=False);
a later re-acquisition is recorded as a sighting by a later increment, never
by rewriting this one. Fields outside the identity (observed_time, collector,
...) of a duplicate are therefore not stored here.

recorded_time is assigned by the database. Media agreement is derived from
declared/sniffed (Observation.media_agreement), not stored. This module does
not check that sniffed_media_type is what the bytes actually are; the ingestion
step that computes it owns that.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.db.tables import observation_table as t
from app.v2.db.tables import source_table as s
from app.v2.domain.content import MediaType, validate_content_hash
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.observation import Observation, StoredObservation
from app.v2.domain.payload import RawPayload
from app.v2.domain.source import StoredSource, validate_source_key
from app.v2.domain.time import EventTime, EventTimePrecision
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import constraint_of, integrity_error_to_domain
from app.v2.repositories.errors import NotFoundError
from app.v2.repositories.raw_payloads import get_raw_payload
from app.v2.repositories.sources import get_source_by_id


@dataclass(frozen=True)
class ObservationStoreResult:
    stored: StoredObservation
    created: bool


@dataclass(frozen=True)
class ObservationLineage:
    """Observation -> RawPayload (hash verified) and Observation -> Source."""

    observation: StoredObservation
    source: StoredSource
    payload: RawPayload


_COLUMNS = (*t.c, s.c.source_key)


def _select_joined():
    return select(*_COLUMNS).select_from(t.join(s, s.c.id == t.c.source_id))


def _to_stored(row) -> StoredObservation:
    m = row._mapping
    try:
        event_time = None
        if m["event_time"] is not None:
            event_time = EventTime(precision=EventTimePrecision(m["event_time_precision"]), start=m["event_time"])
        return StoredObservation(
            id=m["id"],
            source_id=m["source_id"],
            observation=Observation(
                source_key=m["source_key"],
                source_record_identifier=m["source_record_identifier"],
                observation_type=m["observation_type"],
                event_time=event_time,
                observed_time=m["observed_time"],
                collection_version=m["collection_version"],
                collector_id=m["collector_id"],
                content_hash=m["content_hash"],
                declared_media_type=m["declared_media_type"],
                sniffed_media_type=MediaType(m["sniffed_media_type"]),
            ),
            recorded_time=m["recorded_time"],
        )
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_observation_invalid", "a stored observation does not satisfy the domain model") from None


def find_observation(
    db: Engine | Connection, source_key: str, source_record_identifier: str | None, content_hash: str
) -> StoredObservation | None:
    """Look an observation up by its dedup identity. source_record_identifier=None means 'none'."""
    validate_source_key(source_key)
    validate_content_hash(content_hash)
    query = _select_joined().where(s.c.source_key == source_key, t.c.content_hash == content_hash)
    query = query.where(t.c.source_record_identifier.is_(None) if source_record_identifier is None
                        else t.c.source_record_identifier == source_record_identifier)
    with _connection(db) as connection:
        row = connection.execute(query).one_or_none()
    return None if row is None else _to_stored(row)


def get_observation_by_id(db: Engine | Connection, observation_id: int) -> StoredObservation | None:
    if type(observation_id) is not int or observation_id < 1:
        raise InvalidInputError("invalid_observation_id", "observation id must be a positive integer")
    with _connection(db) as connection:
        row = connection.execute(_select_joined().where(t.c.id == observation_id)).one_or_none()
    return None if row is None else _to_stored(row)


def store_observation(db: Engine | Connection, observation: Observation) -> ObservationStoreResult:
    if not isinstance(observation, Observation):
        raise InvalidInputError("not_an_observation", "store_observation requires an Observation")

    with _connection(db) as connection:
        source_id = connection.execute(select(s.c.id).where(s.c.source_key == observation.source_key)).scalar()
        if source_id is None:
            raise NotFoundError("source_not_found", "no source is registered under the observation's source key")

        values = {
            "source_id": source_id,
            "source_record_identifier": observation.source_record_identifier,
            "observation_type": observation.observation_type,
            "event_time": None if observation.event_time is None else observation.event_time.start,
            "event_time_precision": None if observation.event_time is None else observation.event_time.precision.value,
            "observed_time": observation.observed_time,
            "collection_version": observation.collection_version,
            "collector_id": observation.collector_id,
            "content_hash": observation.content_hash,
            "declared_media_type": observation.declared_media_type,
            "sniffed_media_type": observation.sniffed_media_type.value,
            # recorded_time is deliberately absent: the database assigns it.
        }
        statement = pg_insert(t).values(**values)
        if observation.source_record_identifier is not None:
            statement = statement.on_conflict_do_nothing(
                index_elements=[t.c.source_id, t.c.source_record_identifier, t.c.content_hash],
                index_where=t.c.source_record_identifier.is_not(None),
            )
        else:
            statement = statement.on_conflict_do_nothing(
                index_elements=[t.c.source_id, t.c.content_hash],
                index_where=t.c.source_record_identifier.is_(None),
            )

        try:
            inserted_id = connection.execute(statement.returning(t.c.id)).scalar()
        except IntegrityError as exc:
            if constraint_of(exc) == "fk_observation_content_hash_raw_payload":
                raise NotFoundError("raw_payload_not_found", "no payload is stored under the observation's content hash") from None
            raise integrity_error_to_domain(exc) from None

        if inserted_id is not None:
            return ObservationStoreResult(_to_stored(connection.execute(_select_joined().where(t.c.id == inserted_id)).one()), created=True)

    existing = find_observation(db, observation.source_key, observation.source_record_identifier, observation.content_hash)
    if existing is None:  # unreachable: evidence is never deleted
        raise InvariantViolationError("observation_missing_after_conflict", "a conflicting observation could not be read back")
    return ObservationStoreResult(existing, created=False)


def get_observation_lineage(db: Engine | Connection, observation_id: int) -> ObservationLineage | None:
    """The observation, its Source and its payload. The payload's hash is verified: corrupted
    evidence raises InvariantViolationError instead of being returned."""
    stored = get_observation_by_id(db, observation_id)
    if stored is None:
        return None
    source = get_source_by_id(db, stored.source_id)
    payload = get_raw_payload(db, stored.observation.content_hash, verify=True)
    if source is None or payload is None:  # unreachable: foreign keys are RESTRICT
        raise InvariantViolationError("lineage_broken", "an observation's source or payload is missing")
    return ObservationLineage(observation=stored, source=source, payload=payload)
