"""
Schema-qualified SQLAlchemy metadata for every V2-owned table. It is empty in
Increment 2 (revision 0001 only establishes the namespace); later increments
add their tables here alongside their migrations.

Alembic autogenerate compares the database against THIS metadata, and only
within schema `v2` (see app/v2/db/scope.py).
"""

from sqlalchemy import MetaData

V2_SCHEMA = "v2"

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(schema=V2_SCHEMA, naming_convention=NAMING_CONVENTION)
