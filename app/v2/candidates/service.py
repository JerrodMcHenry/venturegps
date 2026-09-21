"""
persist_verified_candidates(db, attempt_id, proposer): the Candidate-layer workflow.

    1  require the ProcessingAttempt to be PROCESSING (row-locked until commit)
    2  load the immutable Observation and its verified RawPayload
    3  call the proposer with ONLY those two immutable objects (no database handle)
    4  validate the proposals' schema, then verify each one's evidence against the
       exact stored bytes
    5  persist immutable, still-UNTRUSTED candidates, atomically (all or none)
    6  return them

It does NOT mark the attempt PROCESSED: completing the lifecycle stays explicit,
so a later processor can add further deterministic checks before declaring
success. A stored candidate means "the proposal is well-formed and its cited
evidence exists", never "the proposed company is real": nothing here can
resolve identity or create canonical state.

A proposer exception leaves no candidate rows and is reported as
ProposerFailedError with a STATIC message (the exception's text may contain
evidence, so it is never copied). The caller may then mark the attempt failed
with a bounded reason code of its own choosing. Replaying the same command for
the same PROCESSING attempt is idempotent (see store_company_candidates); once
the attempt is terminal, nothing more can be attached.
"""

from collections.abc import Sequence

from sqlalchemy.engine import Connection, Engine

from app.v2.candidates.proposer import CandidateProposer
from app.v2.domain.candidate import CompanyCandidateProposal
from app.v2.domain.errors import DomainError, InvalidInputError
from app.v2.repositories._db import atomic
from app.v2.repositories.company_candidates import (
    CandidatesStoreResult,
    load_proposal_context,
    store_company_candidates,
)


class ProposerFailedError(DomainError):
    """The proposer raised. Only the exception's CLASS NAME is kept; never its message."""

    def __init__(self, exception_type: str):
        super().__init__("proposer_failed", "the proposer raised an exception")
        self.exception_type = exception_type


def persist_verified_candidates(db: Engine | Connection, attempt_id: int, proposer: CandidateProposer) -> CandidatesStoreResult:
    with atomic(db) as connection:
        context = load_proposal_context(connection, attempt_id)
        try:
            proposed = proposer.propose(context.observation.observation, context.payload)
        except Exception as exc:  # noqa: BLE001 - a proposer may raise anything; none of it may reach state or logs
            raise ProposerFailedError(type(exc).__name__) from None
        if isinstance(proposed, (str, bytes)) or not isinstance(proposed, Sequence):
            raise InvalidInputError("invalid_proposer_output", "a proposer must return a sequence of proposals")
        proposals: tuple[CompanyCandidateProposal, ...] = tuple(proposed)
        return store_company_candidates(connection, attempt_id, proposals)
