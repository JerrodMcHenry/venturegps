"""
Increment 18.6c: add-identity-candidate (app/v2/tools/cli.py) against the disposable V2 test database. No
network, no AI -- a human names two exact substrings (company name, domain/website) in an already-ingested
first-party observation; this only locates, hashes, and proposes them as an untrusted candidate. Required
coverage: duplicate submissions, ambiguous evidence, invalid domains, mismatched company names, and conflicting
existing identifiers (at the existing, unmodified attach boundary).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.v2.domain.observation import Observation
from app.v2.domain.resolution import human_authority
from app.v2.observations.hashing import build_raw_payload, compute_content_hash
from app.v2.observations.media import sniff_media_type
from app.v2.repositories.companies import list_company_identifiers
from app.v2.repositories.company_candidates import get_company_candidate as load_candidate
from app.v2.repositories.observations import store_observation
from app.v2.repositories.processing_attempts import get_processing_attempt
from app.v2.repositories.raw_payloads import store_raw_payload
from app.v2.repositories.sources import register_source
from app.v2.resolution import promotion
from app.v2.resolution.errors import IdentifierConflictError
from app.v2.tests.db.financing_fakes import canonical_company
from app.v2.tools import cli

pytestmark = pytest.mark.db

GECKO_PAGE = (
    b"<html><head><title>Gecko Robotics</title></head><body>"
    b"<h1>Gecko Robotics</h1><p>Gecko Robotics, Inc. builds AI + Robotics for the Built World. "
    b"Visit us at https://www.geckorobotics.com/ to learn more. "
    b"Gecko Robotics, Inc. is headquartered in Pittsburgh.</p></body></html>"
)


class Args(SimpleNamespace):
    """Matches exactly the attributes build_parser() sets on the argparse Namespace for add-identity-candidate."""


def _args(**overrides):
    base = dict(
        observation_id=None, name_find="Gecko Robotics, Inc.", name=None, name_occurrence=0,
        identifier_type="website_url", identifier_value="https://www.geckorobotics.com/",
        identifier_find="https://www.geckorobotics.com/", identifier_occurrence=0,
    )
    base.update(overrides)
    return Args(**base)


def _ingest_first_party_page(engine, *, record_id: str, payload: bytes = GECKO_PAGE) -> int:
    register_source(engine, cli.SOURCE_FIRST_PARTY_COMPANY)
    data = payload
    store_raw_payload(engine, data)
    observation = Observation(
        source_key=cli.SOURCE_FIRST_PARTY_COMPANY.source_key, source_record_identifier=record_id,
        observation_type="company_web_page", observed_time=datetime.now(timezone.utc),
        collection_version="manual_upload.v1", collector_id="admin:jerrod",
        content_hash=compute_content_hash(data), sniffed_media_type=sniff_media_type(data),
    )
    return store_observation(engine, observation).stored.id


def _candidate_count(engine) -> int:
    from sqlalchemy import text
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM v2.company_candidate")).scalar()


# ---------------------------------------------------------------- happy path

def test_a_valid_identity_candidate_is_created_with_verified_evidence(migrated_db):
    obs_id = _ingest_first_party_page(migrated_db, record_id="gecko-1")
    before = _candidate_count(migrated_db)

    cli.cmd_add_identity_candidate(_args(observation_id=obs_id), migrated_db)

    assert _candidate_count(migrated_db) == before + 1
    attempt = get_processing_attempt(migrated_db, 1)  # only attempt so far in a fresh clean_db
    assert attempt.status.value == "processed"


def test_bootstrap_registers_the_first_party_source_idempotently(migrated_db):
    class BootstrapArgs(SimpleNamespace):
        pass
    args = BootstrapArgs(taxonomy_version="venturegps_taxonomy.v1", market_slug="robotics", market_name="Robotics")
    cli.cmd_bootstrap(args, migrated_db)
    cli.cmd_bootstrap(args, migrated_db)  # idempotent, must not raise or duplicate
    from app.v2.repositories.sources import get_source_by_key
    stored = get_source_by_key(migrated_db, "first_party_company_page")
    assert stored is not None
    assert stored.source.source_type.value == "first_party_company"
    assert stored.source.is_test is False  # never test by default, same as every other registered source


# ---------------------------------------------------------------- required negative coverage

def test_duplicate_submission_is_reported_not_re_proposed(migrated_db, capsys):
    """Running the command twice for the SAME observation (an operator mistake, or two people working the same
    page) does not silently create a second candidate and does not raise an unhandled exception -- it is
    caught and reported as a duplicate, pointing at the candidate already proposed, exactly the same shape
    _collect_and_extract_one already uses for a re-collected Form D filing ("status": "duplicate")."""
    obs_id = _ingest_first_party_page(migrated_db, record_id="gecko-dup")
    before = _candidate_count(migrated_db)

    cli.cmd_add_identity_candidate(_args(observation_id=obs_id), migrated_db)
    assert _candidate_count(migrated_db) == before + 1

    capsys.readouterr()  # discard first call's output
    cli.cmd_add_identity_candidate(_args(observation_id=obs_id), migrated_db)
    assert _candidate_count(migrated_db) == before + 1  # still exactly one -- never a second

    printed = capsys.readouterr().out
    assert '"status": "duplicate"' in printed


def test_ambiguous_evidence_with_an_out_of_range_occurrence_is_rejected(migrated_db):
    """The substring appears twice in GECKO_PAGE; occurrence=2 (0-based) does not exist. Rather than guess
    which one was meant, this is refused -- the human must state an in-range occurrence explicitly."""
    obs_id = _ingest_first_party_page(migrated_db, record_id="gecko-ambiguous")
    before = _candidate_count(migrated_db)

    with pytest.raises(SystemExit):
        cli.cmd_add_identity_candidate(_args(observation_id=obs_id, name_occurrence=5), migrated_db)

    assert _candidate_count(migrated_db) == before  # nothing persisted
    attempt = get_processing_attempt(migrated_db, 1)
    assert attempt.status.value == "failed"


def test_invalid_domain_is_rejected_before_persistence(migrated_db):
    obs_id = _ingest_first_party_page(migrated_db, record_id="gecko-baddomain")
    before = _candidate_count(migrated_db)

    with pytest.raises(SystemExit):
        cli.cmd_add_identity_candidate(_args(
            observation_id=obs_id, identifier_type="domain", identifier_value="not a valid domain!!",
            identifier_find="Gecko Robotics",  # any real substring; the domain shape check fails first
        ), migrated_db)

    assert _candidate_count(migrated_db) == before


def test_mismatched_company_name_is_rejected_by_evidence_verification(migrated_db):
    """--name-find locates real evidence, but --name claims something that text never actually says --
    verify_proposal (unmodified) catches this the same way it would catch any other proposer's mismatch."""
    obs_id = _ingest_first_party_page(migrated_db, record_id="gecko-mismatch")
    before = _candidate_count(migrated_db)

    with pytest.raises(SystemExit):
        cli.cmd_add_identity_candidate(_args(observation_id=obs_id, name="A Totally Different Company Name"), migrated_db)

    assert _candidate_count(migrated_db) == before
    attempt = get_processing_attempt(migrated_db, 1)
    assert attempt.status.value == "failed"


