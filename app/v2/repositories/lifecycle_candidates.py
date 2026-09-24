"""
Lifecycle-event candidate persistence: immutable records of what a processing attempt PROPOSED about an
ALREADY-canonical company's name history, operating status, acquisition, or successor relationship. A stored
candidate is still UNTRUSTED: nothing here creates canonical state, and this module writes ONLY the five
lifecycle-candidate tables. Attempts, observations, payloads, and companies are read-only here.

    persist_lifecycle_event_candidates(db, attempt_id, proposals) -> LifecycleCandidatesStoreResult
    get_lifecycle_event_candidate(db, candidate_id)
    list_lifecycle_event_candidates(db, attempt_id)
    list_lifecycle_event_candidates_for_company(db, company_id)
    list_lifecycle_event_candidates_for_observation(db, observation_id)

Persistence rules, mirroring app.v2.repositories.financing_event_candidates exactly:
  1. the attempt must exist and be PROCESSING (row-locked FOR SHARE so it cannot finish underneath the write);
     a terminal attempt never receives candidates and is never reopened or otherwise modified;
  2. its Observation and verified RawPayload are loaded;
  3. every proposal's Company must already exist (FOR KEY SHARE); this module never creates Companies;
  4. every locator (event, and each present typed fact) is verified against the exact payload bytes
     (app.v2.candidates.lifecycle_evidence);
  5. the whole batch is atomic: one invalid proposal rejects all of them (SAVEPOINT on a Connection).

Identity is (processing_attempt_id, candidate_ordinal). Replaying an identical batch returns the stored
candidates with created=False; a DIFFERENT proposal at an existing ordinal is a ConflictError.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.candidates.lifecycle_evidence import verify_lifecycle_proposal
from app.v2.db.tables import company_table
from app.v2.db.tables import lifecycle_event_candidate_acquisition_table as lca
from app.v2.db.tables import lifecycle_event_candidate_name_change_table as lcn
from app.v2.db.tables import lifecycle_event_candidate_operating_status_table as lco
from app.v2.db.tables import lifecycle_event_candidate_successor_table as lcs
from app.v2.db.tables import lifecycle_event_candidate_table as lec
from app.v2.db.tables import processing_attempt_table as pa
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.lifecycle import (
    MAX_LIFECYCLE_CANDIDATES_PER_ATTEMPT,
    LifecycleEventCandidateProposal,
    OperatingStatus,
    ProposedAcquisition,
    ProposedNameChange,
    ProposedOperatingStatus,
    ProposedSuccessorRelationship,
    StoredLifecycleEventCandidate,
    SuccessorRelationshipKind,
)
from app.v2.domain.time import EventTime, EventTimePrecision
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import integrity_error_to_domain
from app.v2.repositories.company_candidates import load_proposal_context
from app.v2.repositories.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class LifecycleCandidatesStoreResult:
    candidates: tuple[StoredLifecycleEventCandidate, ...]   # in candidate_ordinal order
    created: tuple[bool, ...]                                # aligned with candidates

    @property
    def created_count(self) -> int:
        return sum(self.created)


def _locator(start, end, digest) -> EvidenceLocator:
    return EvidenceLocator(byte_start=start, byte_end=end, evidence_hash=digest)


def _time(precision, start) -> EventTime | None:
    return None if precision is None else EventTime(precision=EventTimePrecision(precision), start=start)


# ---------------------------------------------------------------- reads

def _load(connection: Connection, where) -> list[StoredLifecycleEventCandidate]:
    rows = connection.execute(select(lec).where(where).order_by(lec.c.processing_attempt_id, lec.c.candidate_ordinal)).all()
    if not rows:
        return []
    ids = [row.id for row in rows]
    name_changes = {r.candidate_id: r for r in connection.execute(select(lcn).where(lcn.c.candidate_id.in_(ids)))}
    statuses = {r.candidate_id: r for r in connection.execute(select(lco).where(lco.c.candidate_id.in_(ids)))}
    acquisitions = {r.candidate_id: r for r in connection.execute(select(lca).where(lca.c.candidate_id.in_(ids)))}
    successors = {r.candidate_id: r for r in connection.execute(select(lcs).where(lcs.c.candidate_id.in_(ids)))}
    try:
        out = []
        for row in rows:
            nc, st, aq, su = name_changes.get(row.id), statuses.get(row.id), acquisitions.get(row.id), successors.get(row.id)
            out.append(StoredLifecycleEventCandidate(
                id=row.id, processing_attempt_id=row.processing_attempt_id, candidate_ordinal=row.candidate_ordinal,
                proposal=LifecycleEventCandidateProposal(
                    company_id=row.company_id,
                    event_evidence=_locator(row.event_evidence_start, row.event_evidence_end, row.event_evidence_hash),
                    name_change=None if nc is None else ProposedNameChange(
                        new_name=nc.new_name, effective=_time(nc.effective_precision, nc.effective_start),
                        evidence=_locator(nc.evidence_start, nc.evidence_end, nc.evidence_hash)),
                    operating_status=None if st is None else ProposedOperatingStatus(
                        status=OperatingStatus(st.status), as_of=_time(st.as_of_precision, st.as_of_start),
                        evidence=_locator(st.evidence_start, st.evidence_end, st.evidence_hash)),
                    acquisition=None if aq is None else ProposedAcquisition(
                        acquirer_name=aq.acquirer_name, acquirer_company_id=aq.acquirer_company_id,
                        transaction_date=_time(aq.transaction_date_precision, aq.transaction_date_start),
                        evidence=_locator(aq.evidence_start, aq.evidence_end, aq.evidence_hash)),
                    successor=None if su is None else ProposedSuccessorRelationship(
                        related_entity_name=su.related_entity_name, related_company_id=su.related_company_id,
                        relationship_kind=SuccessorRelationshipKind(su.relationship_kind),
                        evidence=_locator(su.evidence_start, su.evidence_end, su.evidence_hash)),
                ),
                created_at=row.created_at,
            ))
        return out
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_lifecycle_candidate_invalid", "a stored lifecycle candidate does not satisfy the domain model") from None


def get_lifecycle_event_candidate(db: Engine | Connection, candidate_id: int) -> StoredLifecycleEventCandidate | None:
    with _connection(db) as connection:
        found = _load(connection, lec.c.id == candidate_id)
    return found[0] if found else None


def list_lifecycle_event_candidates(db: Engine | Connection, attempt_id: int) -> list[StoredLifecycleEventCandidate]:
    with _connection(db) as connection:
        return _load(connection, lec.c.processing_attempt_id == attempt_id)


def list_lifecycle_event_candidates_for_company(db: Engine | Connection, company_id: UUID) -> list[StoredLifecycleEventCandidate]:
    with _connection(db) as connection:
        return _load(connection, lec.c.company_id == company_id)


def list_lifecycle_event_candidates_for_observation(db: Engine | Connection, observation_id: int) -> list[StoredLifecycleEventCandidate]:
    with _connection(db) as connection:
        attempt_ids = select(pa.c.id).where(pa.c.observation_id == observation_id)
        return _load(connection, lec.c.processing_attempt_id.in_(attempt_ids))


# ---------------------------------------------------------------- writes

def _insert_facts(connection: Connection, candidate_id: int, proposal: LifecycleEventCandidateProposal) -> None:
    if proposal.name_change:
        nc = proposal.name_change
        connection.execute(insert(lcn), [{
            "candidate_id": candidate_id, "new_name": nc.new_name,
            "effective_precision": nc.effective.precision.value if nc.effective else None,
            "effective_start": nc.effective.start if nc.effective else None,
            "evidence_start": nc.evidence.byte_start, "evidence_end": nc.evidence.byte_end, "evidence_hash": nc.evidence.evidence_hash,
        }])
    if proposal.operating_status:
        st = proposal.operating_status
        connection.execute(insert(lco), [{
            "candidate_id": candidate_id, "status": st.status.value,
            "as_of_precision": st.as_of.precision.value if st.as_of else None,
            "as_of_start": st.as_of.start if st.as_of else None,
            "evidence_start": st.evidence.byte_start, "evidence_end": st.evidence.byte_end, "evidence_hash": st.evidence.evidence_hash,
        }])
    if proposal.acquisition:
        aq = proposal.acquisition
        connection.execute(insert(lca), [{
            "candidate_id": candidate_id, "acquirer_name": aq.acquirer_name, "acquirer_company_id": aq.acquirer_company_id,
            "transaction_date_precision": aq.transaction_date.precision.value if aq.transaction_date else None,
            "transaction_date_start": aq.transaction_date.start if aq.transaction_date else None,
            "evidence_start": aq.evidence.byte_start, "evidence_end": aq.evidence.byte_end, "evidence_hash": aq.evidence.evidence_hash,
        }])
    if proposal.successor:
        su = proposal.successor
        connection.execute(insert(lcs), [{
            "candidate_id": candidate_id, "related_entity_name": su.related_entity_name, "related_company_id": su.related_company_id,
            "relationship_kind": su.relationship_kind.value,
            "evidence_start": su.evidence.byte_start, "evidence_end": su.evidence.byte_end, "evidence_hash": su.evidence.evidence_hash,
        }])


def persist_lifecycle_event_candidates(
    db: Engine | Connection, attempt_id: int, proposals: Sequence[LifecycleEventCandidateProposal]
) -> LifecycleCandidatesStoreResult:
    """Verify every proposal against the immutable evidence AND that its Company already exists, then persist
    them all atomically (or none)."""
    proposals = tuple(proposals)
    if len(proposals) > MAX_LIFECYCLE_CANDIDATES_PER_ATTEMPT:
        raise InvalidInputError("too_many_candidates", f"an attempt may propose at most {MAX_LIFECYCLE_CANDIDATES_PER_ATTEMPT} lifecycle candidates")
    for proposal in proposals:
        if not isinstance(proposal, LifecycleEventCandidateProposal):
            raise InvalidInputError("not_a_proposal", "only LifecycleEventCandidateProposal objects can be stored")

    with _connection(db) as connection:
        context = load_proposal_context(connection, attempt_id)
        media_type = context.observation.observation.sniffed_media_type
        for ordinal, proposal in enumerate(proposals, start=1):          # verify ALL before writing ANY
            verify_lifecycle_proposal(proposal, context.payload, media_type, ordinal=ordinal)
            exists = connection.execute(select(company_table.c.id).where(company_table.c.id == proposal.company_id)
                                        .with_for_update(read=True, key_share=True)).first()
            if exists is None:
                raise NotFoundError("company_not_found", f"lifecycle candidate {ordinal}: the company does not exist canonically")
            if proposal.acquisition and proposal.acquisition.acquirer_company_id is not None:
                acquirer_exists = connection.execute(select(company_table.c.id).where(company_table.c.id == proposal.acquisition.acquirer_company_id)).first()
                if acquirer_exists is None:
                    raise NotFoundError("acquirer_company_not_found", f"lifecycle candidate {ordinal}: the proposed acquirer_company_id does not exist canonically")
            if proposal.successor and proposal.successor.related_company_id is not None:
                related_exists = connection.execute(select(company_table.c.id).where(company_table.c.id == proposal.successor.related_company_id)).first()
                if related_exists is None:
                    raise NotFoundError("related_company_not_found", f"lifecycle candidate {ordinal}: the proposed related_company_id does not exist canonically")

        stored: list[StoredLifecycleEventCandidate] = []
        created: list[bool] = []
        for ordinal, proposal in enumerate(proposals, start=1):
            try:
                inserted_id = connection.execute(
                    pg_insert(lec).values(
                        processing_attempt_id=attempt_id, company_id=proposal.company_id, candidate_ordinal=ordinal,
                        event_evidence_start=proposal.event_evidence.byte_start, event_evidence_end=proposal.event_evidence.byte_end,
                        event_evidence_hash=proposal.event_evidence.evidence_hash,
                        # created_at is deliberately absent: the database assigns it.
                    ).on_conflict_do_nothing(index_elements=[lec.c.processing_attempt_id, lec.c.candidate_ordinal]).returning(lec.c.id)
                ).scalar()
                if inserted_id is not None:
                    _insert_facts(connection, inserted_id, proposal)
            except IntegrityError as exc:
                raise integrity_error_to_domain(exc) from None

            if inserted_id is not None:
                stored.append(_load(connection, lec.c.id == inserted_id)[0])
                created.append(True)
                continue
            existing = _load(connection, (lec.c.processing_attempt_id == attempt_id) & (lec.c.candidate_ordinal == ordinal))[0]
            if existing.proposal != proposal:
                raise ConflictError("candidate_ordinal_conflict", f"lifecycle candidate {ordinal} already exists with different content")
            stored.append(existing)
            created.append(False)
        return LifecycleCandidatesStoreResult(candidates=tuple(stored), created=tuple(created))
