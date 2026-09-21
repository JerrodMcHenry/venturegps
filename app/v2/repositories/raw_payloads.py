"""
Raw payload persistence: store the exact bytes a source exposed, content-addressed.

    store_raw_payload(db, data)                    -> PayloadStoreResult(payload, created)
    get_raw_payload(db, content_hash, verify=True) -> RawPayload | None

The repository COMPUTES the hash from the bytes it is given; a caller never
supplies one, so a payload can never be stored under the wrong key. Storing
identical bytes again returns the existing payload (created=False). Oversized
content raises UnsupportedInputError; nothing is truncated.

Payloads are append-only evidence: there is no update or delete operation
here, and the database rejects them for every writer.

Reads verify sha256(stored bytes) == content_hash and the recorded size, and
raise InvariantViolationError on a mismatch. Corrupted evidence fails loudly
and is never repaired. verify=False exists only so audit tooling can inspect
suspect bytes.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from app.v2.db.tables import raw_payload_table as t
from app.v2.domain.content import validate_content_hash
from app.v2.domain.errors import DomainError, InvariantViolationError
from app.v2.domain.payload import RawPayload, StorageKind
from app.v2.observations.hashing import build_raw_payload, verify_raw_payload
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import translating_integrity_errors as _translating_integrity_errors


@dataclass(frozen=True)
class PayloadStoreResult:
    payload: RawPayload
    created: bool


def _to_payload(row, *, verify: bool) -> RawPayload:
    m = row._mapping
    try:
        payload = RawPayload(
            content_hash=m["content_hash"],
            payload_bytes=bytes(m["payload_bytes"]),
            storage_kind=StorageKind(m["storage_kind"]),
        )
    except (DomainError, ValueError, TypeError):
        raise InvariantViolationError("stored_payload_invalid", "a stored payload does not satisfy the domain model") from None
    if verify:
        if payload.size_bytes != m["size_bytes"]:
            raise InvariantViolationError("payload_size_mismatch", "stored payload size does not match its recorded size")
        verify_raw_payload(payload)
    return payload


def store_raw_payload(db: Engine | Connection, data: bytes | bytearray | memoryview) -> PayloadStoreResult:
    payload = build_raw_payload(data)
    values = {
        "content_hash": payload.content_hash,
        "storage_kind": payload.storage_kind.value,
        "size_bytes": payload.size_bytes,
        "payload_bytes": payload.payload_bytes,
    }
    with _connection(db) as connection, _translating_integrity_errors():
        inserted = connection.execute(
            pg_insert(t).values(**values).on_conflict_do_nothing(index_elements=[t.c.content_hash]).returning(t.c.content_hash)
        ).one_or_none()
    return PayloadStoreResult(payload=payload, created=inserted is not None)


def get_raw_payload(db: Engine | Connection, content_hash: str, *, verify: bool = True) -> RawPayload | None:
    validate_content_hash(content_hash)
    with _connection(db) as connection:
        row = connection.execute(select(t).where(t.c.content_hash == content_hash)).one_or_none()
    return None if row is None else _to_payload(row, verify=verify)
