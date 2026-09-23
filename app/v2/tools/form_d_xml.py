"""
Deterministic, safe parsing of an SEC Form D primary_doc.xml, plus byte-exact location of every extracted
value in the ORIGINAL raw bytes (never the parsed tree, which has no reliable byte-offset information of its
own): the two proposer modules in this package turn these into EvidenceLocators, which the existing
app.v2.candidates.evidence / app.v2.candidates.financing_evidence verification re-checks independently against
the exact stored payload before anything is persisted.

SECURITY (Increment 18.2's own explicit requirement): parsed with defusedxml, which disables external entity
resolution, external DTD fetching and entity expansion ("billion laughs") by construction -- the standard
library's own xml.etree.ElementTree is explicitly NOT recommended for untrusted input for exactly this reason.
No network access happens anywhere in this module or anything it calls; defusedxml raises rather than silently
ignoring a document that tries to reference an external entity or DTD.

Every extracted field is cross-checked twice before being trusted:
  1. defusedxml parses the well-formed XML tree and extracts the logical value.
  2. This module INDEPENDENTLY re-locates that exact tag's text in the raw bytes by literal substring search,
     and the parsed value and the located text must match exactly, or parsing fails loudly. This guards against
     a byte-locate bug ever producing an EvidenceLocator that points at the wrong bytes.

A tag that does not appear EXACTLY ONCE in the document is refused as ambiguous, rather than guessing which
occurrence the caller meant -- Form D's own schema does not repeat any of the fields this module reads, but if a
future filing shape ever does, this module fails rather than silently locating the wrong one.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree as DefusedET


class FormDParseError(Exception):
    """The document is not a parseable, well-formed Form D primary_doc.xml, or a required field is missing,
    duplicated or does not match between the parsed tree and the raw bytes. Never contains the offending bytes
    themselves (only a static message and the field name), matching the evidence layer's own "no evidence
    content in error messages" convention."""


@dataclass(frozen=True)
class ByteSpan:
    start: int
    end: int
    text: str


def _locate_unique_element_text(raw: bytes, tag: str) -> ByteSpan:
    """The byte span of <tag>...</tag>'s inner text, requiring the tag to appear exactly once in the raw bytes.
    Self-closing tags and attributes are not supported (Form D's primary_doc.xml uses neither for the fields
    this module reads)."""
    open_tag = f"<{tag}>".encode("ascii")
    close_tag = f"</{tag}>".encode("ascii")
    first = raw.find(open_tag)
    if first == -1:
        raise FormDParseError(f"required element <{tag}> not found")
    if raw.find(open_tag, first + 1) != -1:
        raise FormDParseError(f"element <{tag}> appears more than once; refusing to guess which one")
    text_start = first + len(open_tag)
    text_end = raw.find(close_tag, text_start)
    if text_end == -1:
        raise FormDParseError(f"element <{tag}> has no closing tag")
    text = raw[text_start:text_end].decode("utf-8")
    return ByteSpan(start=text_start, end=text_end, text=text)


def _cross_checked(raw: bytes, tag: str, parsed_value: str) -> ByteSpan:
    span = _locate_unique_element_text(raw, tag)
    if span.text != parsed_value:
        raise FormDParseError(f"parsed value for <{tag}> does not match the raw bytes at its located span")
    return span


@dataclass(frozen=True)
class FormDFiling:
    """Every field this package proposes from a Form D filing, each still paired with its own byte span in the
    ORIGINAL raw bytes (never a copy, never re-encoded) so a proposer can build an EvidenceLocator directly from
    it. Fields Form D does not state (see module docstring on stage/financing_type) are simply not modeled here
    -- there is no placeholder or None to "fill in later"; a proposer that wants them must get them from
    different evidence.

    Money amounts are decimal STRINGS in Form D's own currency convention: SEC Form D amounts are always in US
    dollars (the form provides no currency field at all -- see the SEC's own Form D instructions), so callers
    combine these with the literal, external, non-evidence-derived fact "USD", not a value read from this
    document.
    """

    entity_name: ByteSpan
    total_offering_amount: ByteSpan  # decimal string, e.g. "139900000"
    total_amount_sold: ByteSpan  # decimal string
    date_of_first_sale: ByteSpan  # "YYYY-MM-DD"
    signature_date: ByteSpan  # "YYYY-MM-DD" -- when the filing itself was signed/filed
    submission_type: ByteSpan  # literally "D" for a Form D notice; event-level evidence that this document
    # proposes a financing occurrence at all


