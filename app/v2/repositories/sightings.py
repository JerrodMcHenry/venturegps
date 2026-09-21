"""
ObservationSighting persistence: append-only acquisition history.

    store_sighting(db, observation_id, sighting)      -> SightingStoreResult(stored, created)
    get_sighting_by_id(db, sighting_id)               -> StoredSighting | None
    find_sighting(db, observation_id, acquisition_key)-> StoredSighting | None
    list_sightings(db, observation_id)                -> list[StoredSighting]

Storing is idempotent on (observation_id, acquisition_key): replaying the same
acquisition returns the EXISTING sighting unchanged (created=False); a new key
for the same Observation creates another sighting. The database's unique
constraint is the final authority, so concurrent replays create exactly one.

list_sightings is ordered by (observed_time, id): deterministic even when
sightings were recorded out of order. There is no update or delete here, and
the database rejects both, and TRUNCATE, for every writer. recorded_time is
assigned by the database.

Lineage back to Observation / RawPayload / Source is get_observation_lineage(
sighting.observation_id) in app.v2.repositories.observations.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.db.tables import observation_sighting_table as t
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.sighting import Sighting, StoredSighting, validate_acquisition_key
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import constraint_of, integrity_error_to_domain
from app.v2.repositories.errors import NotFoundError


@dataclass(frozen=True)
class SightingStoreResult:
    stored: StoredSighting
    created: bool


def _positive_id(value: object, what: str) -> None:
    if type(value) is not int or value < 1:
        raise InvalidInputError(f"invalid_{what}", f"{what.replace('_', ' ')} must be a positive integer")


def _to_stored(row) -> StoredSighting:
    m = row._mapping
    try:
        return StoredSighting(
            id=m["id"],
            observation_id=m["observation_id"],
            sighting=Sighting(
                observed_time=m["observed_time"],
                collector_id=m["collector_id"],
                collection_version=m["collection_version"],
                acquisition_key=m["acquisition_key"],
            ),
            recorded_time=m["recorded_time"],
        )
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_sighting_invalid", "a stored sighting does not satisfy the domain model") from None


def store_sighting(db: Engine | Connection, observation_id: int, sighting: Sighting) -> SightingStoreResult:
    _positive_id(observation_id, "observation_id")
    if not isinstance(sighting, Sighting):
        raise InvalidInputError("not_a_sighting", "store_sighting requires a Sighting")
    values = {
        "observation_id": observation_id,
        "observed_time": sighting.observed_time,
        "collector_id": sighting.collector_id,
        "collection_version": sighting.collection_version,
        "acquisition_key": sighting.acquisition_key,
        # recorded_time is deliberately absent: the database assigns it.
    }
    with _connection(db) as connection:
        try:
            inserted = connection.execute(
                pg_insert(t).values(**values)
                .on_conflict_do_nothing(index_elements=[t.c.observation_id, t.c.acquisition_key])
                .returning(*t.c)
            ).one_or_none()
        except IntegrityError as exc:
            if constraint_of(exc) == "fk_observation_sighting_observation_id_observation":
                raise NotFoundError("observation_not_found", "no observation exists with that id") from None
            raise integrity_error_to_domain(exc) from None
        if inserted is not None:
            return SightingStoreResult(_to_stored(inserted), created=True)
        existing = connection.execute(
            select(t).where(t.c.observation_id == observation_id, t.c.acquisition_key == sighting.acquisition_key)
        ).one()
        return SightingStoreResult(_to_stored(existing), created=False)


def get_sighting_by_id(db: Engine | Connection, sighting_id: int) -> StoredSighting | None:
    _positive_id(sighting_id, "sighting_id")
    with _connection(db) as connection:
        row = connection.execute(select(t).where(t.c.id == sighting_id)).one_or_none()
    return None if row is None else _to_stored(row)


def find_sighting(db: Engine | Connection, observation_id: int, acquisition_key: str) -> StoredSighting | None:
    _positive_id(observation_id, "observation_id")
    validate_acquisition_key(acquisition_key)
    with _connection(db) as connection:
        row = connection.execute(
            select(t).where(t.c.observation_id == observation_id, t.c.acquisition_key == acquisition_key)
        ).one_or_none()
    return None if row is None else _to_stored(row)


def list_sightings(db: Engine | Connection, observation_id: int) -> list[StoredSighting]:
    _positive_id(observation_id, "observation_id")
    with _connection(db) as connection:
        rows = connection.execute(select(t).where(t.c.observation_id == observation_id).order_by(t.c.observed_time, t.c.id)).all()
    return [_to_stored(row) for row in rows]
