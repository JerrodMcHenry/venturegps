"""
READ-ONLY access to canonical Company identity and resolution history.

Nothing in this module writes. Canonical writes live in exactly one place,
app.v2.resolution._writes, reached only through app.v2.resolution.promotion; an architecture
test fails if any other module writes the canonical tables. Reads may be broad.
"""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.engine import Connection, Engine

from app.v2.db.tables import company_candidate_identifier_table as ci
from app.v2.db.tables import company_candidate_table as cc
from app.v2.db.tables import company_identifier_table as company_identifier
from app.v2.db.tables import company_name_table as company_name
from app.v2.db.tables import company_table as company
from app.v2.db.tables import observation_table as obs
from app.v2.db.tables import processing_attempt_table as pa
from app.v2.db.tables import resolution_decision_table as decision
from app.v2.db.tables import source_table as src
from app.v2.domain.candidate import IdentifierType, StoredCompanyCandidate
from app.v2.domain.company import (
    CompanyNameRole,
    LineageLink,
    StoredCompany,
    StoredCompanyIdentifier,
    StoredCompanyName,
    normalize_identifier,
)
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.resolution import (
    FINAL_DECISION_KINDS,
    Authority,
    AuthorityKind,
    CandidateResolutionState,
    DecisionKind,
    StoredResolutionDecision,
    derive_candidate_state,
)
from app.v2.repositories._db import connection as _connection

MAX_PENDING_LIST_LIMIT = 200


def _decision(row) -> StoredResolutionDecision:
    try:
        return StoredResolutionDecision(
            id=row.id, candidate_id=row.candidate_id, decision_kind=DecisionKind(row.decision_kind),
            company_id=row.company_id, authority=Authority(kind=AuthorityKind(row.decided_by_kind), id=row.decided_by_id),
            reason_code=row.reason_code, created_at=row.created_at,
        )
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_decision_invalid", "a stored decision does not satisfy the domain model") from None


def get_company(db: Engine | Connection, company_id: UUID) -> StoredCompany | None:
    with _connection(db) as connection:
        row = connection.execute(select(company).where(company.c.id == company_id)).first()
    return None if row is None else StoredCompany(id=row.id, created_at=row.created_at)


def list_company_names(db: Engine | Connection, company_id: UUID) -> list[StoredCompanyName]:
    with _connection(db) as connection:
        rows = connection.execute(select(company_name).where(company_name.c.company_id == company_id)
                                  .order_by(company_name.c.id)).all()
    return [StoredCompanyName(id=r.id, company_id=r.company_id, name=r.name, name_role=CompanyNameRole(r.name_role),
                              resolution_decision_id=r.resolution_decision_id, created_at=r.created_at) for r in rows]


def list_company_identifiers(db: Engine | Connection, company_id: UUID) -> list[StoredCompanyIdentifier]:
    with _connection(db) as connection:
        rows = connection.execute(select(company_identifier).where(company_identifier.c.company_id == company_id)
                                  .order_by(company_identifier.c.id)).all()
    return [StoredCompanyIdentifier(id=r.id, company_id=r.company_id, identifier_type=IdentifierType(r.identifier_type),
                                    identifier_value=r.identifier_value, resolution_decision_id=r.resolution_decision_id,
                                    candidate_identifier_id=r.candidate_identifier_id, created_at=r.created_at) for r in rows]


def find_company_ids_by_identifier(db: Engine | Connection, identifier_type: IdentifierType, value: str) -> list[UUID]:
    """Companies owning exactly this identifier after normalization (at most one, by constraint)."""
    normalized = normalize_identifier(identifier_type, value)
    with _connection(db) as connection:
        rows = connection.execute(select(company_identifier.c.company_id).where(
            company_identifier.c.identifier_type == identifier_type.value,
            company_identifier.c.identifier_value == normalized)).all()
    return [r.company_id for r in rows]


def get_resolution_decision(db: Engine | Connection, decision_id: int) -> StoredResolutionDecision:
    with _connection(db) as connection:
        row = connection.execute(select(decision).where(decision.c.id == decision_id)).one()
    return _decision(row)


