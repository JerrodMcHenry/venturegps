"""
Source persistence: the capability to register, look up, and change the
explicitly mutable state of a Source, backed by v2.source.

Public API (every function takes `db`: an Engine, which runs the operation in
its own transaction, or a Connection, which joins the caller's transaction):

    register_source(db, source)                  -> RegistrationResult
    get_source_by_id(db, source_id)              -> StoredSource | None
    get_source_by_key(db, source_key)            -> StoredSource | None
    list_sources(db, active_only=False)          -> list[StoredSource]
    update_source_metadata(db, source_key, name=, url=)   -> StoredSource
    deactivate_source(db, source_key) / reactivate_source(db, source_key) -> StoredSource

There is deliberately NO delete operation. Deactivation keeps the row and
changes nothing else about the Source.

Identity is source_key. Immutable after creation: source_key, source_type,
collection_method (the database trigger enforces it; this module simply
offers no way to change them). Mutable: name, url, is_active.

Registration is create-only with idempotent replay:
  - new source_key                                  -> created (created=True)
  - existing key, same source_type + collection_method
                                                    -> the EXISTING Source is returned unchanged
                                                       (created=False). Registration never rewrites
                                                       name/url/is_active; use update_source_metadata.
  - existing key, different source_type or collection_method
                                                    -> ConflictError("source_identity_conflict")

Domain objects cross this boundary, never SQLAlchemy rows. Unexpected
database constraint failures surface as InvariantViolationError (constraint
names are our own; no data values are included).
"""

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from app.v2.db.tables import source_table as t
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.source import (
    CollectionMethod,
    Source,
    SourceType,
    StoredSource,
    validate_source_key,
    validate_source_name,
    validate_source_url,
)
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import translating_integrity_errors as _translating_integrity_errors
from app.v2.repositories.errors import ConflictError, NotFoundError


class _Unchanged:
    def __repr__(self) -> str:
        return "UNCHANGED"


UNCHANGED = _Unchanged()  # "leave this field alone" (None means "clear the URL")


@dataclass(frozen=True)
class RegistrationResult:
    stored: StoredSource
    created: bool


# ---------------------------------------------------------------- plumbing

def _to_stored(row) -> StoredSource:
    m = row._mapping
    try:
        return StoredSource(
            id=m["id"],
            source=Source(
                source_key=m["source_key"],
                name=m["source_name"],
                source_type=SourceType(m["source_type"]),
                collection_method=CollectionMethod(m["collection_method"]),
                url=m["source_url"],
                is_active=m["is_active"],
            ),
            recorded_time=m["created_at"],
            updated_time=m["updated_at"],
        )
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_source_invalid", "a stored source does not satisfy the domain model") from None


def _select_by(connection: Connection, column, value):
    return connection.execute(select(t).where(column == value)).one_or_none()


# ---------------------------------------------------------------- operations

def register_source(db: Engine | Connection, source: Source) -> RegistrationResult:
    if not isinstance(source, Source):
        raise InvalidInputError("not_a_source", "register_source requires a Source")
    values = {
        "source_key": source.source_key,
        "source_name": source.name,
        "source_type": source.source_type.value,
        "collection_method": source.collection_method.value,
        "source_url": source.url,
        "is_active": source.is_active,
    }
    with _connection(db) as connection, _translating_integrity_errors():
        inserted = connection.execute(
            pg_insert(t).values(**values).on_conflict_do_nothing(index_elements=[t.c.source_key]).returning(*t.c)
        ).one_or_none()
        if inserted is not None:
            return RegistrationResult(_to_stored(inserted), created=True)

        existing = _to_stored(_select_by(connection, t.c.source_key, source.source_key))
        if (existing.source.source_type, existing.source.collection_method) != (source.source_type, source.collection_method):
            raise ConflictError(
                "source_identity_conflict",
                "source key is already registered with a different source type or collection method",
            )
        return RegistrationResult(existing, created=False)


def get_source_by_id(db: Engine | Connection, source_id: int) -> StoredSource | None:
    if type(source_id) is not int or source_id < 1:
        raise InvalidInputError("invalid_source_id", "source id must be a positive integer")
    with _connection(db) as connection:
        row = _select_by(connection, t.c.id, source_id)
    return None if row is None else _to_stored(row)


def get_source_by_key(db: Engine | Connection, source_key: str) -> StoredSource | None:
    validate_source_key(source_key)
    with _connection(db) as connection:
        row = _select_by(connection, t.c.source_key, source_key)
    return None if row is None else _to_stored(row)


def list_sources(db: Engine | Connection, *, active_only: bool = False) -> list[StoredSource]:
    query = select(t).order_by(t.c.source_key)
    if active_only:
        query = query.where(t.c.is_active.is_(True))
    with _connection(db) as connection:
        return [_to_stored(row) for row in connection.execute(query)]


def _require(db: Engine | Connection, source_key: str) -> StoredSource:
    stored = get_source_by_key(db, source_key)
    if stored is None:
        raise NotFoundError("source_not_found", "no source is registered under that key")
    return stored


def _update(db: Engine | Connection, source_key: str, values: dict) -> StoredSource:
    with _connection(db) as connection, _translating_integrity_errors():
        row = connection.execute(
            update(t).where(t.c.source_key == source_key).values(**values).returning(*t.c)
        ).one_or_none()
    if row is None:
        raise NotFoundError("source_not_found", "no source is registered under that key")
    return _to_stored(row)


def update_source_metadata(
    db: Engine | Connection,
    source_key: str,
    *,
    name: str | _Unchanged = UNCHANGED,
    url: str | None | _Unchanged = UNCHANGED,
) -> StoredSource:
    """Change only the mutable descriptive fields. Fields left UNCHANGED are not
    touched (so concurrent updates of different fields cannot lose each other);
    url=None clears the URL. With nothing to change, the current Source is
    returned and updated_time does not move."""
    validate_source_key(source_key)
    values: dict = {}
    if name is not UNCHANGED:
        values["source_name"] = validate_source_name(name)
    if url is not UNCHANGED:
        values["source_url"] = None if url is None else validate_source_url(url)
    if not values:
        return _require(db, source_key)
    return _update(db, source_key, values)


def _set_active(db: Engine | Connection, source_key: str, is_active: bool) -> StoredSource:
    validate_source_key(source_key)
    return _update(db, source_key, {"is_active": is_active})


def deactivate_source(db: Engine | Connection, source_key: str) -> StoredSource:
    """Stop considering the source enabled. Keeps the row; alters nothing else. Idempotent."""
    return _set_active(db, source_key, False)


def reactivate_source(db: Engine | Connection, source_key: str) -> StoredSource:
    return _set_active(db, source_key, True)
