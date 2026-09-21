"""persist_verified_candidates: the proposer boundary, evidence verification, atomicity, media policy."""

import socket

import pytest
from sqlalchemy import text

from app.v2.candidates import service
from app.v2.candidates.proposer import CandidateProposer
from app.v2.candidates.service import ProposerFailedError, persist_verified_candidates
from app.v2.domain.candidate import CompanyCandidateProposal, EvidenceLocator, StoredCompanyCandidate
from app.v2.domain.errors import InvalidInputError, InvariantViolationError, UnsupportedInputError
from app.v2.domain.observation import Observation
from app.v2.domain.payload import RawPayload
from app.v2.repositories import company_candidates as cand_repo
from app.v2.repositories import processing_attempts as attempts
from app.v2.repositories.errors import ConflictError
from app.v2.tests.db.candidate_fakes import (
    MULTIBYTE,
    PAGE,
    PROC,
    V1,
    FixedProposer,
    RaisingProposer,
    ScriptedProposer,
    locate,
    make_proposal,
)
from app.v2.tests.db.evidence_helpers import count, evidence_snapshot, ingest_one

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def no_python_level_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted in the candidate layer")
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, boom)
    for name in ("create_connection", "getaddrinfo", "gethostbyname"):
        monkeypatch.setattr(socket, name, boom)


@pytest.fixture
def world(migrated_db):
    observation = ingest_one(migrated_db, payload=PAGE).observation
    attempt = attempts.start_processing(migrated_db, observation.id, PROC, V1)
    return migrated_db, observation, attempt


def counts(db):
    return {t: count(db, t) for t in ("company_candidate", "company_candidate_identifier")}


ACME = lambda: make_proposal(PAGE, "Acme Robotics", domain="acmerobotics.com", domain_needle=b"ACMEROBOTICS.COM", url="https://www.acmerobotics.com")
GLOBEX = lambda: make_proposal(PAGE, "Globex Corporation")


# ---------------- the proposer boundary

def test_the_proposer_receives_only_the_immutable_observation_and_the_verified_payload(world):
    db, observation, attempt = world
    proposer = FixedProposer([ACME()])
    persist_verified_candidates(db, attempt.id, proposer)
    (seen_observation, seen_payload), = proposer.calls
    assert isinstance(seen_observation, Observation) and seen_observation == observation.observation
    assert isinstance(seen_payload, RawPayload) and seen_payload.payload_bytes == PAGE
    assert seen_payload.content_hash == observation.observation.content_hash            # the verified payload


def test_the_proposer_is_never_handed_a_connection_or_anything_writable(world):
    db, _, attempt = world
    seen = []
    def inspect_args(observation, payload):
        seen.extend([type(observation), type(payload)])
        with pytest.raises(Exception):
            observation.observed_time = payload  # immutable
        with pytest.raises(Exception):
            payload.payload_bytes = b"tampered"
        return []
    persist_verified_candidates(db, attempt.id, ScriptedProposer(inspect_args))
    assert seen == [Observation, RawPayload]


def test_the_protocol_is_structural_and_minimal():
    import inspect
    assert list(inspect.signature(CandidateProposer.propose).parameters) == ["self", "observation", "payload"]
    assert isinstance(FixedProposer([]), object) and hasattr(FixedProposer([]), "propose")


def test_zero_proposals_are_supported_and_leave_the_attempt_untouched(world):
    db, _, attempt = world
    result = persist_verified_candidates(db, attempt.id, FixedProposer([]))
    assert result.candidates == () and result.created_count == 0 and counts(db) == {"company_candidate": 0, "company_candidate_identifier": 0}
    assert attempts.get_processing_attempt(db, attempt.id) == attempt


def test_one_proposal_becomes_one_untrusted_stored_candidate(world):
    db, _, attempt = world
    result = persist_verified_candidates(db, attempt.id, FixedProposer([ACME()]))
    (candidate,) = result.candidates
    assert isinstance(candidate, StoredCompanyCandidate) and StoredCompanyCandidate.TRUST_LEVEL == "untrusted_proposal"
    assert (candidate.processing_attempt_id, candidate.candidate_ordinal) == (attempt.id, 1)
    assert candidate.proposal == ACME() and [i.identifier_type.value for i in candidate.proposal.identifiers] == ["domain", "website_url"]
    assert result.created == (True,)


