"""
Company-candidate persistence: immutable records of what a processing attempt
PROPOSED. A stored candidate is still UNTRUSTED: nothing in this module creates
canonical state, and it reads/writes only candidate tables (attempts, observations
and payloads are read-only here).

    load_proposal_context(db, attempt_id)              -> ProposalContext
    store_company_candidates(db, attempt_id, proposals) -> CandidatesStoreResult
    get_company_candidate(db, candidate_id)
    list_company_candidates(db, attempt_id)
    list_company_candidates_for_observation(db, observation_id)

Persistence rules, all verified here BEFORE any write and re-checked by database triggers:
  - the attempt must exist and be PROCESSING (it is row-locked FOR SHARE for the
    transaction, so it cannot finish underneath the write); a terminal attempt
    never receives candidates and is never reopened;
  - every proposal's evidence is verified against the exact bytes of the
    Observation's immutable RawPayload (app.v2.candidates.evidence): media type,
    bounds, sha256 of the exact span, and that the proposed value appears in it.
    Nothing is repaired or fuzzy-matched;
  - the whole batch is atomic: one invalid proposal rejects all of them.

Identity is (processing_attempt_id, candidate_ordinal) where the ordinal is the
proposal's position (1-based) in the batch, so replaying the same batch is
idempotent: identical candidates are returned with created=False; a DIFFERENT
proposal at an existing ordinal is a ConflictError (never silently ignored or
overwritten). A name is never identity. created_at is the database's.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.candidates.evidence import verify_proposal
from app.v2.db.tables import company_candidate_identifier_table as ci
from app.v2.db.tables import company_candidate_table as cc
from app.v2.db.tables import observation_table as obs
from app.v2.db.tables import processing_attempt_table as pa
from app.v2.domain.candidate import (
    MAX_CANDIDATES_PER_ATTEMPT,
    CompanyCandidateProposal,
    EvidenceLocator,
    IdentifierType,
    ProposedIdentifier,
    StoredCompanyCandidate,
)
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.observation import StoredObservation
from app.v2.domain.payload import RawPayload
from app.v2.domain.processing import ProcessingStatus
from app.v2.domain.processing_attempt import StoredProcessingAttempt
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import integrity_error_to_domain
from app.v2.repositories.errors import ConflictError, NotFoundError
from app.v2.repositories.observations import get_observation_by_id
from app.v2.repositories.processing_attempts import get_processing_attempt
from app.v2.repositories.raw_payloads import get_raw_payload


@dataclass(frozen=True)
class ProposalContext:
    """What a proposer may see: the immutable evidence, verified. Nothing writable."""

    attempt: StoredProcessingAttempt
    observation: StoredObservation
    payload: RawPayload


@dataclass(frozen=True)
class CandidatesStoreResult:
    candidates: tuple[StoredCompanyCandidate, ...]   # in candidate_ordinal order
    created: tuple[bool, ...]                        # aligned with candidates

    @property
    def created_count(self) -> int:
        return sum(self.created)


def _positive_id(value: object, what: str) -> None:
    if type(value) is not int or value < 1:
        raise InvalidInputError(f"invalid_{what}", f"{what.replace('_', ' ')} must be a positive integer")


# ---------------------------------------------------------------- context

def load_proposal_context(db: Engine | Connection, attempt_id: int) -> ProposalContext:
    """Resolve attempt -> observation -> verified payload. The attempt must be PROCESSING; it is locked
    FOR SHARE until the transaction ends, so it cannot become terminal while candidates are written."""
    _positive_id(attempt_id, "attempt_id")
    with _connection(db) as connection:
        locked = connection.execute(select(pa.c.id).where(pa.c.id == attempt_id).with_for_update(read=True)).scalar()
        if locked is None:
            raise NotFoundError("attempt_not_found", "no processing attempt exists with that id")
        attempt = get_processing_attempt(connection, attempt_id)
        if attempt.status is not ProcessingStatus.PROCESSING:
            raise InvariantViolationError(
                "attempt_not_processing", f"a {attempt.status.value} attempt cannot receive candidates and is never reopened"
            )
        observation = get_observation_by_id(connection, attempt.observation_id)
        payload = get_raw_payload(connection, observation.observation.content_hash, verify=True)
    return ProposalContext(attempt=attempt, observation=observation, payload=payload)


# ---------------------------------------------------------------- reads

def _load(connection: Connection, where) -> list[StoredCompanyCandidate]:
    rows = connection.execute(select(cc).where(where).order_by(cc.c.processing_attempt_id, cc.c.candidate_ordinal)).all()
    if not rows:
        return []
    identifiers: dict[int, list[ProposedIdentifier]] = {row.id: [] for row in rows}
    for r in connection.execute(select(ci).where(ci.c.candidate_id.in_(list(identifiers))).order_by(ci.c.candidate_id, ci.c.identifier_ordinal)):
        identifiers[r.candidate_id].append(ProposedIdentifier(
            identifier_type=IdentifierType(r.identifier_type), value=r.identifier_value,
            evidence=EvidenceLocator(byte_start=r.evidence_start, byte_end=r.evidence_end, evidence_hash=r.evidence_hash)))
    try:
        return [
            StoredCompanyCandidate(
                id=row.id, processing_attempt_id=row.processing_attempt_id, candidate_ordinal=row.candidate_ordinal,
                proposal=CompanyCandidateProposal(
                    proposed_name=row.proposed_name,
                    name_evidence=EvidenceLocator(byte_start=row.name_evidence_start, byte_end=row.name_evidence_end,
                                                  evidence_hash=row.name_evidence_hash),
                    identifiers=tuple(identifiers[row.id]),
                ),
                created_at=row.created_at,
            )
            for row in rows
        ]
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_candidate_invalid", "a stored candidate does not satisfy the domain model") from None


def get_company_candidate(db: Engine | Connection, candidate_id: int) -> StoredCompanyCandidate | None:
    _positive_id(candidate_id, "candidate_id")
    with _connection(db) as connection:
        found = _load(connection, cc.c.id == candidate_id)
    return found[0] if found else None


def list_company_candidates(db: Engine | Connection, attempt_id: int) -> list[StoredCompanyCandidate]:
    """The attempt's candidates in candidate_ordinal order."""
    _positive_id(attempt_id, "attempt_id")
    with _connection(db) as connection:
        return _load(connection, cc.c.processing_attempt_id == attempt_id)


