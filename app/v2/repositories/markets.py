"""
Market and TaxonomyVersion persistence: reference/taxonomy data, registered directly (like v2.source) rather than
behind a candidate/resolution boundary -- a Market is a taxonomy node VentureGPS defines, not evidence-derived
truth about the world, so there is nothing here for an untrusted candidate to propose or a resolution decision to
promote.

    register_taxonomy_version(db, taxonomy_version)   -> StoredTaxonomyVersion
    register_market(db, slug, display_name)           -> StoredMarket
    get_taxonomy_version(db, taxonomy_version)         -> StoredTaxonomyVersion | None
    get_market(db, market_id)                          -> StoredMarket | None
    get_market_by_slug(db, slug)                       -> StoredMarket | None
    list_taxonomy_versions(db)                          -> list[StoredTaxonomyVersion]
    list_markets(db, limit=None, offset=0)              -> list[StoredMarket]
    count_markets(db)                                   -> int
    count_primary_classified_companies(db, market_id, taxonomy_version) -> int

Both tables are append-only at the database level (no update/delete/truncate): a Market's slug and display_name do
not change once registered, and there is deliberately no rename operation in Increment 12 -- if a taxonomy node is
ever genuinely renamed, that is a later, separately reviewed decision (see docs). Registering an existing
taxonomy_version or slug is a ConflictError, never a silent overwrite.
"""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.db.tables import company_market_classification_table as cmc
from app.v2.db.tables import market_table as market
from app.v2.db.tables import taxonomy_version_table as tv
from app.v2.domain.errors import InvalidInputError
from app.v2.domain.taxonomy import StoredMarket, StoredTaxonomyVersion, validate_market_display_name, validate_market_slug
from app.v2.domain.versions import validate_version_id
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import integrity_error_to_domain
from app.v2.repositories.errors import ConflictError


def register_taxonomy_version(db: Engine | Connection, taxonomy_version: str) -> StoredTaxonomyVersion:
    validate_version_id(taxonomy_version)
    with _connection(db) as connection:
        try:
            row = connection.execute(pg_insert(tv).values(taxonomy_version=taxonomy_version)
                                   .on_conflict_do_nothing(index_elements=[tv.c.taxonomy_version]).returning(tv)).first()
        except IntegrityError as exc:
            raise integrity_error_to_domain(exc) from None
        if row is None:
            raise ConflictError("taxonomy_version_already_registered", "this taxonomy version is already registered")
    return StoredTaxonomyVersion(taxonomy_version=row.taxonomy_version, created_at=row.created_at)


def register_market(db: Engine | Connection, slug: str, display_name: str) -> StoredMarket:
    validate_market_slug(slug)
    validate_market_display_name(display_name)
    with _connection(db) as connection:
        try:
            row = connection.execute(pg_insert(market).values(slug=slug, display_name=display_name)
                                   .on_conflict_do_nothing(index_elements=[market.c.slug]).returning(market)).first()
        except IntegrityError as exc:
            raise integrity_error_to_domain(exc) from None
        if row is None:
            raise ConflictError("market_slug_already_registered", "this market slug is already registered")
    return StoredMarket(id=row.id, slug=row.slug, display_name=row.display_name, created_at=row.created_at)


def get_taxonomy_version(db: Engine | Connection, taxonomy_version: str) -> StoredTaxonomyVersion | None:
    with _connection(db) as connection:
        row = connection.execute(select(tv).where(tv.c.taxonomy_version == taxonomy_version)).first()
    return None if row is None else StoredTaxonomyVersion(taxonomy_version=row.taxonomy_version, created_at=row.created_at)


def get_market(db: Engine | Connection, market_id) -> StoredMarket | None:
    with _connection(db) as connection:
        row = connection.execute(select(market).where(market.c.id == market_id)).first()
    return None if row is None else StoredMarket(id=row.id, slug=row.slug, display_name=row.display_name, created_at=row.created_at)


def get_market_by_slug(db: Engine | Connection, slug: str) -> StoredMarket | None:
    with _connection(db) as connection:
        row = connection.execute(select(market).where(market.c.slug == slug)).first()
    return None if row is None else StoredMarket(id=row.id, slug=row.slug, display_name=row.display_name, created_at=row.created_at)


def list_taxonomy_versions(db: Engine | Connection) -> list[StoredTaxonomyVersion]:
    with _connection(db) as connection:
        rows = connection.execute(select(tv).order_by(tv.c.created_at)).all()
    return [StoredTaxonomyVersion(taxonomy_version=r.taxonomy_version, created_at=r.created_at) for r in rows]


def list_markets(db: Engine | Connection, limit: int | None = None, offset: int = 0) -> list[StoredMarket]:
    """Ordered by (created_at, id) for a STABLE, deterministic page order (id breaks ties within the same instant).
    `limit`/`offset` push real LIMIT/OFFSET to Postgres; omitting `limit` returns everything, unchanged from
    Increment 12's behavior."""
    if offset < 0:
        raise InvalidInputError("invalid_offset", "offset must be non-negative")
    if limit is not None and limit < 0:
        raise InvalidInputError("invalid_limit", "limit must be non-negative")
    query = select(market).order_by(market.c.created_at, market.c.id).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    with _connection(db) as connection:
        rows = connection.execute(query).all()
    return [StoredMarket(id=r.id, slug=r.slug, display_name=r.display_name, created_at=r.created_at) for r in rows]


def count_markets(db: Engine | Connection) -> int:
    with _connection(db) as connection:
        return connection.execute(select(func.count()).select_from(market)).scalar_one()


def count_primary_classified_companies(db: Engine | Connection, market_id, taxonomy_version: str) -> int:
    """How many DISTINCT canonical Companies currently hold a PRIMARY classification into `market_id` under
    `taxonomy_version` -- a genuine, deterministic count, never a fabricated coverage estimate. Used to tell
    apart 'no companies are even classified into this market' from 'companies are classified but have no
    qualifying financings in the requested period' (see docs/v2/CAPITAL_METHODOLOGY.md, coverage section)."""
    with _connection(db) as connection:
        return connection.execute(
            select(func.count(func.distinct(cmc.c.company_id)))
            .where(cmc.c.market_id == market_id, cmc.c.taxonomy_version == taxonomy_version, cmc.c.role == "primary")
        ).scalar_one()
