"""
The CandidateProposer port.

A proposer turns an immutable Observation and its verified payload into
UNTRUSTED proposals. Today it is implemented by deterministic test fakes; a
later, separately reviewed increment may implement it with a model. Either
way the contract is the same and the safety does not depend on the proposer:

  - it receives only immutable domain objects (never a connection, repository
    or session), so it cannot write to the database;
  - it returns proposals, which the caller validates deterministically
    (schema, then evidence against the exact stored bytes) before anything is stored;
  - it cannot create canonical entities, resolve identity, or promote anything;
  - it performs no network access (a rule enforced on this module).

Probabilistic proposal -> deterministic validation -> untrusted stored candidate
-> future deterministic/human resolution. Never: proposer -> canonical row.
"""

from collections.abc import Sequence
from typing import Protocol

from app.v2.domain.candidate import CompanyCandidateProposal
from app.v2.domain.observation import Observation
from app.v2.domain.payload import RawPayload


class CandidateProposer(Protocol):
    def propose(self, observation: Observation, payload: RawPayload) -> Sequence[CompanyCandidateProposal]:
        """Return zero, one or many proposals, in a deterministic order."""
        ...
