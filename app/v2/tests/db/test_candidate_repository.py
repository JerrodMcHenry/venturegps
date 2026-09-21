"""Candidate persistence: untrusted records, DB-owned time, identity by ordinal, history, idempotency."""

import inspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.v2.domain.candidate import CompanyCandidateProposal, IdentifierType, ProposedIdentifier, StoredCompanyCandidate
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.repositories import company_candidates as repo
from app.v2.repositories import processing_attempts as attempts
from app.v2.repositories.errors import ConflictError, NotFoundError
from app.v2.tests.db.candidate_fakes import PAGE, PROC, V1, V2, locate, make_proposal
from app.v2.tests.db.evidence_helpers import count, evidence_snapshot, fetch_row, ingest_one

pytestmark = pytest.mark.db

ACME = lambda: make_proposal(PAGE, "Acme Robotics", domain="acmerobotics.com", domain_needle=b"ACMEROBOTICS.COM", url="https://www.acmerobotics.com")
GLOBEX = lambda: make_proposal(PAGE, "Globex Corporation")


@pytest.fixture
def world(migrated_db):
    observation = ingest_one(migrated_db, payload=PAGE).observation
    return migrated_db, observation, attempts.start_processing(migrated_db, observation.id, PROC, V1)


# ---------------- belonging and trust

def test_a_candidate_belongs_to_exactly_one_processing_attempt(world):
    db, observation, attempt = world
    stored = repo.store_company_candidates(db, attempt.id, [ACME()]).candidates[0]
    assert stored.processing_attempt_id == attempt.id
    # the attempt already identifies the observation, processor, version and attempt number: none is duplicated on the candidate
    assert not {"observation_id", "processor_id", "processor_version", "attempt_number"} & set(StoredCompanyCandidate.model_fields)
    assert fetch_row(db, "processing_attempt", "id = :i", {"i": stored.processing_attempt_id})["observation_id"] == observation.id


def test_a_stored_candidate_is_still_explicitly_untrusted(world):
    db, _, attempt = world
    stored = repo.store_company_candidates(db, attempt.id, [ACME()]).candidates[0]
    assert StoredCompanyCandidate.TRUST_LEVEL == "untrusted_proposal" and stored.TRUST_LEVEL == "untrusted_proposal"
    assert repo.get_company_candidate(db, stored.id) == stored


def test_a_candidate_name_is_not_identity(world):
    db, observation, attempt = world
    same_name_twice = [make_proposal(PAGE, "Acme Robotics"), make_proposal(PAGE, "Acme Robotics", domain="acmerobotics.com", domain_needle=b"ACMEROBOTICS.COM")]
    a, b = repo.store_company_candidates(db, attempt.id, same_name_twice).candidates
    assert a.proposal.proposed_name == b.proposal.proposed_name and a.id != b.id and (a.candidate_ordinal, b.candidate_ordinal) == (1, 2)
    later = attempts.start_processing(db, observation.id, "other_finder", "other_finder.v1")
    c = repo.store_company_candidates(db, later.id, [make_proposal(PAGE, "Acme Robotics")]).candidates[0]
    assert c.id not in (a.id, b.id)                                    # the same name in another attempt is another candidate


def test_identifier_proposals_stay_in_the_candidate_tables_and_noncanonical(world):
    db, _, attempt = world
    stored = repo.store_company_candidates(db, attempt.id, [ACME()]).candidates[0]
    assert [(i.identifier_type, i.value) for i in stored.proposal.identifiers] == [
        (IdentifierType.DOMAIN, "acmerobotics.com"), (IdentifierType.WEBSITE_URL, "https://www.acmerobotics.com")]
    with db.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='v2' AND relkind='r'"))}
    assert not any("claim" in t or "company" == t or "resolution" in t for t in tables)   # nothing canonical exists to receive them


