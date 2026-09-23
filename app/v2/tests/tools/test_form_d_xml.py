"""form_d_xml.py: safe parsing, byte-exact cross-checked location, and refusal of anything malformed/ambiguous/
unsafe. Increment 18.2's own required test coverage: malformed XML, evidence locator integrity."""

from pathlib import Path

import pytest

from app.v2.tools.form_d_xml import FormDParseError, parse_form_d

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
REAL_FILING = (FIXTURE_DIR / "gecko_robotics_form_d_real.xml").read_bytes()

MINIMAL_VALID = b"""<?xml version="1.0"?>
<edgarSubmission>
  <submissionType>D</submissionType>
  <primaryIssuer><entityName>Example Robotics, Inc.</entityName></primaryIssuer>
  <offeringData>
    <offeringSalesAmounts><totalOfferingAmount>1000000</totalOfferingAmount><totalAmountSold>500000</totalAmountSold></offeringSalesAmounts>
    <typeOfFiling><dateOfFirstSale><value>2025-01-15</value></dateOfFirstSale></typeOfFiling>
    <signatureBlock><signature><signatureDate>2025-01-20</signatureDate></signature></signatureBlock>
  </offeringData>
</edgarSubmission>"""


def test_parses_the_real_filing_and_every_span_round_trips():
    filing = parse_form_d(REAL_FILING)
    for span in (filing.entity_name, filing.total_offering_amount, filing.total_amount_sold,
                filing.date_of_first_sale, filing.signature_date, filing.submission_type):
        assert REAL_FILING[span.start:span.end].decode("utf-8") == span.text


def test_parses_a_minimal_valid_document():
    filing = parse_form_d(MINIMAL_VALID)
    assert filing.entity_name.text == "Example Robotics, Inc."
    assert filing.total_offering_amount.text == "1000000"
    assert filing.total_amount_sold.text == "500000"
    assert filing.date_of_first_sale.text == "2025-01-15"
    assert filing.signature_date.text == "2025-01-20"


def test_not_well_formed_xml_is_rejected():
    with pytest.raises(FormDParseError):
        parse_form_d(b"<edgarSubmission><submissionType>D</submissionType>")  # unclosed


def test_random_bytes_are_rejected():
    with pytest.raises(FormDParseError):
        parse_form_d(b"\x00\x01\x02 not xml at all")


def test_not_a_form_d_submission_type_is_rejected():
    doc = MINIMAL_VALID.replace(b"<submissionType>D</submissionType>", b"<submissionType>D/A</submissionType>")
    with pytest.raises(FormDParseError):
        parse_form_d(doc)


def test_missing_required_field_is_rejected():
    doc = MINIMAL_VALID.replace(b"<entityName>Example Robotics, Inc.</entityName>", b"")
    with pytest.raises(FormDParseError):
        parse_form_d(doc)


def test_a_negative_amount_is_rejected():
    doc = MINIMAL_VALID.replace(b"<totalOfferingAmount>1000000</totalOfferingAmount>", b"<totalOfferingAmount>-5</totalOfferingAmount>")
    with pytest.raises(FormDParseError):
        parse_form_d(doc)


def test_a_non_decimal_amount_is_rejected():
    doc = MINIMAL_VALID.replace(b"<totalOfferingAmount>1000000</totalOfferingAmount>", b"<totalOfferingAmount>lots</totalOfferingAmount>")
    with pytest.raises(FormDParseError):
        parse_form_d(doc)


def test_a_duplicated_ambiguous_entity_name_tag_is_rejected():
    """form_d_xml.py refuses to guess which occurrence is meant -- see its own docstring."""
    doc = MINIMAL_VALID.replace(
        b"<primaryIssuer><entityName>Example Robotics, Inc.</entityName></primaryIssuer>",
        b"<primaryIssuer><entityName>Example Robotics, Inc.</entityName><entityName>Example Robotics, Inc.</entityName></primaryIssuer>",
    )
    with pytest.raises(FormDParseError):
        parse_form_d(doc)


def test_external_entity_reference_is_refused_not_resolved():
    """SECURITY (Increment 18.2's own explicit requirement): no external entity resolution, no network access.
    defusedxml raises for a DOCTYPE declaring an external entity rather than resolving it."""
    xxe_doc = b"""<?xml version="1.0"?>
<!DOCTYPE edgarSubmission [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<edgarSubmission><submissionType>&xxe;</submissionType></edgarSubmission>"""
    with pytest.raises(FormDParseError):
        parse_form_d(xxe_doc)


def test_billion_laughs_entity_expansion_is_refused():
    """A classic entity-expansion denial-of-service document; defusedxml refuses it outright rather than
    expanding it (which is the whole point of using defusedxml over the standard library's ElementTree here)."""
    bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<edgarSubmission><submissionType>&lol2;</submissionType></edgarSubmission>"""
    with pytest.raises(FormDParseError):
        parse_form_d(bomb)


def test_evidence_locator_integrity_bytes_outside_the_document_are_never_produced():
    """Every span form_d_xml.py returns must lie strictly within the document it was given -- this is what
    "evidence locator integrity" means at this layer (byte-exact verification against the ACTUAL bytes,
    handled independently downstream by app.v2.candidates.evidence, is exercised in test_form_d_proposers.py)."""
    filing = parse_form_d(REAL_FILING)
    for span in (filing.entity_name, filing.total_offering_amount, filing.total_amount_sold,
                filing.date_of_first_sale, filing.signature_date, filing.submission_type):
        assert 0 <= span.start < span.end <= len(REAL_FILING)
