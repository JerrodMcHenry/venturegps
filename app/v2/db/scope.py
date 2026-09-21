"""
What Alembic is allowed to see. V2 migrations own schema `v2` and nothing else.

Two layers, both fail-closed:

- include_name runs BEFORE reflection: every schema except `v2` (including
  the default schema, whose name is None -- that is where legacy tables live)
  is never even reflected, so legacy `public` tables cannot appear as
  "tables to drop" in an autogenerate diff.
- include_object runs on each object: only objects belonging to a `v2` table
  pass; anything it cannot attribute to `v2` is excluded.

The version table is `v2.alembic_version`, never `public.alembic_version`.
"""

from app.v2.db.metadata import V2_SCHEMA

VERSION_TABLE = "alembic_version"
VERSION_TABLE_SCHEMA = V2_SCHEMA


def include_name(name, type_, parent_names) -> bool:
    if type_ == "schema":
        return name == V2_SCHEMA
    return parent_names.get("schema_name") == V2_SCHEMA


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    if type_ == "table":
        return getattr(obj, "schema", None) == V2_SCHEMA
    table = getattr(obj, "table", None)
    if table is not None:
        return getattr(table, "schema", None) == V2_SCHEMA
    return False