def test_created_at_is_assigned_by_the_database(world):
    db, _, attempt = world
    stored = repo.store_company_candidates(db, attempt.id, [ACME()]).candidates[0]
    assert stored.created_at.tzinfo is timezone.utc and abs(datetime.now(timezone.utc) - stored.created_at) < timedelta(minutes=5)
    assert "created_at" not in inspect.signature(repo.store_company_candidates).parameters
    assert "created_at" not in CompanyCandidateProposal.model_fields


# ---------------- multiple candidates, ordering, reads

def test_multiple_candidates_per_observation_are_stored_in_deterministic_order(world):
    db, observation, attempt = world
    repo.store_company_candidates(db, attempt.id, [GLOBEX(), ACME(), make_proposal(PAGE, "Acme Robotics")])
    listed = repo.list_company_candidates(db, attempt.id)
    assert [c.candidate_ordinal for c in listed] == [1, 2, 3]
    assert [c.proposal.proposed_name for c in listed] == ["Globex Corporation", "Acme Robotics", "Acme Robotics"]
    assert repo.list_company_candidates_for_observation(db, observation.id) == listed


def test_identifiers_come_back_in_their_proposed_order(world):
    db, _, attempt = world
    reversed_order = CompanyCandidateProposal(
        proposed_name="Acme Robotics", name_evidence=locate(PAGE, b"Acme Robotics"),
        identifiers=tuple(reversed(ACME().identifiers)))
    stored = repo.store_company_candidates(db, attempt.id, [reversed_order]).candidates[0]
    assert [i.identifier_type.value for i in stored.proposal.identifiers] == ["website_url", "domain"]


def test_reads_of_missing_things(world):
    db, _, _ = world
    assert repo.get_company_candidate(db, 999) is None and repo.list_company_candidates(db, 999) == []
    for bad in (0, -1, "1", None, True):
        with pytest.raises(InvalidInputError):
            repo.get_company_candidate(db, bad)


# ---------------- history under later attempts and versions

def test_a_later_processor_version_adds_candidate_history_and_the_old_candidates_are_untouched(world):
    db, observation, attempt = world
    old = repo.store_company_candidates(db, attempt.id, [ACME()]).candidates[0]
    attempts.mark_processed(db, attempt.id)
    old_rows = evidence_snapshot(db)
    with db.connect() as conn:
        old_row = [tuple(r) for r in conn.execute(text("SELECT * FROM v2.company_candidate ORDER BY id"))]

    later = attempts.start_processing(db, observation.id, PROC, V2)                       # reprocessing under a later version
    new = repo.store_company_candidates(db, later.id, [GLOBEX(), ACME()]).candidates
    with db.connect() as conn:
        assert [tuple(r) for r in conn.execute(text("SELECT * FROM v2.company_candidate ORDER BY id"))][:1] == old_row
    assert repo.get_company_candidate(db, old.id) == old
    history = repo.list_company_candidates_for_observation(db, observation.id)
    assert [(c.processing_attempt_id, c.candidate_ordinal) for c in history] == [(attempt.id, 1), (later.id, 1), (later.id, 2)]
    assert new[0].id != old.id and evidence_snapshot(db) == old_rows                        # evidence untouched too


def test_a_failed_attempts_partial_history_does_not_block_a_retry(world):
    db, observation, attempt = world
    repo.store_company_candidates(db, attempt.id, [GLOBEX()])
    attempts.mark_failed(db, attempt.id, "post_check_failed")
    retry = attempts.start_processing(db, observation.id, PROC, V1)
    assert retry.attempt_number == 2
    stored = repo.store_company_candidates(db, retry.id, [GLOBEX()]).candidates[0]
    assert stored.candidate_ordinal == 1 and count(db, "company_candidate") == 2         # ordinals are per attempt


# ---------------- idempotency

def test_replaying_the_same_batch_returns_the_existing_candidates(world):
    db, _, attempt = world
    first = repo.store_company_candidates(db, attempt.id, [ACME(), GLOBEX()])
    again = repo.store_company_candidates(db, attempt.id, [ACME(), GLOBEX()])
    assert first.created == (True, True) and again.created == (False, False) and again.created_count == 0
    assert again.candidates == first.candidates
    assert (count(db, "company_candidate"), count(db, "company_candidate_identifier")) == (2, 2)


