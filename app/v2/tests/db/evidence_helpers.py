"""Helpers for the evidence (raw_payload / observation) database tests."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.v2.domain.content import MediaType
from app.v2.domain.observation import Observation
from app.v2.domain.source import CollectionMethod, Source, SourceType
from app.v2.repositories import raw_payloads, sources

OBSERVED = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def register_source(engine, key="sec_edgar"):
    source = Source(source_key=key, name=f"Source {key}", source_type=SourceType.GOVERNMENT_REGULATORY,
                    collection_method=CollectionMethod.API, url=None, is_active=True)
    return sources.register_source(engine, source).stored


def store_payload(engine, data: bytes) -> str:
    return raw_payloads.store_raw_payload(engine, data).payload.content_hash


def make_observation(content_hash: str, **overrides) -> Observation:
    base = dict(source_key="sec_edgar", observation_type="filing_document", observed_time=OBSERVED,
                collection_version="manual_upload.v1", collector_id="admin:user_2abc", content_hash=content_hash,
                sniffed_media_type=MediaType.TEXT_PLAIN)
    base.update(overrides)
    return Observation(**base)


def insert_payload_sql(engine, data: bytes) -> str:
    import hashlib
    digest = hashlib.sha256(data).hexdigest()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO v2.raw_payload (content_hash, storage_kind, size_bytes, payload_bytes) "
                          "VALUES (:h, 'inline', :n, :b)"), {"h": digest, "n": len(data), "b": data})
    return digest


def insert_observation_sql(engine, source_id: int, content_hash: str, **overrides) -> int:
    values = dict(source_id=source_id, observation_type="filing_document", observed_time=OBSERVED,
                  collection_version="manual_upload.v1", collector_id="admin:user_2abc", content_hash=content_hash,
                  sniffed_media_type="text/plain")
    values.update(overrides)
    cols = ", ".join(values)
    binds = ", ".join(f":{k}" for k in values)
    with engine.begin() as conn:
        return conn.execute(text(f"INSERT INTO v2.observation ({cols}) VALUES ({binds}) RETURNING id"), values).scalar()


def fetch_row(engine, table: str, where: str, params: dict):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT * FROM v2.{table} WHERE {where}"), params).mappings().one_or_none()


def count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM v2.{table}")).scalar()


def refused(engine, sql, params=None, *, exc):
    """Run `sql` in its own transaction; assert the database refused it; return (diag, message)."""
    with pytest.raises(exc) as info:
        with engine.begin() as conn:
            conn.execute(text(sql), params or {})
    return getattr(info.value.orig, "diag", None), str(info.value.orig)


def tamper_payload(engine, content_hash: str, *, new_bytes=None, new_size=None):
    """Simulate corruption/tampering by an operator who defeats the protections (disposable DB only)."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE v2.raw_payload DISABLE TRIGGER trg_raw_payload_append_only"))
        if new_bytes is not None:
            conn.execute(text("ALTER TABLE v2.raw_payload DROP CONSTRAINT ck_raw_payload_hash_matches_bytes"))
            conn.execute(text("UPDATE v2.raw_payload SET payload_bytes = :b WHERE content_hash = :h"), {"b": new_bytes, "h": content_hash})
        if new_size is not None:
            conn.execute(text("ALTER TABLE v2.raw_payload DROP CONSTRAINT ck_raw_payload_size_matches_bytes"))
            conn.execute(text("UPDATE v2.raw_payload SET size_bytes = :n WHERE content_hash = :h"), {"n": new_size, "h": content_hash})
