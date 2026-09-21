"""Deterministic evidence verification: exact bytes, bounds, hashes, value support, media policy."""

import pytest

from app.v2.candidates.evidence import TEXT_LIKE_MEDIA_TYPES, verify_locator, verify_proposal
from app.v2.domain.candidate import CompanyCandidateProposal, EvidenceLocator, IdentifierType, ProposedIdentifier
from app.v2.domain.content import MediaType
from app.v2.domain.errors import InvalidInputError, UnsupportedInputError
from app.v2.observations.hashing import build_raw_payload, compute_content_hash
from app.v2.tests.db.candidate_fakes import MULTIBYTE, PAGE, locate, make_proposal

HTML, TEXT, JSON = MediaType.TEXT_HTML, MediaType.TEXT_PLAIN, MediaType.APPLICATION_JSON


def payload(data=PAGE):
    return build_raw_payload(data)


# ---------------- locators

def test_a_valid_span_returns_exactly_the_evidence_bytes():
    locator = locate(PAGE, b"Acme Robotics")
    assert verify_locator(PAGE, locator, label="name") == b"Acme Robotics"
    assert compute_content_hash(b"Acme Robotics") == locator.evidence_hash


def test_the_whole_payload_boundary_is_inclusive_of_the_last_byte():
    last = EvidenceLocator(byte_start=len(PAGE) - 7, byte_end=len(PAGE), evidence_hash=compute_content_hash(PAGE[-7:]))
    assert verify_locator(PAGE, last, label="name") == PAGE[-7:]


@pytest.mark.parametrize("overshoot", [1, 10, 4000])
def test_a_span_past_the_end_is_rejected_not_clamped(overshoot):
    start = len(PAGE) - 3
    locator = EvidenceLocator(byte_start=start, byte_end=len(PAGE) + overshoot, evidence_hash=compute_content_hash(PAGE[start:]))
    with pytest.raises(InvalidInputError) as info:
        verify_locator(PAGE, locator, label="name")
    assert info.value.code == "evidence_out_of_bounds"


def test_a_span_starting_past_the_end_is_rejected():
    locator = EvidenceLocator(byte_start=len(PAGE) + 5, byte_end=len(PAGE) + 9, evidence_hash="a" * 64)
    with pytest.raises(InvalidInputError) as info:
        verify_locator(PAGE, locator, label="name")
    assert info.value.code == "evidence_out_of_bounds"


def test_the_wrong_hash_is_rejected():
    good = locate(PAGE, b"Acme Robotics")
    bad = EvidenceLocator(byte_start=good.byte_start, byte_end=good.byte_end, evidence_hash="0" * 64)
    with pytest.raises(InvalidInputError) as info:
        verify_locator(PAGE, bad, label="name")
    assert info.value.code == "evidence_hash_mismatch"


def test_a_span_taken_from_a_different_payload_is_rejected():
    other = b"<html><body><h1>Zeta Labs LLC</h1><p>Visit https://zeta.example</p></body></html>"
    locator = locate(other, b"Zeta Labs")             # correct for `other`...
    with pytest.raises(InvalidInputError) as info:    # ...but not for the payload actually stored
        verify_locator(PAGE, locator, label="name")
    assert info.value.code in ("evidence_hash_mismatch", "evidence_out_of_bounds")


def test_one_byte_off_is_rejected_nothing_is_repaired_or_fuzzy_matched():
    good = locate(PAGE, b"Acme Robotics")
    for shift in (-1, 1):
        shifted = EvidenceLocator(byte_start=good.byte_start + shift, byte_end=good.byte_end + shift, evidence_hash=good.evidence_hash)
        with pytest.raises(InvalidInputError):
            verify_locator(PAGE, shifted, label="name")


def test_multibyte_content_is_addressed_by_bytes_not_characters():
    text = MULTIBYTE.decode("utf-8")
    char_index = text.index("Acme")
    byte_index = MULTIBYTE.index(b"Acme")
    assert char_index != byte_index                                       # the encoding really shifts offsets
    right = locate(MULTIBYTE, "Acme Robotics".encode())
    assert right.byte_start == byte_index and verify_locator(MULTIBYTE, right, label="name") == b"Acme Robotics"
    by_characters = EvidenceLocator(byte_start=char_index, byte_end=char_index + len("Acme Robotics"),
                                    evidence_hash=compute_content_hash(b"Acme Robotics"))
    with pytest.raises(InvalidInputError):                                # a character-offset locator does not verify
        verify_locator(MULTIBYTE, by_characters, label="name")