def test_a_partial_replay_extends_only_with_genuinely_new_ordinals(world):
    db, _, attempt = world
    repo.store_company_candidates(db, attempt.id, [ACME()])
    extended = repo.store_company_candidates(db, attempt.id, [ACME(), GLOBEX()])
    assert extended.created == (False, True) and count(db, "company_candidate") == 2


def test_different_content_at_an_existing_ordinal_conflicts_and_changes_nothing(world):
    db, _, attempt = world
    first = repo.store_company_candidates(db, attempt.id, [ACME()])
    for different in (GLOBEX(), make_proposal(PAGE, "Acme Robotics"), make_proposal(PAGE, "Acme Robotics", url="https://www.acmerobotics.com")):
        with pytest.raises(ConflictError) as info:
            repo.store_company_candidates(db, attempt.id, [different])
        assert info.value.code == "candidate_ordinal_conflict"
    assert repo.list_company_candidates(db, attempt.id) == list(first.candidates)


# ---------------- validation before any write

def test_only_proposals_are_accepted_and_the_batch_is_bounded(world):
    db, _, attempt = world
    with pytest.raises(InvalidInputError):
        repo.store_company_candidates(db, attempt.id, [{"proposed_name": "x"}])
    with pytest.raises(InvalidInputError) as info:
        repo.store_company_candidates(db, attempt.id, [GLOBEX()] * 51)
    assert info.value.code == "too_many_candidates"
    assert count(db, "company_candidate") == 0


def test_unknown_or_terminal_attempts_are_refused(world):
    db, _, attempt = world
    with pytest.raises(NotFoundError):
        repo.store_company_candidates(db, 999999, [GLOBEX()])
    attempts.mark_quarantined(db, attempt.id, "not_processable")
    with pytest.raises(InvariantViolationError) as info:
        repo.store_company_candidates(db, attempt.id, [GLOBEX()])
    assert info.value.code == "attempt_not_processing"
    with pytest.raises(InvariantViolationError):
        repo.load_proposal_context(db, attempt.id)


def test_the_context_is_the_verified_immutable_evidence(world):
    db, observation, attempt = world
    context = repo.load_proposal_context(db, attempt.id)
    assert context.attempt == attempt and context.observation == observation and context.payload.payload_bytes == PAGE


# ---------------- surface

def test_the_repository_exposes_no_update_delete_or_promotion_and_touches_only_candidate_tables():
    public = {n for n, v in vars(repo).items() if callable(v) and not n.startswith("_") and getattr(v, "__module__", "") == repo.__name__}
    assert public == {"load_proposal_context", "store_company_candidates", "get_company_candidate", "list_company_candidates",
                      "list_company_candidates_for_observation", "ProposalContext", "CandidatesStoreResult"}
    import re
    source = inspect.getsource(repo)
    code = re.sub(r'#.*', "", re.sub(r'""".*?"""', "", source, flags=re.S)).lower()      # code only: docstrings mention the word "canonical"
    assert "delete(" not in code and not re.search(r"(?<![\w])update\(", code) and "do_update" not in code   # (with_for_update is a lock, not a write)
    assert sorted(re.findall(r"insert\((\w+)\)", code)) == ["cc", "ci"]                    # writes company_candidate and its identifiers only
    for forbidden in ("insert(obs", "insert(pa", "raw_payload_table", "promote", "canonical", "resolve"):
        assert forbidden not in code, forbidden


def test_a_connection_joins_the_callers_transaction(world):
    db, _, attempt = world
    with db.connect() as conn:
        txn = conn.begin()
        repo.store_company_candidates(conn, attempt.id, [ACME()])
        assert len(repo.list_company_candidates(conn, attempt.id)) == 1
        txn.rollback()
    assert repo.list_company_candidates(db, attempt.id) == []
