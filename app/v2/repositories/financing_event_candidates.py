"""
Financing-event candidate persistence: immutable records of what a processing attempt PROPOSED about a
startup financing. A stored candidate is still UNTRUSTED: nothing here creates canonical state (there is no
canonical financing_event table), and this module writes ONLY the three financing-candidate tables. Attempts,
observations, payloads and companies are read-only here.

    persist_financing_event_candidates(db, attempt_id, proposals) -> FinancingCandidatesStoreResult
    get_financing_event_candidate(db, candidate_id)
    list_financing_event_candidates(db, attempt_id)
    list_financing_event_candidates_for_company(db, company_id)
    list_financing_event_candidates_for_observation(db, observation_id)

Persistence rules, all verified BEFORE any write and re-checked by database triggers:
  1. the attempt must exist and be PROCESSING (row-locked FOR SHARE so it cannot finish underneath the write);
     a terminal attempt never receives candidates and is never reopened or otherwise modified;
  2. its Observation and verified RawPayload are loaded;
  3. every proposal's Company must already exist (FOR KEY SHARE); this module never creates Companies, and a
     company is identified only by its canonical id, never by a name, domain or URL;
  4. every locator (event, stage, type, each amount, each date) is verified against the exact payload bytes
     (app.v2.candidates.financing_evidence): media type, bounds, sha256 of the exact span, fact-kind consistency;
  5. the whole batch is atomic: one invalid proposal or fact rejects all of them (SAVEPOINT on a Connection).

Identity is (processing_attempt_id, candidate_ordinal), the 1-based position in the batch. That is only stable
while proposers are deterministic and must be revisited when a probabilistic proposer exists. Replaying an
identical batch returns the stored candidates with created=False; a DIFFERENT proposal at an existing ordinal is a
ConflictError. Conflicting candidates from different observations are stored side by side: nothing is merged.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.candidates.financing_evidence import verify_financing_proposal
from app.v2.db.tables import company_table
from app.v2.db.tables import financing_event_candidate_amount_table as fa
from app.v2.db.tables import financing_event_candidate_date_table as fd
from app.v2.db.tables import financing_event_candidate_table as fc
from app.v2.db.tables import processing_attempt_table as pa
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError
from app.v2.domain.financing import (
    MAX_FINANCING_CANDIDATES_PER_ATTEMPT,
    AmountSemantics,
    FinancingDateKind,
    FinancingEventCandidateProposal,
    FinancingType,
    Money,
    ProposedAmount,
    ProposedFinancingDate,
    ProposedFinancingType,
    ProposedStage,
    Stage,
    StoredFinancingEventCandidate,
)
from app.v2.domain.time import EventTime, EventTimePrecision
from app.v2.repositories._db import connection as _connection
from app.v2.repositories._db import integrity_error_to_domain
from app.v2.repositories.company_candidates import load_proposal_context
from app.v2.repositories.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class FinancingCandidatesStoreResult:
    candidates: tuple[StoredFinancingEventCandidate, ...]   # in candidate_ordinal order
    created: tuple[bool, ...]                               # aligned with candidates

    @property
    def created_count(self) -> int:
        return sum(self.created)


def _locator(start, end, digest) -> EvidenceLocator:
    return EvidenceLocator(byte_start=start, byte_end=end, evidence_hash=digest)


# ---------------------------------------------------------------- reads

def _load(connection: Connection, where) -> list[StoredFinancingEventCandidate]:
    rows = connection.execute(select(fc).where(where).order_by(fc.c.processing_attempt_id, fc.c.candidate_ordinal)).all()
    if not rows:
        return []
    ids = [row.id for row in rows]
    amounts: dict[int, list[ProposedAmount]] = {i: [] for i in ids}
    dates: dict[int, list[ProposedFinancingDate]] = {i: [] for i in ids}
    for r in connection.execute(select(fa).where(fa.c.candidate_id.in_(ids)).order_by(fa.c.candidate_id, fa.c.id)):
        amounts[r.candidate_id].append(ProposedAmount(
            semantics=AmountSemantics(r.amount_semantics), money=Money(currency_code=r.currency_code, minor_units=r.amount_minor_units),
            evidence=_locator(r.evidence_start, r.evidence_end, r.evidence_hash)))
    for r in connection.execute(select(fd).where(fd.c.candidate_id.in_(ids)).order_by(fd.c.candidate_id, fd.c.id)):
        dates[r.candidate_id].append(ProposedFinancingDate(
            kind=FinancingDateKind(r.date_kind), time=EventTime(precision=EventTimePrecision(r.date_precision), start=r.date_start),
            evidence=_locator(r.evidence_start, r.evidence_end, r.evidence_hash)))
    try:
        return [
            StoredFinancingEventCandidate(
                id=row.id, processing_attempt_id=row.processing_attempt_id, candidate_ordinal=row.candidate_ordinal,
                proposal=FinancingEventCandidateProposal(
                    company_id=row.company_id,
                    event_evidence=_locator(row.event_evidence_start, row.event_evidence_end, row.event_evidence_hash),
                    stage=None if row.stage == Stage.UNKNOWN.value else ProposedStage(
                        stage=Stage(row.stage), evidence=_locator(row.stage_evidence_start, row.stage_evidence_end, row.stage_evidence_hash)),
                    financing_type=None if row.financing_type == FinancingType.UNKNOWN.value else ProposedFinancingType(
                        financing_type=FinancingType(row.financing_type),
                        evidence=_locator(row.type_evidence_start, row.type_evidence_end, row.type_evidence_hash)),
                    amounts=tuple(amounts[row.id]), dates=tuple(dates[row.id]),
                ),
                created_at=row.created_at,
            )
            for row in rows
        ]
    except (DomainError, ValueError):
        raise InvariantViolationError("stored_candidate_invalid", "a stored financing candidate does not satisfy the domain model") from None


def get_financing_event_candidate(db: Engine | Connection, candidate_id: int) -> StoredFinancingEventCandidate | None:
    with _connection(db) as connection:
        found = _load(connection, fc.c.id == candidate_id)
    return found[0] if found else None


def list_financing_event_candidates(db: Engine | Connection, attempt_id: int) -> list[StoredFinancingEventCandidate]:
    with _connection(db) as connection:
        return _load(connection, fc.c.processing_attempt_id == attempt_id)


def list_financing_event_candidates_for_company(db: Engine | Connection, company_id: UUID) -> list[StoredFinancingEventCandidate]:
    """Every candidate proposed about the company by any attempt: unresolved proposals, possibly conflicting."""
    with _connection(db) as connection:
        return _load(connection, fc.c.company_id == company_id)


def list_financing_event_candidates_for_observation(db: Engine | Connection, observation_id: int) -> list[StoredFinancingEventCandidate]:
    with _connection(db) as connection:
        attempt_ids = select(pa.c.id).where(pa.c.observation_id == observation_id)
        return _load(connection, fc.c.processing_attempt_id.in_(attempt_ids))


# ---------------------------------------------------------------- writes

def _insert_children(connection: Connection, candidate_id: int, proposal: FinancingEventCandidateProposal) -> None:
    if proposal.amounts:
        connection.execute(insert(fa), [
            {"candidate_id": candidate_id, "amount_semantics": a.semantics.value, "currency_code": a.money.currency_code,
             "amount_minor_units": a.money.minor_units, "evidence_start": a.evidence.byte_start,
             "evidence_end": a.evidence.byte_end, "evidence_hash": a.evidence.evidence_hash}
            for a in proposal.amounts])
    if proposal.dates:
        connection.execute(insert(fd), [
            {"candidate_id": candidate_id, "date_kind": d.kind.value, "date_precision": d.time.precision.value,
             "date_start": d.time.start, "evidence_start": d.evidence.byte_start, "evidence_end": d.evidence.byte_end,
             "evidence_hash": d.evidence.evidence_hash}
            for d in proposal.dates])


def persist_financing_event_candidates(
    db: Engine | Connection, attempt_id: int, proposals: Sequence[FinancingEventCandidateProposal]
) -> FinancingCandidatesStoreResult:
    """Verify every proposal against the immutable evidence, then persist them all atomically (or none)."""
    proposals = tuple(proposals)
    if len(proposals) > MAX_FINANCING_CANDIDATES_PER_ATTEMPT:
        raise InvalidInputError("too_many_candidates", f"an attempt may propose at most {MAX_FINANCING_CANDIDATES_PER_ATTEMPT} financing candidates")
    for proposal in proposals:
        if not isinstance(proposal, FinancingEventCandidateProposal):
            raise InvalidInputError("not_a_proposal", "only FinancingEventCandidateProposal objects can be stored")

    with _connection(db) as connection:
        context = load_proposal_context(connection, attempt_id)
        media_type = context.observation.observation.sniffed_media_type
        for ordinal, proposal in enumerate(proposals, start=1):          # verify ALL before writing ANY
            verify_financing_proposal(proposal, context.payload, media_type, ordinal=ordinal)
            exists = connection.execute(select(company_table.c.id).where(company_table.c.id == proposal.company_id)
                                        .with_for_update(read=True, key_share=True)).first()
            if exists is None:
                raise NotFoundError("company_not_found", f"financing candidate {ordinal}: the company does not exist canonically")

        stored: list[StoredFinancingEventCandidate] = []
        created: list[bool] = []
        for ordinal, proposal in enumerate(proposals, start=1):
            stage, ftype = proposal.stage, proposal.financing_type
            try:
                inserted_id = connection.execute(
                    pg_insert(fc).values(
                        processing_attempt_id=attempt_id, company_id=proposal.company_id, candidate_ordinal=ordinal,
                        event_evidence_start=proposal.event_evidence.byte_start, event_evidence_end=proposal.event_evidence.byte_end,
                        event_evidence_hash=proposal.event_evidence.evidence_hash,
                        stage=proposal.stage_value.value,
                        stage_evidence_start=stage.evidence.byte_start if stage else None,
                        stage_evidence_end=stage.evidence.byte_end if stage else None,
                        stage_evidence_hash=stage.evidence.evidence_hash if stage else None,
                        financing_type=proposal.financing_type_value.value,
                        type_evidence_start=ftype.evidence.byte_start if ftype else None,
                        type_evidence_end=ftype.evidence.byte_end if ftype else None,
                        type_evidence_hash=ftype.evidence.evidence_hash if ftype else None,
                        # created_at is deliberately absent: the database assigns it.
                    ).on_conflict_do_nothing(index_elements=[fc.c.processing_attempt_id, fc.c.candidate_ordinal]).returning(fc.c.id)
                ).scalar()
                if inserted_id is not None:
                    _insert_children(connection, inserted_id, proposal)
            except IntegrityError as exc:
                raise integrity_error_to_domain(exc) from None

            if inserted_id is not None:
                stored.append(_load(connection, fc.c.id == inserted_id)[0])
                created.append(True)
                continue
            existing = _load(connection, (fc.c.processing_attempt_id == attempt_id) & (fc.c.candidate_ordinal == ordinal))[0]
            if _canonical_form(existing.proposal) != _canonical_form(proposal):
                raise ConflictError("candidate_ordinal_conflict", f"financing candidate {ordinal} already exists with different content")
            stored.append(existing)
            created.append(False)
        return FinancingCandidatesStoreResult(candidates=tuple(stored), created=tuple(created))


def _canonical_form(proposal: FinancingEventCandidateProposal) -> FinancingEventCandidateProposal:
    """Amounts and dates are a set keyed by semantics/kind; compare independent of the order they were listed in."""
    return proposal.model_copy(update={
        "amounts": tuple(sorted(proposal.amounts, key=lambda a: a.semantics.value)),
        "dates": tuple(sorted(proposal.dates, key=lambda d: d.kind.value)),
    })