def test_a_multibyte_name_can_be_proposed_and_verified():
    p = make_proposal(MULTIBYTE, "Zürich")
    verify_proposal(p, payload(MULTIBYTE), TEXT, ordinal=1)
    assert p.name_evidence.length >= len("Zürich".encode())


# ---------------- value support (the evidence must actually contain the value)

def test_a_name_may_be_a_substring_of_a_wider_span():
    verify_proposal(make_proposal(PAGE, "Acme Robotics", pad=20), payload(), HTML, ordinal=1)


def test_a_name_that_is_not_in_its_evidence_is_rejected():
    span = locate(PAGE, b"Globex Corporation")
    p = CompanyCandidateProposal(proposed_name="Acme Robotics", name_evidence=span)    # cites evidence about a different company
    with pytest.raises(InvalidInputError) as info:
        verify_proposal(p, payload(), HTML, ordinal=3)
    assert info.value.code == "value_not_in_evidence" and "candidate 3" in info.value.message


def test_a_domain_is_matched_ascii_case_insensitively_but_names_and_urls_exactly():
    upper = make_proposal(PAGE, "Acme Robotics", domain="acmerobotics.com", domain_needle=b"ACMEROBOTICS.COM")
    verify_proposal(upper, payload(), HTML, ordinal=1)
    wrong_case_name = CompanyCandidateProposal(proposed_name="ACME ROBOTICS", name_evidence=locate(PAGE, b"Acme Robotics", before=5, after=5))
    with pytest.raises(InvalidInputError):
        verify_proposal(wrong_case_name, payload(), HTML, ordinal=1)


def test_an_identifier_must_appear_in_its_own_evidence():
    ident = ProposedIdentifier(identifier_type=IdentifierType.DOMAIN, value="globex.com", evidence=locate(PAGE, b"Globex Corporation"))
    p = CompanyCandidateProposal(proposed_name="Globex Corporation", name_evidence=locate(PAGE, b"Globex Corporation"), identifiers=(ident,))
    with pytest.raises(InvalidInputError) as info:
        verify_proposal(p, payload(), HTML, ordinal=2)
    assert info.value.code == "value_not_in_evidence" and "identifier 1" in info.value.message


def test_the_website_url_identifier_is_verified_too():
    verify_proposal(make_proposal(PAGE, "Acme Robotics", url="https://www.acmerobotics.com"), payload(), HTML, ordinal=1)


# ---------------- media policy: only text-like evidence has meaningful byte spans

@pytest.mark.parametrize("media", sorted(TEXT_LIKE_MEDIA_TYPES, key=lambda m: m.value))
def test_text_like_media_is_supported(media):
    verify_proposal(make_proposal(PAGE, "Acme Robotics"), payload(), media, ordinal=1)


@pytest.mark.parametrize("media", [MediaType.APPLICATION_PDF, MediaType.UNKNOWN])
def test_binary_pdf_and_unknown_media_are_not_supported_no_ocr_no_pdf_parsing(media):
    with pytest.raises(UnsupportedInputError) as info:
        verify_proposal(make_proposal(PAGE, "Acme Robotics"), payload(), media, ordinal=1)
    assert info.value.code == "evidence_media_unsupported"


def test_the_supported_set_is_exactly_the_three_text_like_types():
    assert TEXT_LIKE_MEDIA_TYPES == {TEXT, HTML, JSON}


# ---------------- messages never carry evidence

def test_rejection_messages_contain_no_evidence_or_proposed_values():
    secret = b"SECRET-PAYLOAD-Zq93 Acme Robotics"
    data = payload(secret)
    good = locate(secret, b"SECRET-PAYLOAD-Zq93")
    bad_hash = EvidenceLocator(byte_start=good.byte_start, byte_end=good.byte_end, evidence_hash="0" * 64)
    p = CompanyCandidateProposal(proposed_name="SECRET-NAME-Zq93", name_evidence=bad_hash)
    with pytest.raises(InvalidInputError) as info:
        verify_proposal(p, data, TEXT, ordinal=1)
    assert "SECRET" not in str(info.value) and "SECRET" not in repr(info.value)
    p2 = CompanyCandidateProposal(proposed_name="SECRET-NAME-Zq93", name_evidence=good)
    with pytest.raises(InvalidInputError) as info:
        verify_proposal(p2, data, TEXT, ordinal=1)
    assert "SECRET-NAME" not in str(info.value)
