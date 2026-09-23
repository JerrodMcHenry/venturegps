"""
Human-guided, NOT automated, evidence location for a second document (e.g. a funding announcement) that Form D
itself cannot state -- specifically ANNOUNCED_ROUND_AMOUNT (app.v2.domain.financing.AmountSemantics), which Form
D never expresses (see form_d_financing_proposer.py's own docstring: Form D never announces a "round").

This is deliberately NOT a free-text extraction proposer: Increment 18.2's boundaries explicitly rule out AI
extraction, and writing a second, general-purpose "find a dollar amount in arbitrary prose" parser would be a
meaningfully different, higher-risk kind of pattern-matching than the structured, schema-anchored XML parsing in
form_d_xml.py -- a wrong regex match on free text could silently propose a fabricated or misattributed amount
with no human ever having asserted it. Instead, a HUMAN reads the second document, decides the exact substring
that states the fact (e.g. "$125M" or "$125 million"), and this module only mechanically locates that literal
substring in the exact stored bytes and computes its hash -- it never decides what the fact IS, only where the
human said it appears. This still goes through the SAME evidence verification
(app.v2.candidates.financing_evidence.verify_financing_proposal) as every other candidate: if the substring
does not actually appear in the payload, or the amount cannot be represented exactly, this raises the same
domain errors a bad automated proposal would.
"""

from datetime import datetime, timezone

from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.financing import AmountSemantics, FinancingDateKind, Money, ProposedAmount, ProposedFinancingDate
from app.v2.domain.time import EventTime
from app.v2.observations.hashing import compute_content_hash


class FactNotFoundError(Exception):
    """The human-specified substring does not appear in the payload, or `occurrence` is out of range for how
    many times it does appear. Static message only; never echoes the substring or the payload content."""


def count_occurrences(payload_bytes: bytes, substring: str) -> int:
    """How many times `substring` appears -- callers (the CLI) show this to the human BEFORE they commit to an
    `occurrence` index, so picking one is an informed, explicit choice, not a guess."""
    needle = substring.encode("utf-8")
    if not needle:
        return 0
    count, start = 0, 0
    while (idx := payload_bytes.find(needle, start)) != -1:
        count += 1
        start = idx + 1
    return count


def _locate_substring(payload_bytes: bytes, substring: str, *, occurrence: int) -> tuple[int, int]:
    """Real pages routinely repeat the same headline/description text across several meta tags -- requiring
    strict uniqueness would make this tool unusable on ordinary web pages. Rather than guess, the human names
    WHICH occurrence (0-based, in byte order) they mean; this is still their explicit decision, just one that
    tolerates realistic repetition instead of demanding an artificially unique substring."""
    needle = substring.encode("utf-8")
    if not needle:
        raise FactNotFoundError("the substring to locate must not be empty")
    if occurrence < 0:
        raise FactNotFoundError("occurrence must be 0 or a positive integer")
    start = 0
    for _ in range(occurrence + 1):
        idx = payload_bytes.find(needle, start)
        if idx == -1:
            raise FactNotFoundError("the given substring does not appear (at least) occurrence+1 times in the payload")
        start = idx + 1
    return idx, idx + len(needle)


def locate_evidence(payload_bytes: bytes, substring: str, *, occurrence: int = 0) -> EvidenceLocator:
    """The general case: a human-named substring, located and hashed, with no fact attached -- used for
    event_evidence (proving a financing occurrence is being proposed at all), which needs no semantics of its
    own beyond "this span exists" (see app.v2.candidates.financing_evidence's own docstring)."""
    start, end = _locate_substring(payload_bytes, substring, occurrence=occurrence)
    return EvidenceLocator(byte_start=start, byte_end=end, evidence_hash=compute_content_hash(payload_bytes[start:end]))


def build_manual_amount(
    payload_bytes: bytes, *, semantics: AmountSemantics, amount: str, currency_code: str, evidence_substring: str, occurrence: int = 0
) -> ProposedAmount:
    """`evidence_substring` is EXACTLY what the human says the document states (e.g. "$125M") -- the substring
    itself does not need to look like `amount`; a human is asserting that this text supports that amount, the
    same judgment call app.v2.financing_resolution.promotion already requires a human to make when selecting
    verified_round_amount. This function only proves the substring is really there, at the stated occurrence."""
    return ProposedAmount(
        semantics=semantics, money=Money.from_decimal(amount, currency_code),
        evidence=locate_evidence(payload_bytes, evidence_substring, occurrence=occurrence),
    )


def build_manual_date(
    payload_bytes: bytes, *, kind: FinancingDateKind, iso_date: str, evidence_substring: str, occurrence: int = 0
) -> ProposedFinancingDate:
    """Same pattern as build_manual_amount, for a date the human read off the document (e.g. its publish date
    for ANNOUNCEMENT_DATE). `iso_date` is YYYY-MM-DD; only day precision is supported here since that is what a
    human reading a page date typically has -- a finer or coarser precision is a case build_manual_date does not
    cover and should not be forced into."""
    try:
        parsed = datetime.strptime(iso_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise FactNotFoundError("iso_date must be YYYY-MM-DD") from None
    return ProposedFinancingDate(
        kind=kind, time=EventTime.of_day(parsed.year, parsed.month, parsed.day),
        evidence=locate_evidence(payload_bytes, evidence_substring, occurrence=occurrence),
    )
