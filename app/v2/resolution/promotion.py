"""
The explicit promotion boundary. Four operations, no generic "execute action":

    create_company_from_candidate   human only   decision + Company + canonical name + identifiers, atomically
    attach_candidate_to_company     human, or the exact-identifier rule (rules.py)
    reject_candidate                human only   reason code required
    defer_candidate                 human only   reason code required (not final)

Every operation takes an Authority (rule or human; AI cannot be constructed) and is re-checked
here: the authority is re-validated, must be permitted to make this kind of decision, and the
candidate must be unresolved. Nothing accepts or looks at a confidence. Each operation is ONE
transaction (a SAVEPOINT when the caller passes a Connection): a failure leaves no half-promoted
Company. The candidate, its attempt and all evidence are never modified. The database re-verifies
everything (see migration 0007), including under concurrency: candidate rows are locked so decisions
on one candidate serialise, and the unique indexes are the final authority.

Exactly two modules may import this one (enforced by app/v2/tests/architecture/test_resolution_boundaries.py):
app.v2.resolution.rules (the deterministic-rule-authority front door) and, since Increment 18.2.1,
app.v2.resolution.human_review (the human-authority front door -- for operational callers such as a local,
human-confirmed CLI). Neither adds logic beyond selecting which authority they act under; nothing else should
import this module directly, including future application/tooling code -- add a caller to human_review.py, or
propose a third, equally narrow and reviewed module, rather than importing promotion.py from anywhere broader.
"""

from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.v2.db.tables import company_candidate_table as cc
from app.v2.db.tables import company_identifier_table as company_identifier
from app.v2.db.tables import company_name_table as company_name
from app.v2.db.tables import company_table as company
from app.v2.domain.candidate import IdentifierType
from app.v2.domain.company import CompanyNameRole, normalize_identifier
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.processing_attempt import validate_reason_code
from app.v2.domain.resolution import (
    FINAL_DECISION_KINDS,
    Authority,
    AuthorityKind,
    DecisionKind,
    StoredResolutionDecision,
)
from app.v2.repositories._db import atomic, constraint_of, integrity_error_to_domain
from app.v2.repositories.companies import (
    get_resolution_decision,
    list_candidate_identifier_rows,
    list_decisions_for_candidate,
    lock_candidate_for_resolution,
)
from app.v2.repositories.errors import NotFoundError
from app.v2.resolution import _writes
from app.v2.resolution.errors import CandidateAlreadyResolvedError, IdentifierConflictError


@dataclass(frozen=True)
class PromotionResult:
    decision: StoredResolutionDecision
    company_id: UUID | None
    accepted_name: bool = False
    accepted_identifier_count: int = 0


def _checked_authority(authority: object, kind: DecisionKind) -> Authority:
    """Re-validate (a model_construct()ed or duck-typed 'authority' does not pass) and check the permission."""
    if not isinstance(authority, Authority):
        raise InvalidInputError("invalid_authority", "authority must be an Authority (rule or human)")
    try:
        verified = Authority(kind=authority.kind, id=authority.id)
    except ValidationError:
        raise InvalidInputError("invalid_authority", "authority must be an Authority (rule or human)") from None
    if not verified.may_decide(kind):
        raise InvariantViolationError("authority_exceeded", "the authority may not make this kind of decision")
    return verified


def _translate(exc: IntegrityError) -> Exception:
    name = constraint_of(exc)
    if name == "uq_resolution_decision_one_final":
        return CandidateAlreadyResolvedError("candidate_already_resolved", "the candidate already has a final resolution")
    if name == "uq_company_identifier_value":
        return IdentifierConflictError("identifier_conflict", "an identifier already belongs to a different company")
    return integrity_error_to_domain(exc)


def _open_candidate(connection: Connection, candidate_id: int) -> str:
    """Lock the candidate, require it to be unresolved and return its proposed name."""
    if isinstance(candidate_id, bool) or not isinstance(candidate_id, int) or candidate_id <= 0:
        raise InvalidInputError("invalid_candidate_id", "candidate_id must be a positive integer")
    if not lock_candidate_for_resolution(connection, candidate_id):
        raise NotFoundError("candidate_not_found", "no such candidate")
    if any(d.decision_kind in FINAL_DECISION_KINDS for d in list_decisions_for_candidate(connection, candidate_id)):
        raise CandidateAlreadyResolvedError("candidate_already_resolved", "the candidate already has a final resolution")
    return connection.execute(select(cc.c.proposed_name).where(cc.c.id == candidate_id)).scalar_one()


