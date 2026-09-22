"""
READ-ONLY access to canonical FinancingEvent identity, its accepted facts, and financing resolution history.

Nothing in this module writes. Canonical writes live in exactly one place, app.v2.financing_resolution._writes,
reached only through app.v2.financing_resolution.promotion; an architecture test fails if any other module
writes the canonical financing tables. Reads may be broad.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine

from app.v2.db.tables import financing_event_candidate_amount_table as fca
from app.v2.db.tables import financing_event_candidate_date_table as fcd
from app.v2.db.tables import financing_event_candidate_table as fcc
from app.v2.db.tables import financing_event_date_table as fed
from app.v2.db.tables import financing_event_stage_table as fes
from app.v2.db.tables import financing_event_table as fe
from app.v2.db.tables import financing_event_type_table as fet
from app.v2.db.tables import financing_event_verified_round_amount_table as fev
from app.v2.db.tables import financing_resolution_decision_table as decision
from app.v2.db.tables import observation_table as obs
from app.v2.db.tables import processing_attempt_table as pa
from app.v2.db.tables import source_table as src
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.errors import DomainError, InvariantViolationError
from app.v2.domain.financing import AmountSemantics, FinancingDateKind, FinancingType, Money, Stage
from app.v2.domain.financing_resolution import (
    Authority,
    AuthorityKind,
    CanonicalFinancingEvent,
    FinancingCandidateResolutionState,
    FinancingDecisionKind,
    FinancingLineageLink,
    StoredFinancingEvent,
    StoredFinancingResolutionDecision,
    derive_financing_candidate_state,
)
from app.v2.repositories._db import connection as _connection


def _decision(row) -> StoredFinancingResolutionDecision:
    try:
        return StoredFinancingResolutionDecision(
            id=row.id, candidate_id=row.candidate_id, decision_kind=FinancingDecisionKind(row.decision_kind),
            financing_event_id=row.financing_event_id,
            authority=Authority(kind=AuthorityKind(row.decided_by_kind), id=row.decided_by_id),
            reason_code=row.reason_code, created_at=row.created_at,
        )
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_financing_decision_invalid", "a stored financing decision does not satisfy the domain model") from None


def get_financing_event(db: Engine | Connection, event_id: UUID) -> StoredFinancingEvent | None:
    with _connection(db) as connection:
        row = connection.execute(select(fe).where(fe.c.id == event_id)).first()
    return None if row is None else StoredFinancingEvent(id=row.id, company_id=row.company_id, created_at=row.created_at)


def list_financing_events_for_company(db: Engine | Connection, company_id: UUID) -> list[StoredFinancingEvent]:
    with _connection(db) as connection:
        rows = connection.execute(select(fe).where(fe.c.company_id == company_id).order_by(fe.c.created_at)).all()
    return [StoredFinancingEvent(id=r.id, company_id=r.company_id, created_at=r.created_at) for r in rows]


def get_canonical_financing_event(db: Engine | Connection, event_id: UUID) -> CanonicalFinancingEvent | None:
    """The event with only the facts explicitly accepted. Any of them may be absent: unknown is legitimate."""
    event = get_financing_event(db, event_id)
    if event is None:
        return None
    from app.v2.domain.financing_resolution import AcceptedDate, AcceptedFinancingType, AcceptedStage, AcceptedVerifiedRoundAmount
    from app.v2.domain.time import EventTime, EventTimePrecision
    with _connection(db) as connection:
        stage_row = connection.execute(select(fes).where(fes.c.financing_event_id == event_id)).first()
        type_row = connection.execute(select(fet).where(fet.c.financing_event_id == event_id)).first()
        amount_row = connection.execute(select(fev).where(fev.c.financing_event_id == event_id)).first()
        date_rows = connection.execute(select(fed).where(fed.c.financing_event_id == event_id).order_by(fed.c.id)).all()
    return CanonicalFinancingEvent(
        event=event,
        stage=None if stage_row is None else AcceptedStage(stage=Stage(stage_row.stage), resolution_decision_id=stage_row.resolution_decision_id, candidate_id=stage_row.candidate_id),
        financing_type=None if type_row is None else AcceptedFinancingType(financing_type=FinancingType(type_row.financing_type), resolution_decision_id=type_row.resolution_decision_id, candidate_id=type_row.candidate_id),
        verified_round_amount=None if amount_row is None else AcceptedVerifiedRoundAmount(
            money=Money(currency_code=amount_row.currency_code, minor_units=amount_row.amount_minor_units),
            resolution_decision_id=amount_row.resolution_decision_id, candidate_amount_id=amount_row.candidate_amount_id),
        dates=tuple(AcceptedDate(kind=FinancingDateKind(r.date_kind), time=EventTime(precision=EventTimePrecision(r.date_precision), start=r.date_start),
                                 resolution_decision_id=r.resolution_decision_id, candidate_date_id=r.candidate_date_id) for r in date_rows),
    )


def get_financing_resolution_decision(db: Engine | Connection, decision_id: int) -> StoredFinancingResolutionDecision:
    with _connection(db) as connection:
        row = connection.execute(select(decision).where(decision.c.id == decision_id)).one()
    return _decision(row)


def list_decisions_for_financing_candidate(db: Engine | Connection, candidate_id: int) -> list[StoredFinancingResolutionDecision]:
    with _connection(db) as connection:
        rows = connection.execute(select(decision).where(decision.c.candidate_id == candidate_id).order_by(decision.c.id)).all()
    return [_decision(r) for r in rows]


def get_financing_candidate_resolution_state(db: Engine | Connection, candidate_id: int) -> FinancingCandidateResolutionState:
    return derive_financing_candidate_state([d.decision_kind for d in list_decisions_for_financing_candidate(db, candidate_id)])


def lock_financing_candidate_for_resolution(connection: Connection, candidate_id: int):
    """Row-lock the (immutable) candidate so decisions on it are serialised. Returns its (company_id, stage, financing_type), or None."""
    row = connection.execute(select(fcc.c.company_id, fcc.c.stage, fcc.c.financing_type)
                             .where(fcc.c.id == candidate_id).with_for_update(key_share=True)).first()
    return None if row is None else (row.company_id, Stage(row.stage), FinancingType(row.financing_type))


def get_candidate_amount_row(connection: Connection, candidate_id: int, semantics: AmountSemantics):
    """(id, Money) of the candidate's amount for this semantics, or None if it was not proposed."""
    row = connection.execute(select(fca.c.id, fca.c.currency_code, fca.c.amount_minor_units)
                             .where(fca.c.candidate_id == candidate_id, fca.c.amount_semantics == semantics.value)).first()
    return None if row is None else (row.id, Money(currency_code=row.currency_code, minor_units=row.amount_minor_units))