def list_company_candidates_for_observation(db: Engine | Connection, observation_id: int) -> list[StoredCompanyCandidate]:
    """Every candidate any attempt proposed for the observation, ordered by (attempt id, ordinal): the history."""
    _positive_id(observation_id, "observation_id")
    with _connection(db) as connection:
        attempt_ids = select(pa.c.id).where(pa.c.observation_id == observation_id)
        return _load(connection, cc.c.processing_attempt_id.in_(attempt_ids))


# ---------------------------------------------------------------- writes

def _insert_identifiers(connection: Connection, candidate_id: int, proposal: CompanyCandidateProposal) -> None:
    if not proposal.identifiers:
        return
    connection.execute(insert(ci), [
        {"candidate_id": candidate_id, "identifier_ordinal": position, "identifier_type": ident.identifier_type.value,
         "identifier_value": ident.value, "evidence_start": ident.evidence.byte_start,
         "evidence_end": ident.evidence.byte_end, "evidence_hash": ident.evidence.evidence_hash}
        for position, ident in enumerate(proposal.identifiers, start=1)
    ])


def store_company_candidates(
    db: Engine | Connection, attempt_id: int, proposals: Sequence[CompanyCandidateProposal]
) -> CandidatesStoreResult:
    """Verify every proposal against the immutable evidence, then persist them all atomically (or none)."""
    proposals = tuple(proposals)
    if len(proposals) > MAX_CANDIDATES_PER_ATTEMPT:
        raise InvalidInputError("too_many_candidates", f"an attempt may propose at most {MAX_CANDIDATES_PER_ATTEMPT} candidates")
    for proposal in proposals:
        if not isinstance(proposal, CompanyCandidateProposal):
            raise InvalidInputError("not_a_proposal", "only CompanyCandidateProposal objects can be stored")

    with _connection(db) as connection:
        context = load_proposal_context(connection, attempt_id)
        for ordinal, proposal in enumerate(proposals, start=1):          # verify ALL before writing ANY
            verify_proposal(proposal, context.payload, context.observation.observation.sniffed_media_type, ordinal=ordinal)

        stored: list[StoredCompanyCandidate] = []
        created: list[bool] = []
        for ordinal, proposal in enumerate(proposals, start=1):
            try:
                inserted_id = connection.execute(
                    pg_insert(cc).values(
                        processing_attempt_id=attempt_id, candidate_ordinal=ordinal, proposed_name=proposal.proposed_name,
                        name_evidence_start=proposal.name_evidence.byte_start, name_evidence_end=proposal.name_evidence.byte_end,
                        name_evidence_hash=proposal.name_evidence.evidence_hash,
                        # created_at is deliberately absent: the database assigns it.
                    ).on_conflict_do_nothing(index_elements=[cc.c.processing_attempt_id, cc.c.candidate_ordinal]).returning(cc.c.id)
                ).scalar()
                if inserted_id is not None:
                    _insert_identifiers(connection, inserted_id, proposal)
            except IntegrityError as exc:
                raise integrity_error_to_domain(exc) from None

            if inserted_id is not None:
                stored.append(_load(connection, cc.c.id == inserted_id)[0])
                created.append(True)
                continue
            existing = _load(connection, (cc.c.processing_attempt_id == attempt_id) & (cc.c.candidate_ordinal == ordinal))[0]
            if existing.proposal != proposal:
                raise ConflictError("candidate_ordinal_conflict", f"candidate {ordinal} already exists with different content")
            stored.append(existing)
            created.append(False)
        return CandidatesStoreResult(candidates=tuple(stored), created=tuple(created))
