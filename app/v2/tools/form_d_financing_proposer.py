"""
propose_financing_from_form_d: builds ONE FinancingEventCandidateProposal from a Form D filing for an
ALREADY-CANONICAL company. Not a CandidateProposer -- app.v2.domain.financing.FinancingEventCandidateProposal
requires a real company_id (see that module's own docstring: "the company is identified ONLY by a canonical
Company id... if the evidence describes an unknown company, company resolution must happen first"), so this
cannot run until a human has resolved the company candidate from the SAME filing (form_d_company_proposer.py)
into a real Company. This is a plain function taking that company_id as an explicit argument, called by the CLI
as its own, later step -- there is no protocol for this in app.v2.candidates (financing candidates have no
proposer abstraction the way company candidates do; app.v2.repositories.financing_event_candidates.
persist_financing_event_candidates takes already-built proposals directly).

Proposes ONLY what Form D actually states, and nothing this package cannot faithfully evidence -- see this
package's own docstring and docs/v2/RUNBOOK_18_2.md's "known schema gaps" for the two things deliberately
NOT proposed here:

  - stage: Form D never states a financing stage (no "seed"/"series" vocabulary anywhere in its schema) --
    absence is correctly expressed by proposing no stage at all, which is what "unknown stays unknown" means.
  - financing_type: Form D DOES carry a security-type flag (<isEquityType>true</isEquityType>), but the
    EXISTING evidence-verification regex (app.v2.candidates.financing_evidence.TYPE_PHRASES) requires the word
    "equity" to appear as its OWN bounded word in the evidence text; "equity" only ever appears embedded inside
    the tag NAME "isEquityType" (confirmed directly against a real filing -- see the increment's report), never
    as a standalone word anywhere in a Form D document. Citing the tag as evidence would fail that check
    honestly; synthesizing a standalone "equity" string that is not actually in the source bytes would be
    evidence fabrication. Per this increment's own instruction ("report the mismatch rather than changing the
    trusted domain model"), this is reported, not worked around, and financing_type is never proposed from
    Form D.

Amount semantics are never collapsed: offering_amount and amount_sold come from Form D's own two distinct
fields and are proposed as exactly that, never as a generic "amount" and never as announced_round_amount (Form D
never announces a "round" -- that is press/investor language Form D does not use). Currency is always "USD":
not read from the document (Form D has no currency field), but the form's own fixed, documented convention (SEC
Form D amounts are always in US dollars) -- an external fact about the form itself, not an inference from this
filing's content.

Dates: dateOfFirstSale maps directly and unambiguously to FinancingDateKind.FIRST_SALE_DATE (the exact same
concept, not a stretch); the filing's own signatureDate maps to FinancingDateKind.FILING_DATE (when the notice
was filed). Both keep DAY precision, matching exactly what the filing states -- never a fabricated time of day.
"""

from datetime import datetime, timezone
from uuid import UUID

from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.financing import (
    AmountSemantics,
    FinancingDateKind,
    FinancingEventCandidateProposal,
    Money,
    ProposedAmount,
    ProposedFinancingDate,
)
from app.v2.domain.payload import RawPayload
from app.v2.domain.time import EventTime
from app.v2.observations.hashing import compute_content_hash
from app.v2.tools.form_d_xml import ByteSpan, FormDFiling, FormDParseError, parse_form_d

FORM_D_CURRENCY = "USD"  # Form D's own fixed convention (see this module's docstring) -- never read from the document


def _locator(span: ByteSpan, payload_bytes: bytes) -> EvidenceLocator:
    return EvidenceLocator(byte_start=span.start, byte_end=span.end, evidence_hash=compute_content_hash(payload_bytes[span.start:span.end]))


def _parse_iso_date(value: str, *, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise FormDParseError(f"{label} is not a YYYY-MM-DD date") from None


def propose_financing_from_form_d(payload: RawPayload, company_id: UUID) -> list[FinancingEventCandidateProposal]:
    """Returns exactly one proposal, or raises FormDParseError if the payload is not a parseable Form D filing.
    (Unlike FormDCompanyProposer.propose, this does not swallow a parse failure into an empty list: by the time
    this runs, a human has already confirmed -- by resolving the company candidate -- that this evidence
    concerns a real company, so a parse failure here is a real error the caller should see, not a quiet no-op.)
    """
    filing: FormDFiling = parse_form_d(payload.payload_bytes)
    raw = payload.payload_bytes

    first_sale = _parse_iso_date(filing.date_of_first_sale.text, label="dateOfFirstSale")
    filed = _parse_iso_date(filing.signature_date.text, label="signatureDate")

    proposal = FinancingEventCandidateProposal(
        company_id=company_id,
        event_evidence=_locator(filing.submission_type, raw),
        stage=None,  # Form D never states one -- see module docstring
        financing_type=None,  # see module docstring: a genuine evidence-verification mismatch, reported not forced
        amounts=(
            ProposedAmount(
                semantics=AmountSemantics.OFFERING_AMOUNT,
                money=Money.from_decimal(filing.total_offering_amount.text, FORM_D_CURRENCY),
                evidence=_locator(filing.total_offering_amount, raw),
            ),
            ProposedAmount(
                semantics=AmountSemantics.AMOUNT_SOLD,
                money=Money.from_decimal(filing.total_amount_sold.text, FORM_D_CURRENCY),
                evidence=_locator(filing.total_amount_sold, raw),
            ),
        ),
        dates=(
            ProposedFinancingDate(
                kind=FinancingDateKind.FIRST_SALE_DATE,
                time=EventTime.of_day(first_sale.year, first_sale.month, first_sale.day),
                evidence=_locator(filing.date_of_first_sale, raw),
            ),
            ProposedFinancingDate(
                kind=FinancingDateKind.FILING_DATE,
                time=EventTime.of_day(filed.year, filed.month, filed.day),
                evidence=_locator(filing.signature_date, raw),
            ),
        ),
    )
    return [proposal]
