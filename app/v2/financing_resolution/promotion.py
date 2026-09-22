"""
The explicit financing-resolution boundary. Four operations, no generic "execute action":

    create_event_from_candidate   human only   decision + FinancingEvent + selected accepted facts, atomically
    attach_candidate_to_event     human, or a registered financing rule (none is registered: FINANCING_RULE_AUTHORITY is empty)
    reject_candidate              human only   reason code required
    defer_candidate                human only   reason code required (not final)

Every operation takes an Authority (AI cannot be constructed) and is re-checked here. The candidate must be
unresolved, and (for attach) must concern the SAME Company as the target event -- WrongCompanyError otherwise, never
a merge. Each operation is ONE transaction (a SAVEPOINT when the caller passes a Connection): a failure leaves no
half-created event and no half-accepted fact. The candidate, its evidence and its attempt are never modified.

FACT SELECTION: a FactSelection names exactly which of the resolved candidate's already-proposed facts become
canonical. Nothing is copied implicitly: create_event/attach_to_event with FactSelection() (the default) accepts NO
facts, only the event's existence. Selecting a fact the candidate never proposed is FactNotAvailableError. Selecting
a fact the event already holds is FactAlreadyAcceptedError (canonical facts are never overwritten; that is a future,
separate correction mechanism). verified_round_amount may be selected only when it comes from the candidate's
ANNOUNCED_ROUND_AMOUNT and only under HUMAN authority -- offering_amount and amount_sold can never become it.
"""

from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.financing import AmountSemantics
from app.v2.domain.financing_resolution import (
    FINAL_FINANCING_DECISION_KINDS,
    NO_FACTS,
    Authority,
    AuthorityKind,
    FactSelection,
    FinancingDecisionKind,
    StoredFinancingResolutionDecision,
    may_decide,
)
from app.v2.domain.processing_attempt import validate_reason_code
from app.v2.repositories._db import atomic, constraint_of, integrity_error_to_domain
from app.v2.repositories.errors import NotFoundError
from app.v2.repositories.financing_events import (
    get_candidate_amount_row,
    get_candidate_date_row,
    get_financing_event,
    get_financing_resolution_decision,
    list_decisions_for_financing_candidate,
    lock_financing_candidate_for_resolution,
)
from app.v2.financing_resolution import _writes
from app.v2.financing_resolution.errors import (
    FactAlreadyAcceptedError,
    FactNotAvailableError,
    FinancingCandidateAlreadyResolvedError,
    WrongCompanyError,
)


@dataclass(frozen=True)
class FinancingPromotionResult:
    decision: StoredFinancingResolutionDecision
    financing_event_id: UUID | None
    accepted_stage: bool = False
    accepted_financing_type: bool = False
    accepted_verified_round_amount: bool = False
    accepted_dates: tuple = ()


def _checked_authority(authority: object, kind: FinancingDecisionKind) -> Authority:
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
    if name == "uq_frd_one_final":
        return FinancingCandidateAlreadyResolvedError("candidate_already_resolved", "the candidate already has a final resolution")
    if name in ("uq_fes_one_per_event", "uq_fet_one_per_event", "uq_fev_one_per_event", "uq_fed_kind_per_event"):
        return FactAlreadyAcceptedError("fact_already_accepted", "the event already holds a canonical value for this fact")
    if name in ("uq_fev_candidate_amount", "uq_fed_candidate_date"):
        return FactAlreadyAcceptedError("fact_already_used", "this candidate fact was already accepted onto a financing event")
    return integrity_error_to_domain(exc)


def _open_candidate(connection: Connection, candidate_id: int):
    """Lock the candidate, require it unresolved, and return (company_id, stage, financing_type)."""
    if isinstance(candidate_id, bool) or not isinstance(candidate_id, int) or candidate_id <= 0:
        raise InvalidInputError("invalid_candidate_id", "candidate_id must be a positive integer")
    core = lock_financing_candidate_for_resolution(connection, candidate_id)
    if core is None:
        raise NotFoundError("candidate_not_found", "no such financing candidate")
    if any(d.decision_kind in FINAL_FINANCING_DECISION_KINDS for d in list_decisions_for_financing_candidate(connection, candidate_id)):
        raise FinancingCandidateAlreadyResolvedError("candidate_already_resolved", "the candidate already has a final resolution")
    return core


def _apply_facts(connection: Connection, *, event_id: UUID, candidate_id: int, stage, financing_type, decision_id: int,
                 authority: Authority, facts: FactSelection) -> FinancingPromotionResult:
    if not isinstance(facts, FactSelection):
        raise InvalidInputError("invalid_fact_selection", "facts must be a FactSelection")
    from app.v2.domain.financing import Stage as StageEnum
    from app.v2.domain.financing import FinancingType as TypeEnum

    accepted_stage = accepted_type = accepted_amount = False
    accepted_dates: list = []

    if facts.stage:
        if stage is StageEnum.UNKNOWN:
            raise FactNotAvailableError("stage_not_proposed", "the resolved candidate proposed no stage")
        _writes.insert_stage(connection, financing_event_id=event_id, stage=stage, decision_id=decision_id, candidate_id=candidate_id)
        accepted_stage = True

    if facts.financing_type:
        if financing_type is TypeEnum.UNKNOWN:
            raise FactNotAvailableError("financing_type_not_proposed", "the resolved candidate proposed no financing type")
        _writes.insert_type(connection, financing_event_id=event_id, financing_type=financing_type, decision_id=decision_id, candidate_id=candidate_id)
        accepted_type = True

    if facts.verified_round_amount:
        if authority.kind is not AuthorityKind.HUMAN:
            raise InvariantViolationError("verified_round_amount_requires_human", "only a human may establish a verified round amount")
        found = get_candidate_amount_row(connection, candidate_id, AmountSemantics.ANNOUNCED_ROUND_AMOUNT)
        if found is None:
            raise FactNotAvailableError("verified_round_amount_not_proposed", "the resolved candidate proposed no announced round amount")
        candidate_amount_id, money = found
        _writes.insert_verified_round_amount(connection, financing_event_id=event_id, money=money, decision_id=decision_id, candidate_amount_id=candidate_amount_id)
        accepted_amount = True

    for kind in facts.dates:
        found = get_candidate_date_row(connection, candidate_id, kind)
        if found is None:
            raise FactNotAvailableError("date_not_proposed", "the resolved candidate proposed no date of this kind")
        candidate_date_id, time = found
        _writes.insert_date(connection, financing_event_id=event_id, kind=kind, time=time, decision_id=decision_id, candidate_date_id=candidate_date_id)
        accepted_dates.append(kind)

    return FinancingPromotionResult(decision=None, financing_event_id=event_id, accepted_stage=accepted_stage,
                                    accepted_financing_type=accepted_type, accepted_verified_round_amount=accepted_amount,
                                    accepted_dates=tuple(accepted_dates))


