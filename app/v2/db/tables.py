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
    Identity,
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
