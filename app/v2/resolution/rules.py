"""
The one deterministic resolution rule: exact_identifier_match.v1.

    A candidate whose validated strong identifiers (domain / website_url), after the documented
    normalization, match identifiers of exactly ONE existing canonical Company is ATTACHED to it.

It is deliberately narrow, and it can only say "attach":
  - name-only candidates never match (names are not identity)      -> not decided
  - no identifier matches                                          -> not decided
  - identifiers match TWO OR MORE companies (ambiguous/conflicting) -> not decided; a human decides
  - the candidate is already resolved                              -> not decided
A rule never creates a Company, rejects, defers, or accepts new canonical facts, and it takes no
confidence and calls no model. When it does not decide, it writes nothing.
"""

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from sqlalchemy.engine import Connection, Engine

from app.v2.domain.errors import InvalidInputError
from app.v2.domain.resolution import (
    FINAL_DECISION_KINDS,
    RULE_EXACT_IDENTIFIER_MATCH,
    StoredResolutionDecision,
    rule_authority,
)
from app.v2.repositories._db import atomic
from app.v2.repositories.companies import (
    find_company_ids_by_identifier,
    list_candidate_identifier_rows,
    list_decisions_for_candidate,
    lock_candidate_for_resolution,
)
from app.v2.repositories.errors import NotFoundError
from app.v2.resolution.promotion import attach_candidate_to_company


class RuleOutcomeKind(str, Enum):
    ATTACHED = "attached"
    NO_IDENTIFIER_MATCH = "no_identifier_match"
    AMBIGUOUS_IDENTIFIERS = "ambiguous_identifiers"
    ALREADY_RESOLVED = "already_resolved"


@dataclass(frozen=True)
class RuleOutcome:
    kind: RuleOutcomeKind
    decision: StoredResolutionDecision | None = None
    company_id: UUID | None = None


def resolve_by_exact_identifier(db: Engine | Connection, candidate_id: int) -> RuleOutcome:
    if isinstance(candidate_id, bool) or not isinstance(candidate_id, int) or candidate_id <= 0:
        raise InvalidInputError("invalid_candidate_id", "candidate_id must be a positive integer")
    with atomic(db) as connection:
        if not lock_candidate_for_resolution(connection, candidate_id):
            raise NotFoundError("candidate_not_found", "no such candidate")
        if any(d.decision_kind in FINAL_DECISION_KINDS for d in list_decisions_for_candidate(connection, candidate_id)):
            return RuleOutcome(RuleOutcomeKind.ALREADY_RESOLVED)
        matched: set[UUID] = set()
        for _id, identifier_type, value in list_candidate_identifier_rows(connection, candidate_id):
            matched.update(find_company_ids_by_identifier(connection, identifier_type, value))
        if not matched:
            return RuleOutcome(RuleOutcomeKind.NO_IDENTIFIER_MATCH)
        if len(matched) > 1:
            return RuleOutcome(RuleOutcomeKind.AMBIGUOUS_IDENTIFIERS)
        (company_id,) = matched
        result = attach_candidate_to_company(connection, candidate_id, company_id, rule_authority(RULE_EXACT_IDENTIFIER_MATCH))
    return RuleOutcome(RuleOutcomeKind.ATTACHED, decision=result.decision, company_id=company_id)
