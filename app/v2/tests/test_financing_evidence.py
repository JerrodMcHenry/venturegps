"""Pure evidence verification for financing proposals: exact bytes, bounds, fact-kind consistency, media policy."""

import uuid

import pytest

from app.v2.candidates.financing_evidence import verify_financing_proposal
from app.v2.domain.candidate import EvidenceLocator
from app.v2.domain.content import MediaType
from app.v2.domain.errors import InvalidInputError, UnsupportedInputError
from app.v2.domain.financing import AmountSemantics, FinancingDateKind, FinancingType, Stage
from app.v2.domain.time import EventTime
from app.v2.observations.hashing import build_raw_payload, compute_content_hash
from app.v2.tests.db.financing_fakes import ANNOUNCEMENT, FORM_D, SEED_NEWS, announcement, form_d, locate, make_financing

C = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEXT, HTML, JSON = MediaType.TEXT_PLAIN, MediaType.TEXT_HTML, MediaType.APPLICATION_JSON


def verify(proposal, data=FORM_D, media=TEXT):
    verify_financing_proposal(proposal, build_raw_payload(data), media, ordinal=1)


def test_valid_exact_evidence_for_every_fact_is_accepted():
    verify(form_d(C))
    verify(announcement(C), ANNOUNCEMENT)


@pytest.mark.parametrize("media", [TEXT, HTML, JSON])
def test_text_like_media_is_accepted(media):
    verify(form_d(C), media=media)


@pytest.mark.parametrize("media", [MediaType.APPLICATION_PDF, MediaType.UNKNOWN])
def test_binary_media_cannot_carry_byte_spans_and_no_pdf_or_ocr_is_attempted(media):
    with pytest.raises(UnsupportedInputError) as info:
        verify(form_d(C), media=media)
    assert info.value.code == "evidence_media_unsupported"


def test_a_wrong_hash_is_rejected():
    good = form_d(C)
    bad = good.model_copy(update={"event_evidence": good.event_evidence.model_copy(update={"evidence_hash": compute_content_hash(b"other")})})
    with pytest.raises(InvalidInputError) as info:
        verify(bad)
    assert info.value.code == "evidence_hash_mismatch"


def test_evidence_from_a_different_payload_is_rejected():
    with pytest.raises(InvalidInputError):
        verify(form_d(C), ANNOUNCEMENT)                    # spans hashed over FORM_D, verified against another payload


def test_an_out_of_range_span_is_rejected_not_clamped():
    good = form_d(C)
    end = len(FORM_D) + 5
    bad = good.model_copy(update={"event_evidence": EvidenceLocator(byte_start=len(FORM_D) - 3, byte_end=end, evidence_hash=compute_content_hash(FORM_D[-3:]))})
    with pytest.raises(InvalidInputError) as info:
        verify(bad)
    assert info.value.code == "evidence_out_of_bounds"


def test_every_kind_of_fact_is_verified_independently():
    for field in ("stage", "financing_type"):
        p = announcement(C) if field == "stage" else form_d(C)
        fact = getattr(p, field)
        bad = p.model_copy(update={field: fact.model_copy(update={"evidence": fact.evidence.model_copy(update={"evidence_hash": compute_content_hash(b"x")})})})
        with pytest.raises(InvalidInputError):
            verify(bad, ANNOUNCEMENT if field == "stage" else FORM_D)
    for collection in ("amounts", "dates"):
        p = form_d(C)
        items = list(getattr(p, collection))
        items[0] = items[0].model_copy(update={"evidence": items[0].evidence.model_copy(update={"evidence_hash": compute_content_hash(b"x")})})
        with pytest.raises(InvalidInputError):
            verify(p.model_copy(update={collection: tuple(items)}))


# ---------------- stated, never inferred

def test_a_stage_must_be_stated_in_its_own_evidence():
    with pytest.raises(InvalidInputError) as info:                     # "Series A" evidence cannot support "seed"
        verify(make_financing(ANNOUNCEMENT, C, event=b"announced a", stage=(Stage.SEED, b"Series A")), ANNOUNCEMENT)
    assert info.value.code == "stage_not_in_evidence"
    for wrong in (Stage.SERIES_B, Stage.GROWTH, Stage.PRE_SEED):
        with pytest.raises(InvalidInputError):
            verify(make_financing(ANNOUNCEMENT, C, event=b"announced a", stage=(wrong, b"Series A")), ANNOUNCEMENT)


def test_an_amount_or_headline_size_does_not_support_a_stage():
    with pytest.raises(InvalidInputError):                              # "$20 million" is not stage evidence
        verify(make_financing(ANNOUNCEMENT, C, event=b"announced a", stage=(Stage.SERIES_A, b"$20 million")), ANNOUNCEMENT)


def test_seed_is_not_supported_by_pre_seed_text_and_pre_seed_is_by_pre_seed_text():
    verify(make_financing(SEED_NEWS, C, event=b"Acme Robotics closed", stage=(Stage.SEED, b"seed round")), SEED_NEWS)
    verify(make_financing(SEED_NEWS, C, event=b"Acme Robotics closed", stage=(Stage.PRE_SEED, b"pre-seed")), SEED_NEWS)
    with pytest.raises(InvalidInputError):
        verify(make_financing(SEED_NEWS, C, event=b"Acme Robotics closed", stage=(Stage.SEED, b"pre-seed")), SEED_NEWS)


def test_a_financing_type_must_be_stated_in_its_evidence():
    with pytest.raises(InvalidInputError) as info:
        verify(make_financing(FORM_D, C, ftype=(FinancingType.DEBT, b"Equity")))
    assert info.value.code == "type_not_in_evidence"
    with pytest.raises(InvalidInputError):                              # an amount is not type evidence
        verify(make_financing(FORM_D, C, ftype=(FinancingType.EQUITY, b"$10,000,000")))


def test_amount_and_date_evidence_must_at_least_contain_a_number():
    with pytest.raises(InvalidInputError) as info:
        verify(make_financing(FORM_D, C, amounts=[(AmountSemantics.AMOUNT_SOLD, "1", "USD", b"Issuer")]))
    assert info.value.code == "amount_not_in_evidence"
    with pytest.raises(InvalidInputError) as info:
        verify(make_financing(FORM_D, C, dates=[(FinancingDateKind.FILING_DATE, EventTime.of_year(2026), b"Issuer")]))
    assert info.value.code == "date_not_in_evidence"


def test_error_messages_never_echo_evidence_or_values():
    with pytest.raises(InvalidInputError) as info:
        verify(make_financing(FORM_D, C, ftype=(FinancingType.DEBT, b"Equity")))
    assert "Equity" not in str(info.value) and "Acme" not in str(info.value)
