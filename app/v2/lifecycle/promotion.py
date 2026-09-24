"""
The explicit lifecycle-resolution boundary. Three operations, no generic "execute action":

    accept_lifecycle_event   human only   decision + exactly the selected accepted facts, atomically
    reject_candidate         human only   reason code required
    defer_candidate          human only   reason code required (not final)

Every operation takes an Authority (AI cannot be constructed) and is re-checked here. Each operation is ONE
transaction (a SAVEPOINT when the caller passes a Connection): a failure leaves no half-accepted fact. The
candidate, its evidence and its attempt are never modified.

There is no create/attach split (unlike financing): a lifecycle candidate always annotates an ALREADY-canonical
Company directly, so there is no separate "event" identity to create or attach to.

FACT SELECTION: a LifecycleFactSelection names exactly which of the resolved candidate's already-proposed
facts become canonical. Nothing is copied implicitly: accept_lifecycle_event with NO_LIFECYCLE_FACTS (the
default) accepts NO facts, only records that the candidate was reviewed and accepted. Selecting a fact the
candidate never proposed is FactNotAvailableError. Accepting one fact kind never implies another: accepting an
acquisition does not also write an operating_status fact, even if both were proposed on the same candidate.

CORRECTIONS: accepted facts are append-only (the database forbids UPDATE/DELETE on all four canonical fact
tables). There is no "amend an accepted fact" operation here -- a correction is a brand-new candidate, reviewed
and accepted through this same boundary, producing a NEW row with a later created_at. "Current" is always
derived by the reader (CompanyLifecycleState.current_legal_name / current_operating_status), never rewritten.

CAPITAL METRICS: accepting any lifecycle fact here has NO effect on v2.financing_event, v2.company_market_
classification, or the capital-metrics/capital-signal read paths -- none of those modules import this package,
and this package never writes their tables. That isolation is enforced by the architecture boundary tests.
"""

from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.lifecycle_resolution import (
    FINAL_LIFECYCLE_DECISION_KINDS,
    NO_LIFECYCLE_FACTS,
    Authority,
    LifecycleDecisionKind,
    LifecycleFactSelection,
    StoredLifecycleResolutionDecision,
    may_decide,
)
from app.v2.domain.processing_attempt import validate_reason_code
from app.v2.repositories._db import atomic, constraint_of, integrity_error_to_domain
from app.v2.repositories.company_lifecycle import (
    get_candidate_acquisition_row,
    get_candidate_name_change_row,
    get_candidate_operating_status_row,
    get_candidate_successor_row,
    get_lifecycle_resolution_decision,
    list_decisions_for_lifecycle_candidate,
    lock_lifecycle_candidate_for_resolution,
)
from app.v2.repositories.errors import NotFoundError
from app.v2.lifecycle import _writes
from app.v2.lifecycle.errors import FactAlreadyAcceptedError, FactNotAvailableError, LifecycleCandidateAlreadyResolvedError


@dataclass(frozen=True)
class LifecyclePromotionResult:
    decision: StoredLifecycleResolutionDecision
    company_id: UUID | None
    accepted_name_change: bool = False
    accepted_operating_status: bool = False
    accepted_acquisition: bool = False
    accepted_successor: bool = False


def _checked_authority(authority: object, kind: LifecycleDecisionKind) -> Authority:
    if not isinstance(authority, Authority):
        raise InvalidInputError("invalid_authority", "authority must be an Authority (rule or human)")
    try:
        verified = Authority(kind=authority.kind, id=authority.id)
    except ValidationError:
        raise InvalidInputError("invalid_authority", "authority must be an Authority (rule or human)") from None
    if not may_decide(verified, kind):
        raise InvariantViolationError("authority_exceeded", "the authority may not make this kind of decision")
    return verified


def _translate(exc: IntegrityError) -> Exception:
    name = constraint_of(exc)
    if name == "uq_lrd_one_final":
        return LifecycleCandidateAlreadyResolvedError("candidate_already_resolved", "the candidate already has a final resolution")
    if name in ("uq_cnh_candidate", "uq_cos_candidate", "uq_ca_candidate", "uq_csr_candidate",
                "uq_cnh_resolution_decision", "uq_cos_resolution_decision", "uq_ca_resolution_decision", "uq_csr_resolution_decision"):
        return FactAlreadyAcceptedError("fact_already_accepted", "this candidate fact was already accepted onto the company")
    return integrity_error_to_domain(exc)


def _open_candidate(connection: Connection, candidate_id: int) -> UUID:
    """Lock the candidate, require it unresolved, and return its company_id."""
    if isinstance(candidate_id, bool) or not isinstance(candidate_id, int) or candidate_id <= 0:
        raise InvalidInputError("invalid_candidate_id", "candidate_id must be a positive integer")
    company_id = lock_lifecycle_candidate_for_resolution(connection, candidate_id)
    if company_id is None:
        raise NotFoundError("candidate_not_found", "no such lifecycle candidate")
    if any(d.decision_kind in FINAL_LIFECYCLE_DECISION_KINDS for d in list_decisions_for_lifecycle_candidate(connection, candidate_id)):
        raise LifecycleCandidateAlreadyResolvedError("candidate_already_resolved", "the candidate already has a final resolution")
    return company_id


