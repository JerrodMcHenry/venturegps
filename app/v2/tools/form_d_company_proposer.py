"""
FormDCompanyProposer: a real implementation of app.v2.candidates.proposer.CandidateProposer, for SEC Form D
evidence specifically. Deterministic XML parsing only (form_d_xml.py) -- no AI, no model, no network, and
(matching the protocol's own contract) it receives only the immutable Observation and its verified RawPayload,
never a database handle, so it cannot write anything itself.

Proposes exactly one company candidate per Form D filing: the issuer's legal name (entityName), byte-exact
evidence from the filing itself, and NO identifiers -- Form D's own schema has no website/domain field (see
docs/v2/RUNBOOK_18_2.md's "known schema gaps" for the two things this deliberately does NOT propose and why).
An identifier-less candidate is a legal proposal (app.v2.domain.candidate.CompanyCandidateProposal.identifiers
defaults to an empty tuple); it correctly routes through resolution to NO_IDENTIFIER_MATCH (see
app.v2.resolution.rules.resolve_by_exact_identifier) and therefore to a human decision, which is exactly right
for a company's FIRST filing: there is nothing yet to auto-attach to.
"""

from collections.abc import Sequence

from app.v2.candidates.proposer import CandidateProposer
from app.v2.domain.candidate import CompanyCandidateProposal, EvidenceLocator
from app.v2.domain.observation import Observation
from app.v2.domain.payload import RawPayload
from app.v2.observations.hashing import compute_content_hash
from app.v2.tools.form_d_xml import ByteSpan, FormDParseError, parse_form_d


def _locator(span: ByteSpan, payload_bytes: bytes) -> EvidenceLocator:
    return EvidenceLocator(byte_start=span.start, byte_end=span.end, evidence_hash=compute_content_hash(payload_bytes[span.start:span.end]))


class FormDCompanyProposer(CandidateProposer):
    """propose() never raises for a well-formed but non-Form-D document -- it returns an empty sequence, so an
    observation this proposer cannot handle simply yields no candidates rather than failing the whole attempt
    (app.v2.candidates.service.persist_verified_candidates turns a raised exception into ProposerFailedError,
    which is the correct outcome for a genuinely malformed document, not a "this isn't Form D" one)."""

    def propose(self, observation: Observation, payload: RawPayload) -> Sequence[CompanyCandidateProposal]:
        try:
            filing = parse_form_d(payload.payload_bytes)
        except FormDParseError:
            return ()

        return (
            CompanyCandidateProposal(
                proposed_name=filing.entity_name.text,
                name_evidence=_locator(filing.entity_name, payload.payload_bytes),
                identifiers=(),
            ),
        )