def test_conflicting_existing_identifier_is_refused_at_attach_not_silently_allowed(migrated_db):
    """The new candidate type is not special-cased around the existing safety net: proposing (and later trying
    to attach) an identifier another canonical company already owns is refused by the SAME
    IdentifierConflictError attach_candidate_to_company has always enforced -- this command adds nothing new
    here, it only proves the new candidate shape reaches that existing check correctly."""
    owner_company_id = canonical_company(migrated_db, name="Acme Robotics, Inc.", domain="acmerobotics.com")

    conflicting_page = (
        b"<html><h1>Rival Robotics, Inc.</h1><p>Rival Robotics, Inc. can be found at acmerobotics.com "
        b"(a deliberately conflicting claim for this test).</p></html>"
    )
    obs_id = _ingest_first_party_page(migrated_db, record_id="gecko-conflict", payload=conflicting_page)
    cli.cmd_add_identity_candidate(_args(
        observation_id=obs_id, name_find="Rival Robotics, Inc.", identifier_type="domain",
        identifier_value="acmerobotics.com", identifier_find="acmerobotics.com",
    ), migrated_db)

    from sqlalchemy import select
    from app.v2.db.tables import company_candidate_table as cc
    with migrated_db.connect() as conn:
        new_candidate_id = conn.execute(select(cc.c.id).order_by(cc.c.id.desc()).limit(1)).scalar_one()

    # Create a SECOND, different canonical company to attach the conflicting candidate to.
    other_candidate = load_candidate(migrated_db, new_candidate_id)
    assert other_candidate.proposal.identifiers[0].value == "acmerobotics.com"

    different_company_id = canonical_company(migrated_db, name="Third Robotics, Inc.", domain="thirdrobotics.com")
    with pytest.raises(IdentifierConflictError):
        promotion.attach_candidate_to_company(migrated_db, new_candidate_id, different_company_id, human_authority("admin:jerrod"))

    # Never silently allowed to attach elsewhere either -- the original owner's identifier is untouched.
    identifiers = {i.identifier_value for i in list_company_identifiers(migrated_db, owner_company_id)}
    assert "acmerobotics.com" in identifiers


# ---------------------------------------------------------------- evidence integrity (byte-exact, re-verified)

def test_persisted_candidate_evidence_is_byte_exact_and_re_verifiable(migrated_db):
    obs_id = _ingest_first_party_page(migrated_db, record_id="gecko-verify")
    cli.cmd_add_identity_candidate(_args(observation_id=obs_id), migrated_db)

    from sqlalchemy import select
    from app.v2.db.tables import company_candidate_table as cc
    with migrated_db.connect() as conn:
        candidate_id = conn.execute(select(cc.c.id).order_by(cc.c.id.desc()).limit(1)).scalar_one()

    from app.v2.candidates.evidence import verify_proposal
    from app.v2.domain.content import MediaType
    from app.v2.repositories.raw_payloads import get_raw_payload
    candidate = load_candidate(migrated_db, candidate_id)
    payload = get_raw_payload(migrated_db, compute_content_hash(GECKO_PAGE), verify=True)
    verify_proposal(candidate.proposal, payload, MediaType.TEXT_HTML, ordinal=1)  # raises on any mismatch

    assert candidate.proposal.proposed_name == "Gecko Robotics, Inc."
    assert candidate.proposal.identifiers[0].value == "https://www.geckorobotics.com/"
    name_span = GECKO_PAGE[candidate.proposal.name_evidence.byte_start:candidate.proposal.name_evidence.byte_end]
    assert name_span == b"Gecko Robotics, Inc."
