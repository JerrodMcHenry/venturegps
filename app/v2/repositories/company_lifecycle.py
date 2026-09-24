"""
READ-ONLY access to a company's accepted lifecycle facts and lifecycle resolution history.

Nothing in this module writes. Canonical writes live in exactly one place, app.v2.lifecycle._writes, reached
only through app.v2.lifecycle.promotion; an architecture test fails if any other module writes the canonical
lifecycle tables (company_name_history / company_operating_status / company_acquisition /
company_successor_relationship). Reads may be broad -- this mirrors app.v2.repositories.financing_events.

Unlike financing, there is no separate canonical "event" row: a lifecycle fact is always about an
ALREADY-canonical Company, so reads key directly off company_id.
"""

from uuid import UUID

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.engine import Connection, Engine

from app.v2.db.tables import company_acquisition_table as ca
from app.v2.db.tables import company_name_history_table as cnh
from app.v2.db.tables import company_operating_status_table as cos
from app.v2.db.tables import company_successor_relationship_table as csr
from app.v2.db.tables import lifecycle_event_candidate_acquisition_table as lca
from app.v2.db.tables import lifecycle_event_candidate_name_change_table as lcn
from app.v2.db.tables import lifecycle_event_candidate_operating_status_table as lco
from app.v2.db.tables import lifecycle_event_candidate_successor_table as lcs
from app.v2.db.tables import lifecycle_event_candidate_table as lec
from app.v2.db.tables import lifecycle_resolution_decision_table as decision
from app.v2.db.tables import observation_table as obs
from app.v2.db.tables import processing_attempt_table as pa
from app.v2.db.tables import source_table as src
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.lifecycle import OperatingStatus, SuccessorRelationshipKind
from app.v2.domain.lifecycle_resolution import (
    FINAL_LIFECYCLE_DECISION_KINDS,
    AcceptedAcquisition,
    AcceptedNameChange,
    AcceptedOperatingStatus,
    AcceptedSuccessorRelationship,
    Authority,
    AuthorityKind,
    CompanyLifecycleState,
    LifecycleCandidateResolutionState,
    LifecycleDecisionKind,
    LifecycleLineageLink,
    StoredLifecycleResolutionDecision,
    derive_lifecycle_candidate_state,
)
from app.v2.domain.time import EventTime, EventTimePrecision
from app.v2.repositories._db import connection as _connection

MAX_PENDING_LIST_LIMIT = 200


def _decision(row) -> StoredLifecycleResolutionDecision:
    try:
        return StoredLifecycleResolutionDecision(
            id=row.id, candidate_id=row.candidate_id, decision_kind=LifecycleDecisionKind(row.decision_kind),
            authority=Authority(kind=AuthorityKind(row.decided_by_kind), id=row.decided_by_id),
            reason_code=row.reason_code, created_at=row.created_at,
        )
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_lifecycle_decision_invalid", "a stored lifecycle decision does not satisfy the domain model") from None


def get_lifecycle_resolution_decision(db: Engine | Connection, decision_id: int) -> StoredLifecycleResolutionDecision:
    with _connection(db) as connection:
        row = connection.execute(select(decision).where(decision.c.id == decision_id)).one()
    return _decision(row)


def list_decisions_for_lifecycle_candidate(db: Engine | Connection, candidate_id: int) -> list[StoredLifecycleResolutionDecision]:
    with _connection(db) as connection:
        rows = connection.execute(select(decision).where(decision.c.candidate_id == candidate_id).order_by(decision.c.id)).all()
    return [_decision(r) for r in rows]


def get_lifecycle_candidate_resolution_state(db: Engine | Connection, candidate_id: int) -> LifecycleCandidateResolutionState:
    return derive_lifecycle_candidate_state([d.decision_kind for d in list_decisions_for_lifecycle_candidate(db, candidate_id)])


