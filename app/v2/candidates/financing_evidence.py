"""
Deterministic evidence verification for financing-event candidate proposals. Pure functions over exact bytes:
no repositories, no database, no network, no AI.

Every locator is verified by app.v2.candidates.evidence.verify_locator (bounds, exact bytes, sha256 equality).
Nothing is repaired, fuzzy-matched or re-located; only text-like payloads carry byte spans (no OCR/PDF).

On top of "the cited bytes exist" each kind of fact gets the smallest honest consistency check:
  event evidence   the span exists (that is all a financing OCCURRENCE can mean at this layer)
  stage            the span contains an explicit stage phrase for exactly that stage (STAGE_PHRASES)
  financing type   the span contains an explicit phrase for that type (TYPE_PHRASES); OTHER needs any letter
  amount           the span contains at least one digit
  date             the span contains at least one digit
These are consistency checks, NOT classification or arithmetic: whether "$20 million" really equals the proposed
minor units, or whether a date is the FIRST SALE date and not another, is not verified here. A passing candidate is
"well-formed with existing evidence", never "a real financing"; deciding that is a later, separate layer.

Error messages are static text and small integers only, never evidence content or proposed values.
"""

import re

from app.v2.candidates.evidence import TEXT_LIKE_MEDIA_TYPES, verify_locator
from app.v2.domain.content import MediaType
from app.v2.domain.errors import InvalidInputError, UnsupportedInputError
from app.v2.domain.financing import FinancingEventCandidateProposal, FinancingType, Stage
from app.v2.domain.payload import RawPayload

_B = r"(?<![\w-])"
_E = r"(?![\w-])"

STAGE_PHRASES = {
    Stage.PRE_SEED: re.compile(_B + r"pre[- ]?seed" + _E, re.I),
    Stage.SEED: re.compile(_B + r"(?<!pre )seed" + _E, re.I),
    Stage.SERIES_A: re.compile(_B + r"series a" + _E, re.I),
    Stage.SERIES_B: re.compile(_B + r"series b" + _E, re.I),
    Stage.GROWTH: re.compile(_B + r"growth" + _E, re.I),
}

TYPE_PHRASES = {
    FinancingType.EQUITY: re.compile(_B + r"(equity|common stock|preferred stock|preferred shares?)" + _E, re.I),
    FinancingType.CONVERTIBLE: re.compile(_B + r"(convertible|safe|simple agreement for future equity)" + _E, re.I),
    FinancingType.DEBT: re.compile(_B + r"(debt|loan|credit facility)" + _E, re.I),
    FinancingType.OTHER: re.compile(r"[A-Za-z]"),
}

_DIGIT = re.compile(rb"[0-9]")


def _text(span: bytes) -> str:
    return span.decode("utf-8", errors="replace")


def verify_financing_proposal(proposal: FinancingEventCandidateProposal, payload: RawPayload, media_type: MediaType, *, ordinal: int) -> None:
    """Raise if any of the proposal's evidence does not check out against the exact payload bytes."""
    if media_type not in TEXT_LIKE_MEDIA_TYPES:
        raise UnsupportedInputError("evidence_media_unsupported", f"financing candidate {ordinal}: only text-like evidence can carry byte spans")
    data = payload.payload_bytes
    verify_locator(data, proposal.event_evidence, label=f"financing candidate {ordinal} event")

    if proposal.stage is not None:
        span = verify_locator(data, proposal.stage.evidence, label=f"financing candidate {ordinal} stage")
        if STAGE_PHRASES[proposal.stage.stage].search(_text(span)) is None:
            raise InvalidInputError("stage_not_in_evidence", f"financing candidate {ordinal}: the proposed stage is not stated in its evidence")
    if proposal.financing_type is not None:
        span = verify_locator(data, proposal.financing_type.evidence, label=f"financing candidate {ordinal} type")
        if TYPE_PHRASES[proposal.financing_type.financing_type].search(_text(span)) is None:
            raise InvalidInputError("type_not_in_evidence", f"financing candidate {ordinal}: the proposed financing type is not stated in its evidence")
    for amount in proposal.amounts:
        span = verify_locator(data, amount.evidence, label=f"financing candidate {ordinal} {amount.semantics.value}")
        if _DIGIT.search(span) is None:
            raise InvalidInputError("amount_not_in_evidence", f"financing candidate {ordinal}: {amount.semantics.value} evidence contains no number")
    for date in proposal.dates:
        span = verify_locator(data, date.evidence, label=f"financing candidate {ordinal} {date.kind.value}")
        if _DIGIT.search(span) is None:
            raise InvalidInputError("date_not_in_evidence", f"financing candidate {ordinal}: {date.kind.value} evidence contains no date")
