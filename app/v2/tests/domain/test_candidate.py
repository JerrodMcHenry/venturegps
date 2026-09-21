"""Pure candidate domain: untrusted proposals, evidence locators, stored candidates."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.v2.domain.candidate import (
    MAX_EVIDENCE_SPAN_BYTES,
    MAX_IDENTIFIERS_PER_CANDIDATE,
    CompanyCandidateProposal,
    EvidenceLocator,
    IdentifierType,
    ProposedIdentifier,
    StoredCompanyCandidate,
    validate_candidate_name,
    validate_domain_name,
)
from app.v2.domain.errors import InvalidInputError, UnsupportedInputError

H = "a" * 64
T0 = datetime(2026, 9, 21, tzinfo=timezone.utc)


def loc(start=0, end=10, h=H):
    return EvidenceLocator(byte_start=start, byte_end=end, evidence_hash=h)


def proposal(**overrides):
    base = dict(proposed_name="Acme Robotics", name_evidence=loc())
    base.update(overrides)
    return CompanyCandidateProposal(**base)


# ---------------- evidence locator

def test_a_valid_locator_names_a_byte_range_and_a_hash():
    locator = loc(5, 25)
    assert (locator.byte_start, locator.byte_end, locator.length) == (5, 25, 20)


@pytest.mark.parametrize("start, end", [(10, 10), (10, 9), (10, 0)])
def test_a_zero_length_or_reversed_span_is_rejected(start, end):
    with pytest.raises((InvalidInputError, ValidationError)):
        loc(start, end)


def test_a_negative_span_is_rejected():
    with pytest.raises(ValidationError):
        loc(-1, 5)
    with pytest.raises(ValidationError):
        loc(0, -5)


def test_the_span_length_is_bounded():
    assert loc(0, MAX_EVIDENCE_SPAN_BYTES).length == MAX_EVIDENCE_SPAN_BYTES
    with pytest.raises(InvalidInputError) as info:
        loc(0, MAX_EVIDENCE_SPAN_BYTES + 1)
    assert info.value.code == "evidence_span_too_large"


@pytest.mark.parametrize("bad", ["", "A" * 64, "a" * 63, "g" * 64, None, 5])
def test_the_evidence_hash_must_be_a_sha256_hex(bad):
    with pytest.raises((InvalidInputError, ValidationError)):
        loc(h=bad)


def test_offsets_are_integers_not_coerced():
    for bad in ("1", 1.0, None, True):
        with pytest.raises(ValidationError):
            loc(start=bad)


# ---------------- names and identifiers

@pytest.mark.parametrize("name", ["Acme", "Acme Robotics, Inc.", "Zürich AG", "x" * 300])
def test_valid_candidate_names(name):
    assert validate_candidate_name(name) == name


@pytest.mark.parametrize("name", ["", " Acme", "Acme ", "Acme\nInc", "a\x00b", "x" * 301, None, 5])
def test_invalid_candidate_names(name):
    with pytest.raises(InvalidInputError):
        validate_candidate_name(name)


@pytest.mark.parametrize("value", ["example.com", "acmerobotics.com", "sub.example.co.uk", "xn--zrich-kva.ch", "a-b.example.org"])
def test_valid_domains(value):
    assert validate_domain_name(value) == value


@pytest.mark.parametrize("value", ["", "example", "Example.com", "-a.com", "a-.com", "a_b.com", "a..com", "zürich.ch", "exa mple.com", ".com",
                                   "http://example.com", "example.com/path", "a" * 64 + ".com", None])
def test_invalid_domains(value):
    with pytest.raises(InvalidInputError):
        validate_domain_name(value)


def test_an_identifier_value_must_fit_its_type():
    assert ProposedIdentifier(identifier_type=IdentifierType.DOMAIN, value="acme.com", evidence=loc()).value == "acme.com"
    assert ProposedIdentifier(identifier_type=IdentifierType.WEBSITE_URL, value="https://www.acme.com/", evidence=loc()).value == "https://www.acme.com/"
    with pytest.raises(InvalidInputError):
        ProposedIdentifier(identifier_type=IdentifierType.DOMAIN, value="https://acme.com", evidence=loc())
    with pytest.raises((InvalidInputError, UnsupportedInputError)):
        ProposedIdentifier(identifier_type=IdentifierType.WEBSITE_URL, value="acme.com", evidence=loc())
    with pytest.raises(InvalidInputError):
        ProposedIdentifier(identifier_type=IdentifierType.WEBSITE_URL, value="https://user:pw@acme.com", evidence=loc())


def test_only_the_small_identifier_vocabulary_exists():
    assert {t.value for t in IdentifierType} == {"domain", "website_url"}


def test_an_identifier_requires_evidence():
    with pytest.raises(ValidationError):
        ProposedIdentifier(identifier_type=IdentifierType.DOMAIN, value="acme.com")


# ---------------- proposals

def test_a_proposal_is_a_name_with_evidence_and_optional_identifiers_each_with_evidence():
    p = proposal(identifiers=(ProposedIdentifier(identifier_type=IdentifierType.DOMAIN, value="acme.com", evidence=loc(3, 9)),))
    assert p.proposed_name == "Acme Robotics" and p.identifiers[0].evidence.byte_start == 3
    assert proposal().identifiers == ()


def test_a_proposal_requires_name_evidence():
    with pytest.raises(ValidationError):
        CompanyCandidateProposal(proposed_name="Acme")


def test_a_proposal_carries_no_ai_metadata_or_canonical_fields():
    assert set(CompanyCandidateProposal.model_fields) == {"proposed_name", "name_evidence", "identifiers"}
    for extra in ("confidence", "score", "model", "provider", "prompt", "reasoning", "company_id", "canonical", "status", "ai_explanation"):
        with pytest.raises(ValidationError):
            proposal(**{extra: "x"})


def test_duplicate_and_excess_identifiers_are_rejected():
    ident = lambda v: ProposedIdentifier(identifier_type=IdentifierType.DOMAIN, value=v, evidence=loc())
    with pytest.raises(InvalidInputError) as info:
        proposal(identifiers=(ident("acme.com"), ident("acme.com")))
    assert info.value.code == "duplicate_identifier"
    with pytest.raises(InvalidInputError) as info:
        proposal(identifiers=tuple(ident(f"site{i}.com") for i in range(MAX_IDENTIFIERS_PER_CANDIDATE + 1)))
    assert info.value.code == "too_many_identifiers"


def test_identifiers_must_be_a_tuple_not_a_list():
    ident = ProposedIdentifier(identifier_type=IdentifierType.DOMAIN, value="acme.com", evidence=loc())
    with pytest.raises(ValidationError):
        proposal(identifiers=[ident])


def test_a_proposal_is_immutable():
    p = proposal()
    with pytest.raises(ValidationError):
        p.proposed_name = "Other"


def test_a_name_is_not_identity_two_proposals_with_the_same_name_are_independent_values():
    assert proposal() == proposal() and proposal(name_evidence=loc(1, 5)) != proposal()


# ---------------- stored candidates stay explicitly untrusted

def stored(**overrides):
    base = dict(id=1, processing_attempt_id=1, candidate_ordinal=1, proposal=proposal(), created_at=T0)
    base.update(overrides)
    return StoredCompanyCandidate(**base)


def test_a_stored_candidate_is_explicitly_an_untrusted_proposal():
    assert StoredCompanyCandidate.TRUST_LEVEL == "untrusted_proposal"
    s = stored()
    assert s.proposal.proposed_name == "Acme Robotics"


def test_a_stored_candidate_has_no_canonical_or_mutable_fields():
    assert set(StoredCompanyCandidate.model_fields) == {"id", "processing_attempt_id", "candidate_ordinal", "proposal", "created_at"}
    for banned in ("company", "canonical", "claim", "resolved", "accepted", "verified", "trusted", "updated", "status", "confidence", "score"):
        assert not any(banned in f for f in StoredCompanyCandidate.model_fields), banned


def test_a_stored_candidate_is_immutable_and_strict():
    s = stored()
    with pytest.raises(ValidationError):
        s.candidate_ordinal = 2
    for bad in (0, -1, "1", None, True, 1.0):
        with pytest.raises(ValidationError):
            stored(id=bad)
    with pytest.raises(InvalidInputError):
        stored(created_at=datetime(2026, 1, 1))


def test_the_proposal_module_does_not_treat_evidence_locators_as_free_text():
    assert {f for f in EvidenceLocator.model_fields} == {"byte_start", "byte_end", "evidence_hash"}   # no quote field