def parse_form_d(raw: bytes) -> FormDFiling:
    """Parse and cross-check a Form D primary_doc.xml. Raises FormDParseError for anything malformed, missing,
    ambiguous or a currency/amount this package cannot represent exactly (see app.v2.domain.financing.Money) --
    never guesses, never drops a field silently."""
    try:
        root = DefusedET.fromstring(raw)
    except Exception as exc:  # defusedxml raises its own exception types for entity/DTD attacks; both are refused
        raise FormDParseError("not well-formed XML, or the document attempted external entity/DTD resolution") from exc

    def text_of(path: str) -> str:
        element = root.find(path)
        if element is None or element.text is None:
            raise FormDParseError(f"required element {path} not found or empty")
        return element.text

    submission_type_value = text_of("submissionType")
    if submission_type_value != "D":
        raise FormDParseError(f"not a Form D notice (submissionType is {submission_type_value!r}, not 'D')")

    entity_name_value = text_of("primaryIssuer/entityName")
    total_offering_amount_value = text_of("offeringData/offeringSalesAmounts/totalOfferingAmount")
    total_amount_sold_value = text_of("offeringData/offeringSalesAmounts/totalAmountSold")
    date_of_first_sale_value = text_of("offeringData/typeOfFiling/dateOfFirstSale/value")
    signature_date_value = text_of("offeringData/signatureBlock/signature/signatureDate")

    for label, value in (("totalOfferingAmount", total_offering_amount_value), ("totalAmountSold", total_amount_sold_value)):
        try:
            if Decimal(value) < 0:
                raise FormDParseError(f"{label} is negative")
        except InvalidOperation:
            raise FormDParseError(f"{label} is not a decimal number") from None

    return FormDFiling(
        entity_name=_cross_checked(raw, "entityName", entity_name_value),
        total_offering_amount=_cross_checked(raw, "totalOfferingAmount", total_offering_amount_value),
        total_amount_sold=_cross_checked(raw, "totalAmountSold", total_amount_sold_value),
        date_of_first_sale=_cross_checked(raw, "value", date_of_first_sale_value) if _tag_count(raw, "value") == 1
        else _locate_dated_value(raw, date_of_first_sale_value),
        signature_date=_cross_checked(raw, "signatureDate", signature_date_value),
        submission_type=_cross_checked(raw, "submissionType", submission_type_value),
    )


def _tag_count(raw: bytes, tag: str) -> int:
    open_tag = f"<{tag}>".encode("ascii")
    count = 0
    start = 0
    while (idx := raw.find(open_tag, start)) != -1:
        count += 1
        start = idx + 1
    return count


def _locate_dated_value(raw: bytes, value: str) -> ByteSpan:
    """dateOfFirstSale is nested as <dateOfFirstSale><value>YYYY-MM-DD</value></dateOfFirstSale>, but Form D's
    schema also uses a bare <value> tag inside every federalExemptionsExclusions <item> wrapper in some filings,
    so <value> alone is not always unique. This locates the <value> specifically inside <dateOfFirstSale>."""
    outer = _locate_unique_element_text_allow_nested(raw, "dateOfFirstSale")
    inner = _locate_unique_element_text(raw[outer.start:outer.end], "value")
    if inner.text != value:
        raise FormDParseError("parsed value for dateOfFirstSale does not match the raw bytes at its located span")
    return ByteSpan(start=outer.start + inner.start, end=outer.start + inner.end, text=inner.text)


def _locate_unique_element_text_allow_nested(raw: bytes, tag: str) -> ByteSpan:
    """Like _locate_unique_element_text, but returns the span of the ELEMENT'S FULL CONTENT (which may itself
    contain child tags), not decoded as a leaf value. Used only to narrow the search region for a tag whose name
    is not unique document-wide but whose PARENT is."""
    open_tag = f"<{tag}>".encode("ascii")
    close_tag = f"</{tag}>".encode("ascii")
    first = raw.find(open_tag)
    if first == -1:
        raise FormDParseError(f"required element <{tag}> not found")
    if raw.find(open_tag, first + 1) != -1:
        raise FormDParseError(f"element <{tag}> appears more than once; refusing to guess which one")
    content_start = first + len(open_tag)
    content_end = raw.find(close_tag, content_start)
    if content_end == -1:
        raise FormDParseError(f"element <{tag}> has no closing tag")
    return ByteSpan(start=content_start, end=content_end, text="")
