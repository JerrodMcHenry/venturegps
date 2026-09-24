"""
PRIVATE. The ONLY module that writes v2.lifecycle_resolution_decision, v2.company_name_history,
v2.company_operating_status, v2.company_acquisition and v2.company_successor_relationship.
app.v2.lifecycle.promotion is the only importer; an architecture test fails if any other module writes those
tables or imports this one.

Nothing here decides anything or selects facts: every function takes an already-validated Authority and
inserts exactly the row the calling operation has justified. The database re-verifies every one of them
(each canonical fact table's guard trigger re-checks that the decision is a human accept_lifecycle_event for
this exact candidate, that the candidate's company_id matches, and that the value being written exactly
matches the candidate's own proposed value).
"""

from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.engine import Connection

from app.v2.db.tables import company_acquisition_table as ca
from app.v2.db.tables import company_name_history_table as cnh
from app.v2.db.tables import company_operating_status_table as cos
from app.v2.db.tables import company_successor_relationship_table as csr
from app.v2.db.tables import lifecycle_resolution_decision_table as decision
from app.v2.domain.lifecycle import OperatingStatus, SuccessorRelationshipKind
from app.v2.domain.lifecycle_resolution import Authority, LifecycleDecisionKind
from app.v2.domain.time import EventTime


def insert_decision(connection: Connection, *, candidate_id: int, kind: LifecycleDecisionKind, authority: Authority, reason_code: str | None) -> int:
    return connection.execute(insert(decision).values(
        candidate_id=candidate_id, decision_kind=kind.value,
        decided_by_kind=authority.kind.value, decided_by_id=authority.id, reason_code=reason_code,
    ).returning(decision.c.id)).scalar_one()


def insert_name_change(connection: Connection, *, company_id: UUID, new_name: str, effective: EventTime | None, decision_id: int, candidate_id: int) -> None:
    connection.execute(insert(cnh).values(
        company_id=company_id, new_name=new_name,
        effective_precision=effective.precision.value if effective else None, effective_start=effective.start if effective else None,
        resolution_decision_id=decision_id, candidate_id=candidate_id,
    ))


def insert_operating_status(connection: Connection, *, company_id: UUID, status: OperatingStatus, as_of: EventTime | None, decision_id: int, candidate_id: int) -> None:
    connection.execute(insert(cos).values(
        company_id=company_id, status=status.value,
        as_of_precision=as_of.precision.value if as_of else None, as_of_start=as_of.start if as_of else None,
        resolution_decision_id=decision_id, candidate_id=candidate_id,
    ))


def insert_acquisition(connection: Connection, *, company_id: UUID, acquirer_name: str, acquirer_company_id: UUID | None,
                       transaction_date: EventTime | None, decision_id: int, candidate_id: int) -> None:
    connection.execute(insert(ca).values(
        company_id=company_id, acquirer_name=acquirer_name, acquirer_company_id=acquirer_company_id,
        transaction_date_precision=transaction_date.precision.value if transaction_date else None,
        transaction_date_start=transaction_date.start if transaction_date else None,
        resolution_decision_id=decision_id, candidate_id=candidate_id,
    ))


def insert_successor(connection: Connection, *, company_id: UUID, related_entity_name: str, related_company_id: UUID | None,
                     relationship_kind: SuccessorRelationshipKind, decision_id: int, candidate_id: int) -> None:
    connection.execute(insert(csr).values(
        company_id=company_id, related_entity_name=related_entity_name, related_company_id=related_company_id,
        relationship_kind=relationship_kind.value, resolution_decision_id=decision_id, candidate_id=candidate_id,
    ))