def test_multiple_proposals_from_one_observation_keep_the_proposers_order(world):
    db, _, attempt = world
    result = persist_verified_candidates(db, attempt.id, FixedProposer([GLOBEX(), ACME()]))
    assert [(c.candidate_ordinal, c.proposal.proposed_name) for c in result.candidates] == [(1, "Globex Corporation"), (2, "Acme Robotics")]
    assert [c.candidate_ordinal for c in cand_repo.list_company_candidates(db, attempt.id)] == [1, 2]


def test_a_scripted_deterministic_extractor_works_through_the_same_boundary(world):
    db, _, attempt = world
    def extract(observation, payload):
        return [make_proposal(payload.payload_bytes, name) for name in ("Acme Robotics", "Globex Corporation") if name.encode() in payload.payload_bytes]
    assert len(persist_verified_candidates(db, attempt.id, ScriptedProposer(extract)).candidates) == 2


def test_the_attempt_is_not_marked_processed_the_caller_completes_the_lifecycle_explicitly(world):
    db, _, attempt = world
    persist_verified_candidates(db, attempt.id, FixedProposer([ACME()]))
    assert attempts.get_processing_attempt(db, attempt.id).status.value == "processing"
    assert attempts.mark_processed(db, attempt.id).status.value == "processed"


def test_candidates_persisting_does_not_touch_any_evidence_or_processing_row(world):
    db, _, attempt = world
    before = evidence_snapshot(db)
    persist_verified_candidates(db, attempt.id, FixedProposer([ACME(), GLOBEX()]))
    assert evidence_snapshot(db) == before and attempts.get_processing_attempt(db, attempt.id) == attempt


def test_a_proposer_may_not_return_a_string_or_non_proposals(world):
    db, _, attempt = world
    for bad in ("Acme Robotics", b"x", 5, None):
        with pytest.raises(InvalidInputError):
            persist_verified_candidates(db, attempt.id, ScriptedProposer(lambda o, p, bad=bad: bad))
    with pytest.raises(InvalidInputError) as info:
        persist_verified_candidates(db, attempt.id, ScriptedProposer(lambda o, p: [{"proposed_name": "Acme"}]))
    assert info.value.code == "not_a_proposal" and counts(db) == {"company_candidate": 0, "company_candidate_identifier": 0}


# ---------------- transactional failure and the batch policy

def test_a_proposer_exception_leaves_no_candidates_and_no_message_leaks(world):
    db, _, attempt = world
    secret = "SECRET-PAYLOAD-Zq93"
    with pytest.raises(ProposerFailedError) as info:
        persist_verified_candidates(db, attempt.id, RaisingProposer(RuntimeError(f"model saw {secret} in the page")))
    error = info.value
    assert error.code == "proposer_failed" and error.exception_type == "RuntimeError"
    assert secret not in str(error) and secret not in repr(error) and error.__cause__ is None and error.__suppress_context__
    assert counts(db) == {"company_candidate": 0, "company_candidate_identifier": 0}
    assert attempts.get_processing_attempt(db, attempt.id) == attempt      # nothing was copied into the attempt; the caller decides


def test_the_caller_can_then_fail_the_attempt_with_its_own_bounded_reason(world):
    db, _, attempt = world
    with pytest.raises(ProposerFailedError):
        persist_verified_candidates(db, attempt.id, RaisingProposer(ValueError("boom")))
    failed = attempts.mark_failed(db, attempt.id, "proposer_error")
    assert failed.reason_code == "proposer_error" and failed.detail_code is None


