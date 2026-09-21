"""
Table definitions for V2-owned tables, registered on app.v2.db.metadata.metadata.

These describe the SHAPE for queries and for Alembic's drift check. The
migrations are the source of truth for constraints and triggers: CHECK
constraints and the v2.source guard trigger live in the migration SQL only,
so there is one definition of each, not two that can drift.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    LargeBinary,
    Table,
    Text,
    UniqueConstraint,
    text,
)

from app.v2.db.metadata import metadata

# Revision 0002.
source_table = Table(
    "source",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("source_key", Text, nullable=False),
    Column("source_name", Text, nullable=False),
    Column("source_type", Text, nullable=False),
    Column("collection_method", Text, nullable=False),
    Column("source_url", Text, nullable=True),
    Column("is_active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint("source_key"),
)

# Revision 0003: immutable evidence (append-only; enforced by triggers in the migration).
raw_payload_table = Table(
    "raw_payload",
    metadata,
    Column("content_hash", Text, primary_key=True),
    Column("storage_kind", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("payload_bytes", LargeBinary, nullable=True),
)

observation_table = Table(
    "observation",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("source_id", BigInteger, ForeignKey("v2.source.id", ondelete="RESTRICT"), nullable=False),
    Column("source_record_identifier", Text, nullable=True),
    Column("observation_type", Text, nullable=False),
    Column("event_time", DateTime(timezone=True), nullable=True),
    Column("event_time_precision", Text, nullable=True),
    Column("observed_time", DateTime(timezone=True), nullable=False),
    Column("recorded_time", DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")),
    Column("collection_version", Text, nullable=False),
    Column("collector_id", Text, nullable=False),
    Column("content_hash", Text, ForeignKey("v2.raw_payload.content_hash", ondelete="RESTRICT"), nullable=False),
    Column("declared_media_type", Text, nullable=True),
    Column("sniffed_media_type", Text, nullable=False),
    # Dedup identity: same source + same record identity (including "none") + same exact bytes.
    Index("uq_observation_dedup_with_record_id", "source_id", "source_record_identifier", "content_hash",
          unique=True, postgresql_where=text("source_record_identifier IS NOT NULL")),
    Index("uq_observation_dedup_without_record_id", "source_id", "content_hash",
          unique=True, postgresql_where=text("source_record_identifier IS NULL")),
)