def create_event_from_candidate(db: Engine | Connection, candidate_id: int, authority: Authority, facts: FactSelection = NO_FACTS) -> FinancingPromotionResult:
    """A human resolves the candidate as a NEW canonical FinancingEvent of ITS Company: one decision, the event, and
    exactly the selected accepted facts, all or nothing."""
    authority = _checked_authority(authority, FinancingDecisionKind.CREATE_EVENT)
    try:
        with atomic(db) as connection:
            company_id, stage, financing_type = _open_candidate(connection, candidate_id)
            event_id = _writes.insert_event(connection, company_id=company_id)
            decision_id = _writes.insert_decision(connection, candidate_id=candidate_id, kind=FinancingDecisionKind.CREATE_EVENT,
                                                  authority=authority, financing_event_id=event_id, reason_code=None)
            result = _apply_facts(connection, event_id=event_id, candidate_id=candidate_id, stage=stage, financing_type=financing_type,
                                  decision_id=decision_id, authority=authority, facts=facts)
            stored = get_financing_resolution_decision(connection, decision_id)
    except IntegrityError as exc:
        raise _translate(exc) from None
    return FinancingPromotionResult(decision=stored, financing_event_id=event_id, accepted_stage=result.accepted_stage,
                                    accepted_financing_type=result.accepted_financing_type,
                                    accepted_verified_round_amount=result.accepted_verified_round_amount, accepted_dates=result.accepted_dates)


def attach_candidate_to_event(db: Engine | Connection, candidate_id: int, event_id: UUID, authority: Authority,
                              facts: FactSelection = NO_FACTS) -> FinancingPromotionResult:
    """The candidate describes an EXISTING event of the SAME Company. Never a merge: attaching cannot create a new
    event, and a candidate for a different Company is refused (WrongCompanyError), in Python and by the database."""
    authority = _checked_authority(authority, FinancingDecisionKind.ATTACH_TO_EVENT)
    try:
        with atomic(db) as connection:
            company_id, stage, financing_type = _open_candidate(connection, candidate_id)
            event = get_financing_event(connection, event_id)
            if event is None:
                raise NotFoundError("financing_event_not_found", "no such financing event")
            if event.company_id != company_id:
                raise WrongCompanyError("wrong_company", "the candidate concerns a different company than the target event")
            decision_id = _writes.insert_decision(connection, candidate_id=candidate_id, kind=FinancingDecisionKind.ATTACH_TO_EVENT,
                                                  authority=authority, financing_event_id=event_id, reason_code=None)
            result = _apply_facts(connection, event_id=event_id, candidate_id=candidate_id, stage=stage, financing_type=financing_type,
                                  decision_id=decision_id, authority=authority, facts=facts)
            stored = get_financing_resolution_decision(connection, decision_id)
    except IntegrityError as exc:
        raise _translate(exc) from None
    return FinancingPromotionResult(decision=stored, financing_event_id=event_id, accepted_stage=result.accepted_stage,
                                    accepted_financing_type=result.accepted_financing_type,
                                    accepted_verified_round_amount=result.accepted_verified_round_amount, accepted_dates=result.accepted_dates)


def _record_without_event(db: Engine | Connection, candidate_id: int, authority: Authority, kind: FinancingDecisionKind, reason_code: str) -> FinancingPromotionResult:
    authority = _checked_authority(authority, kind)
    validate_reason_code(reason_code)
    try:
        with atomic(db) as connection:
            _open_candidate(connection, candidate_id)
            decision_id = _writes.insert_decision(connection, candidate_id=candidate_id, kind=kind, authority=authority,
                                                  financing_event_id=None, reason_code=reason_code)
            stored = get_financing_resolution_decision(connection, decision_id)
    except IntegrityError as exc:
        raise _translate(exc) from None
    return FinancingPromotionResult(decision=stored, financing_event_id=None)


def reject_candidate(db: Engine | Connection, candidate_id: int, authority: Authority, reason_code: str) -> FinancingPromotionResult:
    return _record_without_event(db, candidate_id, authority, FinancingDecisionKind.REJECT_CANDIDATE, reason_code)


def defer_candidate(db: Engine | Connection, candidate_id: int, authority: Authority, reason_code: str) -> FinancingPromotionResult:
    """Recorded for the audit trail; not final, so a later decision may still resolve the candidate."""
    return _record_without_event(db, candidate_id, authority, FinancingDecisionKind.DEFER_CANDIDATE, reason_code)
