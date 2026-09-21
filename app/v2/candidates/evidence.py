"""
Deterministic evidence verification for candidate proposals. Pure functions
over exact bytes: no repositories, no database, no network, no AI.

A proposal's evidence is verified against the immutable payload bytes:

  1. the media type must be text-like (text/plain, text/html, application/json).
     Binary/PDF evidence has no meaningful byte spans until a later increment
     adds an extracted-text artifact; there is no OCR and no PDF parsing here;
  2. each locator must lie within the payload (0 <= start < end <= len);
  3. the bytes payload[start:end] are extracted EXACTLY and sha256-hashed;
  4. the hash must equal the proposed evidence hash;
  5. the proposed value must literally appear in those bytes (a domain is
     compared ASCII-case-insensitively; everything else exactly).

Nothing is repaired, fuzzy-matched or re-located. A failure rejects the
proposal. Passing means "the cited evidence exists and contains the value",
never "the proposed identity is correct".

Error messages contain static text and small integers only, never evidence
content or proposed values.
"""

from app.v2.domain.candidate import CompanyCandidateProposal, EvidenceLocator, IdentifierType
from app.v2.domain.content import MediaType
from app.v2.domain.errors import InvalidInputError, UnsupportedInputError
from app.v2.domain.payload import RawPayload
from app.v2.observations.hashing import compute_content_hash

TEXT_LIKE_MEDIA_TYPES = frozenset({MediaType.TEXT_PLAIN, MediaType.TEXT_HTML, MediaType.APPLICATION_JSON})


def verify_locator(payload_bytes: bytes, locator: EvidenceLocator, *, label: str) -> bytes:
    """The exact evidence bytes, or InvalidInputError. `label` is a developer-supplied position such as 'name'."""
    if locator.byte_end > len(payload_bytes):
        raise InvalidInputError("evidence_out_of_bounds", f"{label} evidence lies outside the payload")
    span = payload_bytes[locator.byte_start:locator.byte_end]
    if compute_content_hash(span) != locator.evidence_hash:
        raise InvalidInputError("evidence_hash_mismatch", f"{label} evidence bytes do not match their hash")
    return span


def _supported(value: str, span: bytes, *, ascii_case_insensitive: bool) -> bool:
    needle = value.encode("utf-8")
    if ascii_case_insensitive:
        return needle.lower() in span.lower()
    return needle in span


def verify_proposal(proposal: CompanyCandidateProposal, payload: RawPayload, media_type: MediaType, *, ordinal: int) -> None:
    """Raise if the proposal's evidence does not check out against the exact payload bytes."""
    if media_type not in TEXT_LIKE_MEDIA_TYPES:
        raise UnsupportedInputError("evidence_media_unsupported", f"candidate {ordinal}: only text-like evidence can carry byte spans")

    span = verify_locator(payload.payload_bytes, proposal.name_evidence, label=f"candidate {ordinal} name")
    if not _supported(proposal.proposed_name, span, ascii_case_insensitive=False):
        raise InvalidInputError("value_not_in_evidence", f"candidate {ordinal}: the proposed name does not appear in its evidence")

    for position, identifier in enumerate(proposal.identifiers, start=1):
        span = verify_locator(payload.payload_bytes, identifier.evidence, label=f"candidate {ordinal} identifier {position}")
        if not _supported(identifier.value, span, ascii_case_insensitive=identifier.identifier_type is IdentifierType.DOMAIN):
            raise InvalidInputError(
                "value_not_in_evidence", f"candidate {ordinal}: proposed identifier {position} does not appear in its evidence"
            )
