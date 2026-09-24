"""Pure evidence verification for lifecycle proposals: exact bytes, bounds, fact-kind consistency, media policy."""

import uuid

import pytest

from app.v2.candidates.lifecycle_evidence import verify_lifecycle_proposal
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.content import MediaType
from app.v2.domain.errors import InvalidInputError, UnsupportedInputError
from app.v2.domain.lifecycle import OperatingStatus, SuccessorRelationshipKind
from app.v2.observations.hashing import build_raw_payload, compute_content_hash
from app.v2.tests.db.lifecycle_fakes import (
    ACQUISITION_NEWS,
    DISTINCT_ONLY_NEWS,
    RENAME_ANNOUNCEMENT,
    STATUS_ACTIVE_NEWS,
    STATUS_CEASED_NEWS,
    SUCCESSOR_CLAIM_NEWS,
    acquisition,
    distinct_only_successor_claim,
    locate,
    make_lifecycle,
    rename,
    status_active,
    status_ceased,
    successor_claim,
)

C = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEXT, HTML, JSON = MediaType.TEXT_PLAIN, MediaType.TEXT_HTML, MediaType.APPLICATION_JSON


def verify(proposal, data, media=TEXT):
    verify_lifecycle_proposal(proposal, build_raw_payload(data), media, ordinal=1)


def test_valid_exact_evidence_is_accepted_for_every_fact_kind():
    verify(rename(C), RENAME_ANNOUNCEMENT)
    verify(status_active(C), STATUS_ACTIVE_NEWS)
    verify(status_ceased(C), STATUS_CEASED_NEWS)
    verify(acquisition(C), ACQUISITION_NEWS)
    verify(successor_claim(C), SUCCESSOR_CLAIM_NEWS)


@pytest.mark.parametrize("media", [TEXT, HTML, JSON])
def test_text_like_media_is_accepted(media):
    verify(rename(C), RENAME_ANNOUNCEMENT, media=media)


@pytest.mark.parametrize("media", [MediaType.APPLICATION_PDF, MediaType.UNKNOWN])
def test_binary_media_cannot_carry_byte_spans(media):
    with pytest.raises(UnsupportedInputError) as info:
        verify(rename(C), RENAME_ANNOUNCEMENT, media=media)
    assert info.value.code == "evidence_media_unsupported"


def test_a_wrong_hash_is_rejected():
    good = rename(C)
    bad = good.model_copy(update={"event_evidence": good.event_evidence.model_copy(update={"evidence_hash": compute_content_hash(b"other")})})
    with pytest.raises(InvalidInputError) as info:
        verify(bad, RENAME_ANNOUNCEMENT)
    assert info.value.code == "evidence_hash_mismatch"


def test_evidence_from_a_different_payload_is_rejected():
    with pytest.raises(InvalidInputError):
        verify(rename(C), STATUS_ACTIVE_NEWS)   # spans hashed over RENAME_ANNOUNCEMENT, verified against another payload


def test_an_out_of_range_span_is_rejected_not_clamped():
    good = rename(C)
    end = len(RENAME_ANNOUNCEMENT) + 5
    bad = good.model_copy(update={"event_evidence": EvidenceLocator(byte_start=len(RENAME_ANNOUNCEMENT) - 3, byte_end=end,
                                                                     evidence_hash=compute_content_hash(RENAME_ANNOUNCEMENT[-3:]))})
    with pytest.raises(InvalidInputError) as info:
        verify(bad, RENAME_ANNOUNCEMENT)
    assert info.value.code == "evidence_out_of_bounds"


# ---------------- fact-kind consistency: the proposed VALUE must appear literally in its own cited span

def test_name_change_requires_the_proposed_name_in_its_own_evidence():
    payload = b"The company changed its name. Unrelated text about something else entirely."
    proposal = make_lifecycle(payload, C, event=b"changed its name", name_change=("Lifeward Ltd.", b"Unrelated text"))
    with pytest.raises(InvalidInputError) as info:
        verify(proposal, payload)
    assert info.value.code == "value_not_in_evidence"


def test_acquisition_requires_the_acquirer_name_in_its_own_evidence():
    payload = b"A company was acquired. Unrelated text about something else entirely."
    proposal = make_lifecycle(payload, C, event=b"was acquired", acquisition=("Siemens Healthineers AG", b"Unrelated text"))
    with pytest.raises(InvalidInputError) as info:
        verify(proposal, payload)
    assert info.value.code == "value_not_in_evidence"


def test_successor_requires_the_related_entity_name_in_its_own_evidence():
    payload = b"A company may have a successor. Unrelated text about something else entirely."
    proposal = make_lifecycle(payload, C, event=b"may have a successor",
                              successor=("NewCo Robotics", SuccessorRelationshipKind.POSSIBLE_SUCCESSOR, b"Unrelated text"))
    with pytest.raises(InvalidInputError) as info:
        verify(proposal, payload)
    assert info.value.code == "value_not_in_evidence"


# ---------------- operating status: an explicit phrase per status; UNKNOWN needs only some evidence text

@pytest.mark.parametrize("status, payload, needle", [
    (OperatingStatus.ACTIVE, STATUS_ACTIVE_NEWS, b"active, independently operating"),
    (OperatingStatus.CEASED_OPERATIONS, STATUS_CEASED_NEWS, b"ceased operations"),
])
def test_each_status_needs_its_own_explicit_phrase(status, payload, needle):
    proposal = make_lifecycle(payload, C, event=payload[:20], operating_status=(status, needle))
    verify(proposal, payload)


def test_a_status_not_actually_stated_in_its_evidence_is_rejected():
    payload = b"The company held its annual meeting on a Tuesday in March."
    proposal = make_lifecycle(payload, C, event=b"annual meeting", operating_status=(OperatingStatus.ACQUIRED, b"a Tuesday in March"))
    with pytest.raises(InvalidInputError) as info:
        verify(proposal, payload)
    assert info.value.code == "status_not_in_evidence"


def test_unknown_status_needs_only_some_evidence_text_not_a_specific_phrase():
    payload = b"The company's current operational status could not be independently confirmed by this source."
    proposal = make_lifecycle(payload, C, event=b"could not be independently confirmed",
                              operating_status=(OperatingStatus.UNKNOWN, b"could not be independently confirmed"))
    verify(proposal, payload)   # UNKNOWN still has to cite SOMETHING, but no specific phrase is required


def test_an_empty_evidence_span_still_fails_the_unknown_bar():
    # STATUS_PHRASES[UNKNOWN] requires at least one letter -- a span of pure digits/punctuation is not "some text".
    payload = b"Reference number: 000-000-0000 filed on this date."
    proposal = make_lifecycle(payload, C, event=b"Reference number", operating_status=(OperatingStatus.UNKNOWN, b"000-000-0000"), pad=0)
    with pytest.raises(InvalidInputError) as info:
        verify(proposal, payload)
    assert info.value.code == "status_not_in_evidence"


# ---------------- the "legally distinct" safeguard is a human judgment, not something this layer detects

def test_the_evidence_layer_cannot_tell_a_legally_distinct_statement_from_real_successor_support():
    """This is the deliberate, documented limit of this layer (see lifecycle_evidence.py's own docstring): it
    only checks that the related entity's NAME appears in the cited span, never whether the span actually
    supports a successor relationship. A "legally distinct" statement passes this check exactly like a genuine
    successor claim would -- the 18.7 design's safeguard against inventing a relationship lives entirely in
    human review (see test_lifecycle_resolution_service.py), not here."""
    verify(distinct_only_successor_claim(C), DISTINCT_ONLY_NEWS)   # passes: "NewCo Robotics" literally appears in its span