def get_company_lifecycle_state(db: Engine | Connection, company_id: UUID) -> CompanyLifecycleState:
    """Every accepted lifecycle fact for this company, oldest-first per kind. A company with zero accepted
    facts (the overwhelming majority, including every company that predates this increment) gets an all-empty
    state -- this function never fabricates a name or status."""
    with _connection(db) as connection:
        name_rows = connection.execute(select(cnh).where(cnh.c.company_id == company_id).order_by(cnh.c.created_at, cnh.c.id)).all()
        status_rows = connection.execute(select(cos).where(cos.c.company_id == company_id).order_by(cos.c.created_at, cos.c.id)).all()
        acq_rows = connection.execute(select(ca).where(ca.c.company_id == company_id).order_by(ca.c.created_at, ca.c.id)).all()
        succ_rows = connection.execute(select(csr).where(csr.c.company_id == company_id).order_by(csr.c.created_at, csr.c.id)).all()
    try:
        return CompanyLifecycleState(
            company_id=company_id,
            name_history=tuple(AcceptedNameChange(
                id=r.id, company_id=r.company_id, new_name=r.new_name,
                effective=None if r.effective_precision is None else EventTime(precision=EventTimePrecision(r.effective_precision), start=r.effective_start),
                resolution_decision_id=r.resolution_decision_id, candidate_id=r.candidate_id, created_at=r.created_at,
            ) for r in name_rows),
            status_history=tuple(AcceptedOperatingStatus(
                id=r.id, company_id=r.company_id, status=OperatingStatus(r.status),
                as_of=None if r.as_of_precision is None else EventTime(precision=EventTimePrecision(r.as_of_precision), start=r.as_of_start),
                resolution_decision_id=r.resolution_decision_id, candidate_id=r.candidate_id, created_at=r.created_at,
            ) for r in status_rows),
            acquisitions=tuple(AcceptedAcquisition(
                id=r.id, company_id=r.company_id, acquirer_name=r.acquirer_name, acquirer_company_id=r.acquirer_company_id,
                transaction_date=None if r.transaction_date_precision is None else EventTime(precision=EventTimePrecision(r.transaction_date_precision), start=r.transaction_date_start),
                resolution_decision_id=r.resolution_decision_id, candidate_id=r.candidate_id, created_at=r.created_at,
            ) for r in acq_rows),
            successors=tuple(AcceptedSuccessorRelationship(
                id=r.id, company_id=r.company_id, related_entity_name=r.related_entity_name, related_company_id=r.related_company_id,
                relationship_kind=SuccessorRelationshipKind(r.relationship_kind),
                resolution_decision_id=r.resolution_decision_id, candidate_id=r.candidate_id, created_at=r.created_at,
            ) for r in succ_rows),
        )
    except (DomainError, ValueError):
        raise InvariantViolationError("accepted_lifecycle_fact_invalid", "an accepted lifecycle fact does not satisfy the domain model") from None


def get_current_legal_name(db: Engine | Connection, company_id: UUID, *, original_name: str) -> str:
    """The company's original canonical name unless a rename has been accepted, in which case the
    most-recently-accepted one. Never rewrites company.company_name; purely a derived read."""
    state = get_company_lifecycle_state(db, company_id)
    return state.current_legal_name or original_name


def list_pending_lifecycle_candidates(db: Engine | Connection, limit: int = 50, offset: int = 0):
    from app.v2.repositories.lifecycle_candidates import get_lifecycle_event_candidate  # local import: avoids a load-order cycle
    if type(limit) is not int or limit < 1 or limit > MAX_PENDING_LIST_LIMIT:
        raise InvalidInputError("invalid_limit", f"limit must be 1-{MAX_PENDING_LIST_LIMIT}")
    if type(offset) is not int or offset < 0:
        raise InvalidInputError("invalid_offset", "offset must be 0 or a positive integer")
    has_final_decision = (
        select(decision.c.id).where(decision.c.candidate_id == lec.c.id, decision.c.decision_kind.in_([k.value for k in FINAL_LIFECYCLE_DECISION_KINDS])).exists()
    )
    with _connection(db) as connection:
        ids = connection.execute(
            select(lec.c.id).where(~has_final_decision).order_by(lec.c.created_at.desc(), lec.c.id.desc()).limit(limit).offset(offset)
        ).scalars().all()
    return [found for i in ids if (found := get_lifecycle_event_candidate(db, i)) is not None]


