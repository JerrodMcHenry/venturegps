"""
Deterministic evidence verification for lifecycle-event candidate proposals. Pure functions over exact bytes:
no repositories, no database, no network, no AI. Mirrors app.v2.candidates.financing_evidence exactly.

Every locator is verified by app.v2.candidates.evidence.verify_locator (bounds, exact bytes, sha256 equality).
On top of "the cited bytes exist", each fact kind gets the smallest honest consistency check:
  event evidence      the span exists (that is all a lifecycle occurrence can mean at this layer)
  name_change         the span contains the proposed new name, literally
  operating_status     the span contains an explicit phrase for that status (STATUS_PHRASES); UNKNOWN needs
                       only some evidence text (mirrors FinancingType.OTHER's own "any letter" bar) -- an
                       explicit "status could not be determined" claim still has to cite SOMETHING
  acquisition          the span contains the proposed acquirer name, literally
  successor             the span contains the proposed related-entity name, literally

These are consistency checks, NOT classification: whether a phrase really proves the company is "active", or
whether the named acquirer really completed the deal, is not verified here. A passing candidate is "well-formed
with existing evidence", never "a true fact about the company" -- deciding that is the human resolution layer.

Error messages are static text and small integers only, never evidence content or proposed values.
"""

import re

from app.v2.candidates.evidence import TEXT_LIKE_MEDIA_TYPES, verify_locator
from app.v2.domain.content import MediaType
from app.v2.domain.errors import InvalidInputError, UnsupportedInputError
from app.v2.domain.lifecycle import LifecycleEventCandidateProposal, OperatingStatus
from app.v2.domain.payload import RawPayload

_B = r"(?<![\w-])"
_E = r"(?![\w-])"

STATUS_PHRASES = {
    OperatingStatus.ACTIVE: re.compile(_B + r"(active|operating|ongoing|in operation)" + _E, re.I),
    OperatingStatus.ACQUIRED: re.compile(_B + r"(acquir\w*|wholly[- ]owned subsidiary|merger)" + _E, re.I),
    OperatingStatus.CEASED_OPERATIONS: re.compile(
        _B + r"(ceased operations?|shut down|dissolved|wound down|out of business)" + _E, re.I
    ),
    OperatingStatus.UNKNOWN: re.compile(r"[A-Za-z]"),  # any letter -- mirrors FinancingType.OTHER's own bar
}


def _text(span: bytes) -> str:
    return span.decode("utf-8", errors="replace")


def _supported(value: str, span: bytes) -> bool:
    return value.encode("utf-8") in span


def verify_lifecycle_proposal(proposal: LifecycleEventCandidateProposal, payload: RawPayload, media_type: MediaType, *, ordinal: int) -> None:
    """Raise if any of the proposal's evidence does not check out against the exact payload bytes."""
    if media_type not in TEXT_LIKE_MEDIA_TYPES:
        raise UnsupportedInputError("evidence_media_unsupported", f"lifecycle candidate {ordinal}: only text-like evidence can carry byte spans")
    data = payload.payload_bytes
    verify_locator(data, proposal.event_evidence, label=f"lifecycle candidate {ordinal} event")

    if proposal.name_change is not None:
        span = verify_locator(data, proposal.name_change.evidence, label=f"lifecycle candidate {ordinal} name_change")
        if not _supported(proposal.name_change.new_name, span):
            raise InvalidInputError("value_not_in_evidence", f"lifecycle candidate {ordinal}: the proposed new name does not appear in its evidence")

    if proposal.operating_status is not None:
        span = verify_locator(data, proposal.operating_status.evidence, label=f"lifecycle candidate {ordinal} operating_status")
        if STATUS_PHRASES[proposal.operating_status.status].search(_text(span)) is None:
            raise InvalidInputError("status_not_in_evidence", f"lifecycle candidate {ordinal}: the proposed status is not stated in its evidence")

    if proposal.acquisition is not None:
        span = verify_locator(data, proposal.acquisition.evidence, label=f"lifecycle candidate {ordinal} acquisition")
        if not _supported(proposal.acquisition.acquirer_name, span):
            raise InvalidInputError("value_not_in_evidence", f"lifecycle candidate {ordinal}: the proposed acquirer does not appear in its evidence")

    if proposal.successor is not None:
        span = verify_locator(data, proposal.successor.evidence, label=f"lifecycle candidate {ordinal} successor")
        if not _supported(proposal.successor.related_entity_name, span):
            raise InvalidInputError("value_not_in_evidence", f"lifecycle candidate {ordinal}: the proposed related entity does not appear in its evidence")