def create_company_from_candidate(db: Engine | Connection, candidate_id: int, authority: Authority) -> PromotionResult:
    """A human resolves the candidate as a NEW canonical Company: one decision, the Company, its canonical
    name (the candidate's proposed name) and the candidate's identifiers, all or nothing."""
    authority = _checked_authority(authority, DecisionKind.CREATE_COMPANY)
    try:
        with atomic(db) as connection:
            name = _open_candidate(connection, candidate_id)
            identifiers = list_candidate_identifier_rows(connection, candidate_id)
            company_id = _writes.insert_company(connection)
            decision_id = _writes.insert_decision(connection, candidate_id=candidate_id, kind=DecisionKind.CREATE_COMPANY,
                                                  authority=authority, company_id=company_id, reason_code=None)
            _writes.insert_name(connection, company_id=company_id, name=name, candidate_id=candidate_id,
                                role=CompanyNameRole.CANONICAL, decision_id=decision_id)
            for identifier_id, identifier_type, value in identifiers:
                _writes.insert_identifier(connection, company_id=company_id, candidate_identifier_id=identifier_id,
                                          identifier_type=identifier_type, value=value, decision_id=decision_id)
            stored = get_resolution_decision(connection, decision_id)
    except IntegrityError as exc:
        raise _translate(exc) from None
    return PromotionResult(decision=stored, company_id=company_id, accepted_name=True,
                           accepted_identifier_count=len(identifiers))


def _owner_of(connection: Connection, identifier_type: IdentifierType, value: str) -> UUID | None:
    return connection.execute(select(company_identifier.c.company_id).where(
        company_identifier.c.identifier_type == identifier_type.value,
        company_identifier.c.identifier_value == normalize_identifier(identifier_type, value))).scalar()


def attach_candidate_to_company(db: Engine | Connection, candidate_id: int, company_id: UUID,
                                authority: Authority) -> PromotionResult:
    """The candidate refers to an EXISTING Company. A human attach also accepts what is new: the candidate's name
    as an alias and its identifiers, unless one already belongs to a DIFFERENT company (IdentifierConflictError:
    no silent two-company ownership, no merge). A rule attach accepts nothing new."""
    authority = _checked_authority(authority, DecisionKind.ATTACH_TO_COMPANY)
    try:
        with atomic(db) as connection:
            name = _open_candidate(connection, candidate_id)
            if connection.execute(select(company.c.id).where(company.c.id == company_id)).first() is None:
                raise NotFoundError("company_not_found", "no such company")
            human = authority.kind is AuthorityKind.HUMAN
            fresh = []
            if human:
                for identifier_id, identifier_type, value in list_candidate_identifier_rows(connection, candidate_id):
                    owner = _owner_of(connection, identifier_type, value)
                    if owner is None:
                        fresh.append((identifier_id, identifier_type, value))
                    elif owner != company_id:
                        raise IdentifierConflictError("identifier_conflict", "an identifier already belongs to a different company")
            decision_id = _writes.insert_decision(connection, candidate_id=candidate_id, kind=DecisionKind.ATTACH_TO_COMPANY,
                                                  authority=authority, company_id=company_id, reason_code=None)
            accepted_name = False
            if human and connection.execute(select(company_name.c.id).where(
                    company_name.c.company_id == company_id, company_name.c.name == name)).first() is None:
                _writes.insert_name(connection, company_id=company_id, name=name, candidate_id=candidate_id,
                                    role=CompanyNameRole.ALIAS, decision_id=decision_id)
                accepted_name = True
            for identifier_id, identifier_type, value in fresh:
                _writes.insert_identifier(connection, company_id=company_id, candidate_identifier_id=identifier_id,
                                          identifier_type=identifier_type, value=value, decision_id=decision_id)
            stored = get_resolution_decision(connection, decision_id)
    except IntegrityError as exc:
        raise _translate(exc) from None
    return PromotionResult(decision=stored, company_id=company_id, accepted_name=accepted_name,
                           accepted_identifier_count=len(fresh))


def _record_without_company(db: Engine | Connection, candidate_id: int, authority: Authority, kind: DecisionKind,
                            reason_code: str) -> PromotionResult:
    authority = _checked_authority(authority, kind)
    validate_reason_code(reason_code)
    try:
        with atomic(db) as connection:
            _open_candidate(connection, candidate_id)
            decision_id = _writes.insert_decision(connection, candidate_id=candidate_id, kind=kind, authority=authority,
                                                  company_id=None, reason_code=reason_code)
            stored = get_resolution_decision(connection, decision_id)
    except IntegrityError as exc:
        raise _translate(exc) from None
    return PromotionResult(decision=stored, company_id=None)


def reject_candidate(db: Engine | Connection, candidate_id: int, authority: Authority, reason_code: str) -> PromotionResult:
    return _record_without_company(db, candidate_id, authority, DecisionKind.REJECT_CANDIDATE, reason_code)


def defer_candidate(db: Engine | Connection, candidate_id: int, authority: Authority, reason_code: str) -> PromotionResult:
    """Recorded for the audit trail; not final, so a later decision may still resolve the candidate."""
    return _record_without_company(db, candidate_id, authority, DecisionKind.DEFER_CANDIDATE, reason_code)