def _apply_facts(connection: Connection, *, company_id: UUID, candidate_id: int, decision_id: int, facts: LifecycleFactSelection) -> LifecyclePromotionResult:
    if not isinstance(facts, LifecycleFactSelection):
        raise InvalidInputError("invalid_fact_selection", "facts must be a LifecycleFactSelection")

    accepted_name = accepted_status = accepted_acq = accepted_succ = False

    if facts.name_change:
        found = get_candidate_name_change_row(connection, candidate_id)
        if found is None:
            raise FactNotAvailableError("name_change_not_proposed", "the resolved candidate proposed no name change")
        new_name, effective = found
        _writes.insert_name_change(connection, company_id=company_id, new_name=new_name, effective=effective, decision_id=decision_id, candidate_id=candidate_id)
        accepted_name = True

    if facts.operating_status:
        found = get_candidate_operating_status_row(connection, candidate_id)
        if found is None:
            raise FactNotAvailableError("operating_status_not_proposed", "the resolved candidate proposed no operating status")
        status, as_of = found
        _writes.insert_operating_status(connection, company_id=company_id, status=status, as_of=as_of, decision_id=decision_id, candidate_id=candidate_id)
        accepted_status = True

    if facts.acquisition:
        found = get_candidate_acquisition_row(connection, candidate_id)
        if found is None:
            raise FactNotAvailableError("acquisition_not_proposed", "the resolved candidate proposed no acquisition")
        acquirer_name, acquirer_company_id, transaction_date = found
        _writes.insert_acquisition(connection, company_id=company_id, acquirer_name=acquirer_name, acquirer_company_id=acquirer_company_id,
                                   transaction_date=transaction_date, decision_id=decision_id, candidate_id=candidate_id)
        accepted_acq = True

    if facts.successor:
        found = get_candidate_successor_row(connection, candidate_id)
        if found is None:
            raise FactNotAvailableError("successor_not_proposed", "the resolved candidate proposed no successor relationship")
        related_entity_name, related_company_id, relationship_kind = found
        _writes.insert_successor(connection, company_id=company_id, related_entity_name=related_entity_name, related_company_id=related_company_id,
                                 relationship_kind=relationship_kind, decision_id=decision_id, candidate_id=candidate_id)
        accepted_succ = True

    return LifecyclePromotionResult(decision=None, company_id=company_id, accepted_name_change=accepted_name,
                                    accepted_operating_status=accepted_status, accepted_acquisition=accepted_acq, accepted_successor=accepted_succ)


def accept_lifecycle_event(db: Engine | Connection, candidate_id: int, authority: Authority, facts: LifecycleFactSelection = NO_LIFECYCLE_FACTS) -> LifecyclePromotionResult:
    """A human accepts the candidate: one decision, plus exactly the selected proposed facts, all or nothing."""
    authority = _checked_authority(authority, LifecycleDecisionKind.ACCEPT_LIFECYCLE_EVENT)
    try:
        with atomic(db) as connection:
            company_id = _open_candidate(connection, candidate_id)
            decision_id = _writes.insert_decision(connection, candidate_id=candidate_id, kind=LifecycleDecisionKind.ACCEPT_LIFECYCLE_EVENT,
                                                  authority=authority, reason_code=None)
            result = _apply_facts(connection, company_id=company_id, candidate_id=candidate_id, decision_id=decision_id, facts=facts)
            stored = get_lifecycle_resolution_decision(connection, decision_id)
    except IntegrityError as exc:
        raise _translate(exc) from None
    return LifecyclePromotionResult(decision=stored, company_id=company_id, accepted_name_change=result.accepted_name_change,
                                    accepted_operating_status=result.accepted_operating_status, accepted_acquisition=result.accepted_acquisition,
                                    accepted_successor=result.accepted_successor)


def _record_without_facts(db: Engine | Connection, candidate_id: int, authority: Authority, kind: LifecycleDecisionKind, reason_code: str) -> LifecyclePromotionResult:
    authority = _checked_authority(authority, kind)
    validate_reason_code(reason_code)
    try:
        with atomic(db) as connection:
            _open_candidate(connection, candidate_id)
            decision_id = _writes.insert_decision(connection, candidate_id=candidate_id, kind=kind, authority=authority, reason_code=reason_code)
            stored = get_lifecycle_resolution_decision(connection, decision_id)
    except IntegrityError as exc:
        raise _translate(exc) from None
    return LifecyclePromotionResult(decision=stored, company_id=None)


def reject_candidate(db: Engine | Connection, candidate_id: int, authority: Authority, reason_code: str) -> LifecyclePromotionResult:
    return _record_without_facts(db, candidate_id, authority, LifecycleDecisionKind.REJECT_CANDIDATE, reason_code)


def defer_candidate(db: Engine | Connection, candidate_id: int, authority: Authority, reason_code: str) -> LifecyclePromotionResult:
    """Recorded for the audit trail; not final, so a later decision may still resolve the candidate."""
    return _record_without_facts(db, candidate_id, authority, LifecycleDecisionKind.DEFER_CANDIDATE, reason_code)