def get_candidate_date_row(connection: Connection, candidate_id: int, kind: FinancingDateKind):
    """(id, EventTime) of the candidate's date for this kind, or None if it was not proposed."""
    from app.v2.domain.time import EventTime, EventTimePrecision
    row = connection.execute(select(fcd.c.id, fcd.c.date_precision, fcd.c.date_start)
                             .where(fcd.c.candidate_id == candidate_id, fcd.c.date_kind == kind.value)).first()
    return None if row is None else (row.id, EventTime(precision=EventTimePrecision(row.date_precision), start=row.date_start))


def get_financing_event_lineage(db: Engine | Connection, event_id: UUID) -> list[FinancingLineageLink]:
    """Every accepted fact of the event traced to its Source: fact -> decision -> candidate (fact) -> attempt -> observation -> payload -> source."""
    chain = fcc.join(pa, pa.c.id == fcc.c.processing_attempt_id).join(obs, obs.c.id == pa.c.observation_id).join(src, src.c.id == obs.c.source_id)
    cols = (fcc.c.id.label("cid"), pa.c.id.label("aid"), obs.c.id.label("oid"), obs.c.content_hash, src.c.id.label("sid"), src.c.source_key)
    links: list[FinancingLineageLink] = []
    with _connection(db) as connection:
        stage = connection.execute(select(fes.c.resolution_decision_id, *cols, fcc.c.event_evidence_start, fcc.c.event_evidence_end, fcc.c.event_evidence_hash,
                                          fcc.c.stage_evidence_start, fcc.c.stage_evidence_end, fcc.c.stage_evidence_hash)
                                   .select_from(fes.join(chain, fcc.c.id == fes.c.candidate_id))
                                   .where(fes.c.financing_event_id == event_id)).first()
        if stage is not None:
            links.append(FinancingLineageLink(subject="stage", financing_event_id=event_id, resolution_decision_id=stage.resolution_decision_id,
                                              candidate_id=stage.cid, processing_attempt_id=stage.aid, observation_id=stage.oid, content_hash=stage.content_hash,
                                              source_id=stage.sid, source_key=stage.source_key,
                                              evidence=EvidenceLocator(byte_start=stage.stage_evidence_start, byte_end=stage.stage_evidence_end, evidence_hash=stage.stage_evidence_hash)))
        ftype = connection.execute(select(fet.c.resolution_decision_id, *cols, fcc.c.type_evidence_start, fcc.c.type_evidence_end, fcc.c.type_evidence_hash)
                                   .select_from(fet.join(chain, fcc.c.id == fet.c.candidate_id))
                                   .where(fet.c.financing_event_id == event_id)).first()
        if ftype is not None:
            links.append(FinancingLineageLink(subject="financing_type", financing_event_id=event_id, resolution_decision_id=ftype.resolution_decision_id,
                                              candidate_id=ftype.cid, processing_attempt_id=ftype.aid, observation_id=ftype.oid, content_hash=ftype.content_hash,
                                              source_id=ftype.sid, source_key=ftype.source_key,
                                              evidence=EvidenceLocator(byte_start=ftype.type_evidence_start, byte_end=ftype.type_evidence_end, evidence_hash=ftype.type_evidence_hash)))
        amount = connection.execute(select(fev.c.resolution_decision_id, fca.c.evidence_start, fca.c.evidence_end, fca.c.evidence_hash, *cols)
                                    .select_from(fev.join(fca, fca.c.id == fev.c.candidate_amount_id).join(chain, fcc.c.id == fca.c.candidate_id))
                                    .where(fev.c.financing_event_id == event_id)).first()
        if amount is not None:
            links.append(FinancingLineageLink(subject="verified_round_amount", financing_event_id=event_id, resolution_decision_id=amount.resolution_decision_id,
                                              candidate_id=amount.cid, candidate_fact_id=None, processing_attempt_id=amount.aid, observation_id=amount.oid,
                                              content_hash=amount.content_hash, source_id=amount.sid, source_key=amount.source_key,
                                              evidence=EvidenceLocator(byte_start=amount.evidence_start, byte_end=amount.evidence_end, evidence_hash=amount.evidence_hash)))
        for r in connection.execute(select(fed.c.date_kind, fed.c.resolution_decision_id, fcd.c.evidence_start, fcd.c.evidence_end, fcd.c.evidence_hash, *cols)
                                    .select_from(fed.join(fcd, fcd.c.id == fed.c.candidate_date_id).join(chain, fcc.c.id == fcd.c.candidate_id))
                                    .where(fed.c.financing_event_id == event_id).order_by(fed.c.id)):
            links.append(FinancingLineageLink(subject=r.date_kind, financing_event_id=event_id, resolution_decision_id=r.resolution_decision_id,
                                              candidate_id=r.cid, candidate_fact_id=None, processing_attempt_id=r.aid, observation_id=r.oid,
                                              content_hash=r.content_hash, source_id=r.sid, source_key=r.source_key,
                                              evidence=EvidenceLocator(byte_start=r.evidence_start, byte_end=r.evidence_end, evidence_hash=r.evidence_hash)))
        # event-level provenance (one link per candidate that resolved into this event, via its event evidence)
        for r in connection.execute(select(decision.c.id.label("did"), *cols, fcc.c.event_evidence_start, fcc.c.event_evidence_end, fcc.c.event_evidence_hash)
                                    .select_from(decision.join(chain, fcc.c.id == decision.c.candidate_id))
                                    .where(decision.c.financing_event_id == event_id,
                                           decision.c.decision_kind.in_(("create_event", "attach_to_event")))
                                    .order_by(decision.c.id)):
            links.append(FinancingLineageLink(subject="event", financing_event_id=event_id, resolution_decision_id=r.did,
                                              candidate_id=r.cid, candidate_fact_id=None, processing_attempt_id=r.aid, observation_id=r.oid,
                                              content_hash=r.content_hash, source_id=r.sid, source_key=r.source_key,
                                              evidence=EvidenceLocator(byte_start=r.event_evidence_start, byte_end=r.event_evidence_end, evidence_hash=r.event_evidence_hash)))
    return links
