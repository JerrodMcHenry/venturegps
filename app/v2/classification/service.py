"""
classify_company(db, company_id, market_id, taxonomy_version, role, authority): the only way to create a
Company -> Market classification.

Re-checks the authority (AI cannot be constructed; a rule may classify only if CLASSIFICATION_RULE_AUTHORITY
registers it -- it is empty today, so effectively human-only), and verifies the Company, Market and taxonomy
version all already exist before writing, for a clean typed NotFoundError rather than relying purely on the
database's foreign keys. One transaction (a SAVEPOINT when the caller passes a Connection). A second PRIMARY
classification for the same (Company, taxonomy version), or a repeat of the exact same (Company, Market, taxonomy
version), is refused -- never a silent overwrite.
"""

from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.classification import _writes
from app.v2.classification.errors import AlreadyClassifiedError, PrimaryAlreadyAssignedError
from app.v2.db.tables import company_market_classification_table as cmc
from app.v2.db.tables import company_table, market_table, taxonomy_version_table
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.resolution import Authority
from app.v2.domain.taxonomy import ClassificationRole, StoredCompanyMarketClassification, may_classify
from app.v2.repositories._db import atomic, constraint_of, integrity_error_to_domain
from app.v2.repositories.errors import NotFoundError


@dataclass(frozen=True)
class ClassificationResult:
    classification: StoredCompanyMarketClassification


def _checked_authority(authority: object) -> Authority:
    if not isinstance(authority, Authority):
        raise InvalidInputError("invalid_authority", "authority must be an Authority (rule or human)")
    try:
        verified = Authority(kind=authority.kind, id=authority.id)
    except ValidationError:
        raise InvalidInputError("invalid_authority", "authority must be an Authority (rule or human)") from None
    if not may_classify(verified):
        raise InvariantViolationError("authority_exceeded", "the authority may not classify a company")
    return verified


def _translate(exc: IntegrityError) -> Exception:
    name = constraint_of(exc)
    if name == "uq_cmc_one_primary_per_company_version":
        return PrimaryAlreadyAssignedError("primary_already_assigned", "the company already has a primary classification under this taxonomy version")
    if name == "uq_cmc_company_market_version":
        return AlreadyClassifiedError("already_classified", "this company is already classified into this market under this taxonomy version")
    return integrity_error_to_domain(exc)


def classify_company(db: Engine | Connection, company_id: UUID, market_id: UUID, taxonomy_version: str,
                     role: ClassificationRole, authority: Authority) -> ClassificationResult:
    authority = _checked_authority(authority)
    if not isinstance(role, ClassificationRole):
        raise InvalidInputError("invalid_role", "role must be a ClassificationRole")
    try:
        with atomic(db) as connection:
            if connection.execute(select(company_table.c.id).where(company_table.c.id == company_id)).first() is None:
                raise NotFoundError("company_not_found", "no such company")
            if connection.execute(select(market_table.c.id).where(market_table.c.id == market_id)).first() is None:
                raise NotFoundError("market_not_found", "no such market")
            if connection.execute(select(taxonomy_version_table.c.taxonomy_version)
                                  .where(taxonomy_version_table.c.taxonomy_version == taxonomy_version)).first() is None:
                raise NotFoundError("taxonomy_version_not_found", "no such taxonomy version")
            classification_id = _writes.insert_classification(connection, company_id=company_id, market_id=market_id,
                                                               taxonomy_version=taxonomy_version, role=role, authority=authority)
            row = connection.execute(select(cmc).where(cmc.c.id == classification_id)).one()
    except IntegrityError as exc:
        raise _translate(exc) from None
    stored = StoredCompanyMarketClassification(
        id=row.id, company_id=row.company_id, market_id=row.market_id, taxonomy_version=row.taxonomy_version,
        role=ClassificationRole(row.role), authority=Authority(kind=authority.kind, id=row.decided_by_id), created_at=row.created_at,
    )
    return ClassificationResult(classification=stored)
