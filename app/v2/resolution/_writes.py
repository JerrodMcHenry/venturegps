"""
PRIVATE. The ONLY module that writes v2.company, v2.resolution_decision, v2.company_name and
v2.company_identifier. app.v2.resolution.promotion is the only importer; an architecture test
fails if any other module writes those tables or imports this one.

Nothing here decides anything: every function takes an already-validated Authority and a
StoredCompanyCandidate (or ids taken from one) and inserts exactly the rows the calling
operation has justified. The database re-verifies every one of those rows.
"""

from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.engine import Connection

from app.v2.db.tables import company_identifier_table as company_identifier
from app.v2.db.tables import company_name_table as company_name
from app.v2.db.tables import company_table as company
from app.v2.db.tables import resolution_decision_table as decision
from app.v2.domain.company import CompanyNameRole, normalize_identifier
from app.v2.domain.resolution import Authority, DecisionKind
from app.v2.domain.candidate import IdentifierType


def insert_company(connection: Connection) -> UUID:
    return connection.execute(insert(company).values().returning(company.c.id)).scalar_one()


def insert_decision(connection: Connection, *, candidate_id: int, kind: DecisionKind, authority: Authority,
                    company_id: UUID | None, reason_code: str | None) -> int:
    return connection.execute(
        insert(decision).values(
            candidate_id=candidate_id, decision_kind=kind.value, company_id=company_id,
            decided_by_kind=authority.kind.value, decided_by_id=authority.id, reason_code=reason_code,
        ).returning(decision.c.id)
    ).scalar_one()


def insert_name(connection: Connection, *, company_id: UUID, name: str, candidate_id: int,
                role: CompanyNameRole, decision_id: int) -> None:
    connection.execute(insert(company_name).values(
        company_id=company_id, name=name, name_role=role.value,
        resolution_decision_id=decision_id, candidate_id=candidate_id,
    ))


def insert_identifier(connection: Connection, *, company_id: UUID, candidate_identifier_id: int,
                      identifier_type: IdentifierType, value: str, decision_id: int) -> None:
    connection.execute(insert(company_identifier).values(
        company_id=company_id, identifier_type=identifier_type.value,
        identifier_value=normalize_identifier(identifier_type, value),
        resolution_decision_id=decision_id, candidate_identifier_id=candidate_identifier_id,
    ))