def list_decisions_for_candidate(db: Engine | Connection, candidate_id: int) -> list[StoredResolutionDecision]:
    """The candidate's resolution history, oldest first."""
    with _connection(db) as connection:
        rows = connection.execute(select(decision).where(decision.c.candidate_id == candidate_id)
                                  .order_by(decision.c.id)).all()
    return [_decision(r) for r in rows]


def get_candidate_resolution_state(db: Engine | Connection, candidate_id: int) -> CandidateResolutionState:
    """DERIVED from the decision history; candidates store no resolution status."""
    return derive_candidate_state([d.decision_kind for d in list_decisions_for_candidate(db, candidate_id)])


def list_pending_company_candidates(db: Engine | Connection, limit: int = 50, offset: int = 0) -> list[StoredCompanyCandidate]:
    """Increment 18.4 -- the review queue: every candidate with no FINAL decision (FINAL_DECISION_KINDS -- the
    exact same closed set resolution.promotion itself checks; this adds no new business meaning, only a read
    over it). A deferred candidate (not a final kind) is correctly still pending. Newest first. This module is
    the right home for it (not app.v2.repositories.company_candidates, which is candidate-table-only by a
    closed, architecture-enforced import set -- see that module's own test): "reads may be broad" here, and this
    module already reads both the candidate and resolution_decision tables together (get_candidate_resolution_state,
    just above)."""
    if type(limit) is not int or limit < 1 or limit > MAX_PENDING_LIST_LIMIT:
        raise InvalidInputError("invalid_limit", f"limit must be 1-{MAX_PENDING_LIST_LIMIT}")
    if type(offset) is not int or offset < 0:
        raise InvalidInputError("invalid_offset", "offset must be 0 or a positive integer")
    has_final_decision = (
        select(decision.c.id).where(decision.c.candidate_id == cc.c.id, decision.c.decision_kind.in_([k.value for k in FINAL_DECISION_KINDS])).exists()
    )
    with _connection(db) as connection:
        ids = connection.execute(
            select(cc.c.id).where(~has_final_decision).order_by(cc.c.created_at.desc(), cc.c.id.desc()).limit(limit).offset(offset)
        ).scalars().all()
    from app.v2.repositories.company_candidates import get_company_candidate  # local import: avoids a module-load-order cycle
    return [found for i in ids if (found := get_company_candidate(db, i)) is not None]


def list_company_candidates_for_review(
    db: Engine | Connection, *, status: str = "pending", search: str | None = None,
    include_test_sources: bool = False, limit: int = 50, offset: int = 0,
) -> tuple[list[StoredCompanyCandidate], int]:
    """Increment 18.5 -- the review queue, generalized on top of list_pending_company_candidates (which stays
    exactly as it was, for existing callers): a status filter (pending/resolved/all), a free-text search over
    the proposed name AND the source's own record identifier (e.g. an SEC accession number), and test-source
    exclusion. Test-source exclusion is STRUCTURAL -- a join to the candidate's own Source row and a check of
    its is_test column -- never a name-prefix match on the candidate itself, exactly as required: a synthetic
    candidate proposing the name "Acme Robotics" is excluded because of where its evidence came from, not
    because of what it says. Returns (page, total_matching_count) so a caller can paginate for real."""
    if status not in ("pending", "resolved", "all"):
        raise InvalidInputError("invalid_status_filter", "status must be one of: pending, resolved, all")
    if type(limit) is not int or limit < 1 or limit > MAX_PENDING_LIST_LIMIT:
        raise InvalidInputError("invalid_limit", f"limit must be 1-{MAX_PENDING_LIST_LIMIT}")
    if type(offset) is not int or offset < 0:
        raise InvalidInputError("invalid_offset", "offset must be 0 or a positive integer")

    has_final_decision = (
        select(decision.c.id)
        .where(decision.c.candidate_id == cc.c.id, decision.c.decision_kind.in_([k.value for k in FINAL_DECISION_KINDS]))
        .exists()
    )
    base = cc.join(pa, pa.c.id == cc.c.processing_attempt_id).join(obs, obs.c.id == pa.c.observation_id).join(src, src.c.id == obs.c.source_id)

    conditions = []
    if status == "pending":
        conditions.append(~has_final_decision)
    elif status == "resolved":
        conditions.append(has_final_decision)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        conditions.append(or_(cc.c.proposed_name.ilike(pattern), obs.c.source_record_identifier.ilike(pattern)))
    if not include_test_sources:
        conditions.append(src.c.is_test.is_(False))

    id_query = select(cc.c.id).select_from(base)
    count_query = select(func.count()).select_from(base)
    for condition in conditions:
        id_query = id_query.where(condition)
        count_query = count_query.where(condition)
    id_query = id_query.order_by(cc.c.created_at.desc(), cc.c.id.desc()).limit(limit).offset(offset)

    with _connection(db) as connection:
        ids = connection.execute(id_query).scalars().all()
        total = connection.execute(count_query).scalar_one()

    from app.v2.repositories.company_candidates import get_company_candidate  # local import: avoids a module-load-order cycle
    found = [c for i in ids if (c := get_company_candidate(db, i)) is not None]
    return found, total