def test_an_invalid_proposal_rejects_the_whole_batch(world):
    db, _, attempt = world
    bad = CompanyCandidateProposal(proposed_name="Globex Corporation", name_evidence=EvidenceLocator(
        byte_start=0, byte_end=20, evidence_hash="0" * 64))
    with pytest.raises(InvalidInputError) as info:
        persist_verified_candidates(db, attempt.id, FixedProposer([ACME(), bad, GLOBEX()]))
    assert info.value.code == "evidence_hash_mismatch" and "candidate 2" in info.value.message
    assert counts(db) == {"company_candidate": 0, "company_candidate_identifier": 0}   # not even the valid first one
    persist_verified_candidates(db, attempt.id, FixedProposer([ACME(), GLOBEX()]))     # and the attempt is still usable
    assert count(db, "company_candidate") == 2


def test_a_failure_after_the_first_write_rolls_the_whole_batch_back(world, monkeypatch):
    db, _, attempt = world
    real = cand_repo._insert_identifiers
    calls = []
    def flaky(connection, candidate_id, proposal):
        calls.append(candidate_id)
        if len(calls) == 2:
            raise RuntimeError("simulated failure mid-batch")
        return real(connection, candidate_id, proposal)
    monkeypatch.setattr(cand_repo, "_insert_identifiers", flaky)
    with pytest.raises(RuntimeError):
        persist_verified_candidates(db, attempt.id, FixedProposer([ACME(), GLOBEX(), make_proposal(PAGE, "Acme Robotics")]))
    assert counts(db) == {"company_candidate": 0, "company_candidate_identifier": 0}