def list_lifecycle_candidates_for_review(
    db: Engine | Connection, *, status: str = "pending", search: str | None = None,
    include_test_sources: bool = False, limit: int = 50, offset: int = 0,
):
    """The lifecycle review queue, generalized exactly like financing_events.list_financing_candidates_for_review:
    status filter, free-text search (source's own record identifier, or a company_id substring), STRUCTURAL
    test-source exclusion via a join to the candidate's own Source. Returns (page, total_matching_count)."""
    from app.v2.repositories.lifecycle_candidates import get_lifecycle_event_candidate  # local import: avoids a load-order cycle
    if status not in ("pending", "resolved", "all"):
        raise InvalidInputError("invalid_status_filter", "status must be one of: pending, resolved, all")
    if type(limit) is not int or limit < 1 or limit > MAX_PENDING_LIST_LIMIT:
        raise InvalidInputError("invalid_limit", f"limit must be 1-{MAX_PENDING_LIST_LIMIT}")
    if type(offset) is not int or offset < 0:
        raise InvalidInputError("invalid_offset", "offset must be 0 or a positive integer")

    has_final_decision = (
        select(decision.c.id)
        .where(decision.c.candidate_id == lec.c.id, decision.c.decision_kind.in_([k.value for k in FINAL_LIFECYCLE_DECISION_KINDS]))
        .exists()
    )
    base = lec.join(pa, pa.c.id == lec.c.processing_attempt_id).join(obs, obs.c.id == pa.c.observation_id).join(src, src.c.id == obs.c.source_id)

    conditions = []
    if status == "pending":
        conditions.append(~has_final_decision)
    elif status == "resolved":
        conditions.append(has_final_decision)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        conditions.append(or_(obs.c.source_record_identifier.ilike(pattern), cast(lec.c.company_id, Text).ilike(pattern)))
    if not include_test_sources:
        conditions.append(src.c.is_test.is_(False))

    id_query = select(lec.c.id).select_from(base)
    count_query = select(func.count()).select_from(base)
    for condition in conditions:
        id_query = id_query.where(condition)
        count_query = count_query.where(condition)
    id_query = id_query.order_by(lec.c.created_at.desc(), lec.c.id.desc()).limit(limit).offset(offset)

    with _connection(db) as connection:
        ids = connection.execute(id_query).scalars().all()
        total = connection.execute(count_query).scalar_one()

    found = [c for i in ids if (c := get_lifecycle_event_candidate(db, i)) is not None]
    return found, total


def lock_lifecycle_candidate_for_resolution(connection: Connection, candidate_id: int) -> UUID | None:
    """Row-lock the (immutable) candidate so decisions on it are serialised. Returns its company_id, or None."""
    row = connection.execute(select(lec.c.company_id).where(lec.c.id == candidate_id).with_for_update(key_share=True)).first()
    return None if row is None else row.company_id


def get_candidate_name_change_row(connection: Connection, candidate_id: int):
    row = connection.execute(select(lcn).where(lcn.c.candidate_id == candidate_id)).first()
    if row is None:
        return None
    effective = None if row.effective_precision is None else EventTime(precision=EventTimePrecision(row.effective_precision), start=row.effective_start)
    return row.new_name, effective


def get_candidate_operating_status_row(connection: Connection, candidate_id: int):
    row = connection.execute(select(lco).where(lco.c.candidate_id == candidate_id)).first()
    if row is None:
        return None
    as_of = None if row.as_of_precision is None else EventTime(precision=EventTimePrecision(row.as_of_precision), start=row.as_of_start)
    return OperatingStatus(row.status), as_of


def get_candidate_acquisition_row(connection: Connection, candidate_id: int):
    row = connection.execute(select(lca).where(lca.c.candidate_id == candidate_id)).first()
    if row is None:
        return None
    txn = None if row.transaction_date_precision is None else EventTime(precision=EventTimePrecision(row.transaction_date_precision), start=row.transaction_date_start)
    return row.acquirer_name, row.acquirer_company_id, txn


def get_candidate_successor_row(connection: Connection, candidate_id: int):
    row = connection.execute(select(lcs).where(lcs.c.candidate_id == candidate_id)).first()
    if row is None:
        return None
    return row.related_entity_name, row.related_company_id, SuccessorRelationshipKind(row.relationship_kind)