def lock_candidate_for_resolution(connection: Connection, candidate_id: int) -> bool:
    """Row-lock the (immutable) candidate so decisions on it are serialised. False if it does not exist."""
    return connection.execute(select(cc.c.id).where(cc.c.id == candidate_id).with_for_update(key_share=True)).first() is not None


def list_candidate_identifier_rows(connection: Connection, candidate_id: int):
    """(id, IdentifierType, value) of the candidate's proposed identifiers, in proposal order."""
    rows = connection.execute(select(ci.c.id, ci.c.identifier_type, ci.c.identifier_value)
                              .where(ci.c.candidate_id == candidate_id).order_by(ci.c.identifier_ordinal)).all()
    return [(r.id, IdentifierType(r.identifier_type), r.identifier_value) for r in rows]


def get_company_lineage(db: Engine | Connection, company_id: UUID) -> list[LineageLink]:
    """Every accepted fact of the company traced to its Source:
    fact -> decision -> candidate -> attempt -> observation -> payload hash -> source."""
    columns = (cc.c.id.label("cid"), pa.c.id.label("aid"), obs.c.id.label("oid"), obs.c.content_hash,
               src.c.id.label("sid"), src.c.source_key)

    def upstream(facts, candidate_id_column):
        return (facts.join(cc, cc.c.id == candidate_id_column).join(pa, pa.c.id == cc.c.processing_attempt_id)
                .join(obs, obs.c.id == pa.c.observation_id).join(src, src.c.id == obs.c.source_id))

    def link(kind, r) -> LineageLink:
        return LineageLink(fact_kind=kind, fact_id=r.id, company_id=r.company_id, resolution_decision_id=r.resolution_decision_id,
                           candidate_id=r.cid, processing_attempt_id=r.aid, observation_id=r.oid, content_hash=r.content_hash,
                           source_id=r.sid, source_key=r.source_key)

    with _connection(db) as connection:
        names = connection.execute(
            select(company_name.c.id, company_name.c.company_id, company_name.c.resolution_decision_id, *columns)
            .select_from(upstream(company_name, company_name.c.candidate_id))
            .where(company_name.c.company_id == company_id).order_by(company_name.c.id)).all()
        identifiers = connection.execute(
            select(company_identifier.c.id, company_identifier.c.company_id, company_identifier.c.resolution_decision_id, *columns)
            .select_from(upstream(company_identifier.join(ci, ci.c.id == company_identifier.c.candidate_identifier_id), ci.c.candidate_id))
            .where(company_identifier.c.company_id == company_id).order_by(company_identifier.c.id)).all()
    return [link("name", r) for r in names] + [link("identifier", r) for r in identifiers]
