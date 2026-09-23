"""form_d_company_proposer.py / form_d_financing_proposer.py, verified through the REAL, existing evidence
verification (app.v2.candidates.evidence.verify_proposal / app.v2.candidates.financing_evidence.
verify_financing_proposal) -- not a re-implementation of that check. Increment 18.2's own required coverage:
evidence locator integrity, absent identifiers, conflicting amounts (semantics never collapsed)."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.v2.candidates.evidence import verify_proposal
from app.v2.candidates.financing_evidence import verify_financing_proposal
from app.v2.domain.financing import AmountSemantics, FinancingDateKind
from app.v2.domain.observation import Observation
from app.v2.observations.hashing import build_raw_payload
from app.v2.observations.media import sniff_media_type
from app.v2.tools.form_d_company_proposer import FormDCompanyProposer
from app.v2.tools.form_d_financing_proposer import propose_financing_from_form_d
from app.v2.tools.form_d_xml import FormDParseError

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
REAL_FILING = (FIXTURE_DIR / "gecko_robotics_form_d_real.xml").read_bytes()


@pytest.fixture
def real_payload():
    return build_raw_payload(REAL_FILING)


@pytest.fixture
def real_media_type():
    return sniff_media_type(REAL_FILING)


def _observation(payload, media_type) -> Observation:
    return Observation(
        source_key="sec_edgar_form_d", source_record_identifier="0001747029-25-000002",
        observation_type="sec_form_d_filing", event_time=None, observed_time=datetime.now(timezone.utc),
        collection_version="manual_upload.v1", collector_id="venturegps_v2_cli",
        content_hash=payload.content_hash, declared_media_type=None, sniffed_media_type=media_type,
    )


def test_form_d_content_sniffs_as_text_plain(real_media_type):
    """Confirms the real filing lands in app.v2.candidates.evidence.TEXT_LIKE_MEDIA_TYPES -- byte-span evidence
    is only legal against text-like media (see that module's own docstring)."""
    from app.v2.domain.content import MediaType
    assert real_media_type is MediaType.TEXT_PLAIN


def test_company_proposer_proposes_the_real_issuer_name_with_verifiable_evidence(real_payload, real_media_type):
    proposals = FormDCompanyProposer().propose(_observation(real_payload, real_media_type), real_payload)
    assert len(proposals) == 1
    assert proposals[0].proposed_name == "Gecko Robotics, Inc."
    verify_proposal(proposals[0], real_payload, real_media_type, ordinal=1)  # raises if evidence is not real


def test_company_proposer_proposes_no_identifiers_form_d_has_no_website_field(real_payload, real_media_type):
    """Increment 18.2's required "absent identifiers" case: Form D's own schema has no website/domain field, so
    an honest proposal has zero identifiers, not a guessed or fabricated one."""
    proposals = FormDCompanyProposer().propose(_observation(real_payload, real_media_type), real_payload)
    assert proposals[0].identifiers == ()


def test_company_proposer_returns_nothing_for_a_non_form_d_document(real_payload, real_media_type):
    not_form_d = build_raw_payload(b"this is not a Form D filing at all")
    proposals = FormDCompanyProposer().propose(_observation(not_form_d, sniff_media_type(not_form_d.payload_bytes)), not_form_d)
    assert proposals == ()


def test_financing_proposer_proposes_offering_amount_and_amount_sold_as_distinct_semantics(real_payload):
    company_id = uuid.uuid4()
    [proposal] = propose_financing_from_form_d(real_payload, company_id)
    by_semantics = {a.semantics: a.money for a in proposal.amounts}
    assert set(by_semantics) == {AmountSemantics.OFFERING_AMOUNT, AmountSemantics.AMOUNT_SOLD}
    assert by_semantics[AmountSemantics.OFFERING_AMOUNT].minor_units == 139_900_000_00
    assert by_semantics[AmountSemantics.AMOUNT_SOLD].minor_units == 121_534_561_00
    # the two real amounts genuinely differ -- proves semantics were never collapsed into one generic "amount"
    assert by_semantics[AmountSemantics.OFFERING_AMOUNT] != by_semantics[AmountSemantics.AMOUNT_SOLD]


def test_financing_proposer_never_proposes_announced_round_amount_from_form_d(real_payload):
    """Increment 18.2's own explicit instruction: never infer an announced round amount from Form D alone."""
    [proposal] = propose_financing_from_form_d(real_payload, uuid.uuid4())
    semantics = {a.semantics for a in proposal.amounts}
    assert AmountSemantics.ANNOUNCED_ROUND_AMOUNT not in semantics


def test_financing_proposer_never_proposes_a_stage_form_d_does_not_state_one(real_payload):
    [proposal] = propose_financing_from_form_d(real_payload, uuid.uuid4())
    assert proposal.stage is None


def test_financing_proposer_never_proposes_a_financing_type_evidence_word_boundary_mismatch(real_payload):
    """The documented, reported mismatch (see form_d_financing_proposer.py's own docstring): Form D's
    <isEquityType>true</isEquityType> never contains the standalone word "equity" the existing evidence-
    verification regex requires, so this is never proposed, not worked around."""
    [proposal] = propose_financing_from_form_d(real_payload, uuid.uuid4())
    assert proposal.financing_type is None


def test_financing_proposer_dates_are_distinct_first_sale_vs_filing(real_payload):
    [proposal] = propose_financing_from_form_d(real_payload, uuid.uuid4())
    by_kind = {d.kind: d.time.start for d in proposal.dates}
    assert by_kind[FinancingDateKind.FIRST_SALE_DATE] == datetime(2025, 5, 15, tzinfo=timezone.utc)
    assert by_kind[FinancingDateKind.FILING_DATE] == datetime(2025, 6, 12, tzinfo=timezone.utc)
    assert by_kind[FinancingDateKind.FIRST_SALE_DATE] != by_kind[FinancingDateKind.FILING_DATE]


def test_financing_proposal_passes_real_evidence_verification(real_payload, real_media_type):
    [proposal] = propose_financing_from_form_d(real_payload, uuid.uuid4())
    verify_financing_proposal(proposal, real_payload, real_media_type, ordinal=1)  # raises if any span is fake


def test_financing_proposer_raises_for_a_non_form_d_document():
    not_form_d = build_raw_payload(b"not a filing")
    with pytest.raises(FormDParseError):
        propose_financing_from_form_d(not_form_d, uuid.uuid4())


def test_financing_proposer_rejects_a_malformed_date_form_d_xml_itself_does_not_validate_date_format():
    """form_d_xml.py only cross-checks that the extracted TEXT matches the raw bytes -- date FORMAT validation
    (this test) is propose_financing_from_form_d's own job, since it is the layer that turns that text into an
    EventTime."""
    malformed = REAL_FILING.replace(b"2025-05-15", b"not-a-date")
    payload = build_raw_payload(malformed)
    with pytest.raises(FormDParseError):
        propose_financing_from_form_d(payload, uuid.uuid4())


def test_evidence_locator_integrity_a_tampered_span_fails_real_verification(real_payload, real_media_type):
    """If a locator's hash does not match the bytes it claims to cite, the EXISTING verification layer must
    catch it -- proves this proposer's output is actually re-checked byte-for-byte, not merely trusted."""
    from app.v2.domain.errors import InvalidInputError

    [proposal] = propose_financing_from_form_d(real_payload, uuid.uuid4())
    tampered_amount = proposal.amounts[0].model_copy(
        update={"evidence": proposal.amounts[0].evidence.model_copy(update={"byte_start": proposal.amounts[0].evidence.byte_start + 1})}
    )
    tampered = proposal.model_copy(update={"amounts": (tampered_amount,) + proposal.amounts[1:]})
    with pytest.raises(InvalidInputError):
        verify_financing_proposal(tampered, real_payload, real_media_type, ordinal=1)
