"""
PRIVATE. The ONLY module that writes v2.financing_event, v2.financing_resolution_decision,
v2.financing_event_stage, v2.financing_event_type, v2.financing_event_verified_round_amount and
v2.financing_event_date. app.v2.financing_resolution.promotion is the only importer; an architecture test fails
if any other module writes those tables or imports this one.

Nothing here decides anything or selects facts: every function takes an already-validated Authority and inserts
exactly the row the calling operation has justified. The database re-verifies every one of them.
"""

from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.engine import Connection

from app.v2.db.tables import financing_event_date_table as fed
from app.v2.db.tables import financing_event_stage_table as fes
from app.v2.db.tables import financing_event_table as fe
from app.v2.db.tables import financing_event_type_table as fet
from app.v2.db.tables import financing_event_verified_round_amount_table as fev
from app.v2.db.tables import financing_resolution_decision_table as decision
from app.v2.domain.financing import FinancingDateKind, FinancingType, Money, Stage
from app.v2.domain.financing_resolution import Authority, FinancingDecisionKind
from app.v2.domain.time import EventTime


def insert_event(connection: Connection, *, company_id: UUID) -> UUID:
    return connection.execute(insert(fe).values(company_id=company_id).returning(fe.c.id)).scalar_one()


def insert_decision(connection: Connection, *, candidate_id: int, kind: FinancingDecisionKind, authority: Authority,
                    financing_event_id: UUID | None, reason_code: str | None) -> int:
    return connection.execute(insert(decision).values(
        candidate_id=candidate_id, decision_kind=kind.value, financing_event_id=financing_event_id,
        decided_by_kind=authority.kind.value, decided_by_id=authority.id, reason_code=reason_code,
    ).returning(decision.c.id)).scalar_one()


def insert_stage(connection: Connection, *, financing_event_id: UUID, stage: Stage, decision_id: int, candidate_id: int) -> None:
    connection.execute(insert(fes).values(financing_event_id=financing_event_id, stage=stage.value,
                                          resolution_decision_id=decision_id, candidate_id=candidate_id))


def insert_type(connection: Connection, *, financing_event_id: UUID, financing_type: FinancingType, decision_id: int, candidate_id: int) -> None:
    connection.execute(insert(fet).values(financing_event_id=financing_event_id, financing_type=financing_type.value,
                                          resolution_decision_id=decision_id, candidate_id=candidate_id))


def insert_verified_round_amount(connection: Connection, *, financing_event_id: UUID, money: Money, decision_id: int, candidate_amount_id: int) -> None:
    connection.execute(insert(fev).values(financing_event_id=financing_event_id, currency_code=money.currency_code,
                                          amount_minor_units=money.minor_units, resolution_decision_id=decision_id,
                                          candidate_amount_id=candidate_amount_id))


def insert_date(connection: Connection, *, financing_event_id: UUID, kind: FinancingDateKind, time: EventTime,
                decision_id: int, candidate_date_id: int) -> None:
    connection.execute(insert(fed).values(financing_event_id=financing_event_id, date_kind=kind.value,
                                          date_precision=time.precision.value, date_start=time.start,
                                          resolution_decision_id=decision_id, candidate_date_id=candidate_date_id))