def test_with_a_connection_only_the_candidate_batch_is_undone(world, monkeypatch):
    db, observation, attempt = world
    monkeypatch.setattr(cand_repo, "_insert_identifiers", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with db.connect() as conn:
        outer = conn.begin()
        second = attempts.start_processing(conn, observation.id, "other_finder", "other_finder.v1")   # earlier work in the caller's txn
        with pytest.raises(RuntimeError):
            persist_verified_candidates(conn, attempt.id, FixedProposer([ACME()]))
        assert count(conn, "company_candidate") == 0
        outer.commit()
    assert attempts.get_processing_attempt(db, second.id) is not None and count(db, "company_candidate") == 0


def test_an_unknown_attempt_is_not_found_and_the_proposer_is_never_called(world):
    db, _, _ = world
    proposer = FixedProposer([ACME()])
    with pytest.raises(Exception) as info:
        persist_verified_candidates(db, 999999, proposer)
    assert info.value.code == "attempt_not_found" and proposer.calls == []


# ---------------- attempt state: only PROCESSING attempts receive candidates

@pytest.mark.parametrize("finish", [
    lambda db, a: attempts.mark_processed(db, a.id),
    lambda db, a: attempts.mark_failed(db, a.id, "some_failure"),
    lambda db, a: attempts.mark_quarantined(db, a.id, "some_quarantine"),
])
def test_a_terminal_attempt_never_receives_candidates_and_the_proposer_is_not_called(world, finish):
    db, _, attempt = world
    persist_verified_candidates(db, attempt.id, FixedProposer([ACME()]))
    terminal = finish(db, attempt)
    proposer = FixedProposer([GLOBEX()])
    with pytest.raises(InvariantViolationError) as info:
        persist_verified_candidates(db, attempt.id, proposer)
    assert info.value.code == "attempt_not_processing" and proposer.calls == []
    assert counts(db)["company_candidate"] == 1
    assert attempts.get_processing_attempt(db, attempt.id) == terminal            # never reopened
    with pytest.raises(InvariantViolationError):
        attempts.renew_lease(db, attempt.id)


def test_replaying_after_the_attempt_finished_is_refused_even_if_identical(world):
    db, _, attempt = world
    persist_verified_candidates(db, attempt.id, FixedProposer([ACME()]))
    attempts.mark_processed(db, attempt.id)
    with pytest.raises(InvariantViolationError):
        persist_verified_candidates(db, attempt.id, FixedProposer([ACME()]))


# ---------------- media policy

def test_a_pdf_observation_cannot_carry_candidate_evidence(migrated_db):
    pdf = b"%PDF-1.7 Acme Robotics, Inc. stream\x00\x01"
    observation = ingest_one(migrated_db, payload=pdf).observation
    assert observation.observation.sniffed_media_type.value == "application/pdf"
    attempt = attempts.start_processing(migrated_db, observation.id, PROC, V1)
    with pytest.raises(UnsupportedInputError) as info:
        persist_verified_candidates(migrated_db, attempt.id, FixedProposer([make_proposal(pdf, "Acme Robotics")]))
    assert info.value.code == "evidence_media_unsupported" and count(migrated_db, "company_candidate") == 0


def test_binary_unknown_media_is_also_refused(migrated_db):
    blob = b"\x00\x01\x02Acme Robotics\xff\xfe"
    observation = ingest_one(migrated_db, payload=blob).observation
    attempt = attempts.start_processing(migrated_db, observation.id, PROC, V1)
    with pytest.raises(UnsupportedInputError):
        persist_verified_candidates(migrated_db, attempt.id, FixedProposer([make_proposal(blob, "Acme Robotics")]))


@pytest.mark.parametrize("payload", [b'{"company": "Acme Robotics, Inc.", "site": "acme.com"}', b"Plain text: Acme Robotics, Inc. (acme.com)"])
def test_json_and_plain_text_evidence_are_supported(migrated_db, payload):
    observation = ingest_one(migrated_db, payload=payload).observation
    attempt = attempts.start_processing(migrated_db, observation.id, PROC, V1)
    result = persist_verified_candidates(migrated_db, attempt.id, FixedProposer([make_proposal(payload, "Acme Robotics", domain="acme.com")]))
    assert len(result.candidates) == 1


def test_a_zero_proposal_binary_observation_is_fine_only_proposals_with_spans_are_refused(migrated_db):
    observation = ingest_one(migrated_db, payload=b"%PDF-1.4 ...").observation
    attempt = attempts.start_processing(migrated_db, observation.id, PROC, V1)
    assert persist_verified_candidates(migrated_db, attempt.id, FixedProposer([])).candidates == ()


def test_multibyte_evidence_round_trips_through_the_database_verification(migrated_db):
    observation = ingest_one(migrated_db, payload=MULTIBYTE).observation
    attempt = attempts.start_processing(migrated_db, observation.id, PROC, V1)
    result = persist_verified_candidates(migrated_db, attempt.id, FixedProposer([make_proposal(MULTIBYTE, "Acme Robotics", pad=0)]))
    start = result.candidates[0].proposal.name_evidence.byte_start
    assert start == MULTIBYTE.index(b"Acme") and start > MULTIBYTE.decode().index("Acme")   # a byte offset, not a character offset


# ---------------- idempotent replay through the service

def test_replaying_the_same_command_does_not_duplicate_candidates(world):
    db, _, attempt = world
    first = persist_verified_candidates(db, attempt.id, FixedProposer([ACME(), GLOBEX()]))
    again = persist_verified_candidates(db, attempt.id, FixedProposer([ACME(), GLOBEX()]))
    assert first.created == (True, True) and again.created == (False, False)
    assert again.candidates == first.candidates
    assert counts(db) == {"company_candidate": 2, "company_candidate_identifier": 2}   # ACME's two identifiers, stored once


def test_a_different_proposal_at_an_existing_ordinal_is_a_conflict_never_a_silent_overwrite(world):
    db, _, attempt = world
    first = persist_verified_candidates(db, attempt.id, FixedProposer([ACME()]))
    with pytest.raises(ConflictError) as info:
        persist_verified_candidates(db, attempt.id, FixedProposer([GLOBEX()]))
    assert info.value.code == "candidate_ordinal_conflict"
    assert cand_repo.list_company_candidates(db, attempt.id) == list(first.candidates)


def test_the_module_offers_only_the_one_workflow():
    import inspect
    public = {n for n, v in vars(service).items() if callable(v) and not n.startswith("_") and getattr(v, "__module__", "") == service.__name__}
    assert public == {"persist_verified_candidates", "ProposerFailedError"}
    assert "mark_processed" not in inspect.getsource(service).replace("does NOT mark the attempt PROCESSED", "")