def get_company_lifecycle_lineage(db: Engine | Connection, company_id: UUID) -> list[LifecycleLineageLink]:
    """Every accepted fact of the company traced to its Source: fact -> decision -> candidate -> attempt ->
    observation -> payload -> source. Mirrors financing_events.get_financing_event_lineage."""
    chain = lec.join(pa, pa.c.id == lec.c.processing_attempt_id).join(obs, obs.c.id == pa.c.observation_id).join(src, src.c.id == obs.c.source_id)
    cols = (lec.c.id.label("cid"), pa.c.id.label("aid"), obs.c.id.label("oid"), obs.c.content_hash, src.c.id.label("sid"), src.c.source_key)
    links: list[LifecycleLineageLink] = []
    with _connection(db) as connection:
        for r in connection.execute(select(cnh.c.id, cnh.c.resolution_decision_id, *cols, lcn.c.evidence_start, lcn.c.evidence_end, lcn.c.evidence_hash)
                                    .select_from(cnh.join(lcn, lcn.c.candidate_id == cnh.c.candidate_id).join(chain, lec.c.id == cnh.c.candidate_id))
                                    .where(cnh.c.company_id == company_id).order_by(cnh.c.id)):
            links.append(LifecycleLineageLink(fact_kind="name_change", fact_id=r.id, company_id=company_id, resolution_decision_id=r.resolution_decision_id,
                                              candidate_id=r.cid, processing_attempt_id=r.aid, observation_id=r.oid, content_hash=r.content_hash,
                                              source_id=r.sid, source_key=r.source_key,
                                              evidence=EvidenceLocator(byte_start=r.evidence_start, byte_end=r.evidence_end, evidence_hash=r.evidence_hash)))
        for r in connection.execute(select(cos.c.id, cos.c.resolution_decision_id, *cols, lco.c.evidence_start, lco.c.evidence_end, lco.c.evidence_hash)
                                    .select_from(cos.join(lco, lco.c.candidate_id == cos.c.candidate_id).join(chain, lec.c.id == cos.c.candidate_id))
                                    .where(cos.c.company_id == company_id).order_by(cos.c.id)):
            links.append(LifecycleLineageLink(fact_kind="operating_status", fact_id=r.id, company_id=company_id, resolution_decision_id=r.resolution_decision_id,
                                              candidate_id=r.cid, processing_attempt_id=r.aid, observation_id=r.oid, content_hash=r.content_hash,
                                              source_id=r.sid, source_key=r.source_key,
                                              evidence=EvidenceLocator(byte_start=r.evidence_start, byte_end=r.evidence_end, evidence_hash=r.evidence_hash)))
        for r in connection.execute(select(ca.c.id, ca.c.resolution_decision_id, *cols, lca.c.evidence_start, lca.c.evidence_end, lca.c.evidence_hash)
                                    .select_from(ca.join(lca, lca.c.candidate_id == ca.c.candidate_id).join(chain, lec.c.id == ca.c.candidate_id))
                                    .where(ca.c.company_id == company_id).order_by(ca.c.id)):
            links.append(LifecycleLineageLink(fact_kind="acquisition", fact_id=r.id, company_id=company_id, resolution_decision_id=r.resolution_decision_id,
                                              candidate_id=r.cid, processing_attempt_id=r.aid, observation_id=r.oid, content_hash=r.content_hash,
                                              source_id=r.sid, source_key=r.source_key,
                                              evidence=EvidenceLocator(byte_start=r.evidence_start, byte_end=r.evidence_end, evidence_hash=r.evidence_hash)))
        for r in connection.execute(select(csr.c.id, csr.c.resolution_decision_id, *cols, lcs.c.evidence_start, lcs.c.evidence_end, lcs.c.evidence_hash)
                                    .select_from(csr.join(lcs, lcs.c.candidate_id == csr.c.candidate_id).join(chain, lec.c.id == csr.c.candidate_id))
                                    .where(csr.c.company_id == company_id).order_by(csr.c.id)):
            links.append(LifecycleLineageLink(fact_kind="successor", fact_id=r.id, company_id=company_id, resolution_decision_id=r.resolution_decision_id,
                                              candidate_id=r.cid, processing_attempt_id=r.aid, observation_id=r.oid, content_hash=r.content_hash,
                                              source_id=r.sid, source_key=r.source_key,
                                              evidence=EvidenceLocator(byte_start=r.evidence_start, byte_end=r.evidence_end, evidence_hash=r.evidence_hash)))
    return links
