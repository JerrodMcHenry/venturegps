"""Lifecycle-event candidates through the real repository: untrusted proposals only, exact evidence, atomic,
about an ALREADY-canonical company. Mirrors test_financing_candidates.py's own structure and rigor."""

import uuid

import pytest
from sqlalchemy import text

from app.v2.domain.errors import InvalidInputError, InvariantViolationError, UnsupportedInputError
from app.v2.domain.lifecycle import OperatingStatus, StoredLifecycleEventCandidate, SuccessorRelationshipKind
from app.v2.repositories import lifecycle_candidates as repo
from app.v2.repositories import observations, processing_attempts as attempts, raw_payloads, sources
from app.v2.repositories.errors import ConflictError, NotFoundError
from app.v2.tests.db.evidence_helpers import count
from app.v2.tests.db.lifecycle_fakes import (
    ACQUISITION_NEWS,
    RENAME_ANNOUNCEMENT,
    STATUS_ACTIVE_NEWS,
    STATUS_CEASED_NEWS,
    SUCCESSOR_CLAIM_NEWS,
    acquisition,
    canonical_company,
    make_lifecycle,
    rename,
    start_attempt,
    status_active,
    status_ceased,
    successor_claim,
)
from app.v2.tests.db.resolution_helpers import canonical_counts, untouched_snapshot

pytestmark = pytest.mark.db

LC_TABLES = ("lifecycle_event_candidate", "lifecycle_event_candidate_name_change",
            "lifecycle_event_candidate_operating_status", "lifecycle_event_candidate_acquisition",
            "lifecycle_event_candidate_successor")


def lc_counts(db):
    return {t: count(db, t) for t in LC_TABLES}


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    observation, attempt = start_attempt(db, RENAME_ANNOUNCEMENT)
    return db, company, observation, attempt


# ---------------- each fact kind, independently evidenced

def test_a_rename_candidate_is_stored_with_its_own_evidence(world):
    db, company, _, attempt = world
    stored = repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)]).candidates[0]
    assert isinstance(stored, StoredLifecycleEventCandidate) and stored.TRUST_LEVEL == "untrusted_proposal"
    assert stored.proposal.name_change.new_name == "Lifeward Ltd."
    assert stored.proposal.operating_status is None and stored.proposal.acquisition is None and stored.proposal.successor is None
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.lifecycle_event_candidate_name_change")).scalar() == 1


def test_dated_status_history_two_candidates_over_time_coexist(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, first = start_attempt(db, STATUS_ACTIVE_NEWS)
    _, second = start_attempt(db, STATUS_CEASED_NEWS, record_id="status-2")
    a = repo.persist_lifecycle_event_candidates(db, first.id, [status_active(company)]).candidates[0]
    b = repo.persist_lifecycle_event_candidates(db, second.id, [status_ceased(company)]).candidates[0]
    assert a.proposal.operating_status.status is OperatingStatus.ACTIVE
    assert b.proposal.operating_status.status is OperatingStatus.CEASED_OPERATIONS
    assert {c.id for c in repo.list_lifecycle_event_candidates_for_company(db, company)} == {a.id, b.id}


def test_a_name_only_acquirer_is_legitimate_with_no_canonical_link(world):
    db, company, _, _ = world
    _, attempt = start_attempt(db, ACQUISITION_NEWS, record_id="acq-1")
    stored = repo.persist_lifecycle_event_candidates(db, attempt.id, [acquisition(company)]).candidates[0]
    assert stored.proposal.acquisition.acquirer_name == "Siemens Healthineers AG"
    assert stored.proposal.acquisition.acquirer_company_id is None       # no canonical acquirer record required


def test_an_evidenced_acquirer_may_also_carry_a_canonical_link_when_one_exists(migrated_db):
    db = migrated_db
    company = canonical_company(db, "Acme Robotics, Inc.", "acmerobotics.com")
    acquirer = canonical_company(db, "Siemens Healthineers AG", "siemens-healthineers.example")
    _, attempt = start_attempt(db, ACQUISITION_NEWS)
    stored = repo.persist_lifecycle_event_candidates(db, attempt.id, [acquisition(company, acquirer_company_id=acquirer)]).candidates[0]
    assert stored.proposal.acquisition.acquirer_company_id == acquirer


def test_a_successor_claim_is_stored_as_an_untrusted_candidate_only(world):
    db, company, _, _ = world
    _, attempt = start_attempt(db, SUCCESSOR_CLAIM_NEWS, record_id="succ-1")
    stored = repo.persist_lifecycle_event_candidates(db, attempt.id, [successor_claim(company)]).candidates[0]
    assert stored.proposal.successor.relationship_kind is SuccessorRelationshipKind.POSSIBLE_SUCCESSOR
    assert stored.proposal.successor.related_company_id is None
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.company_successor_relationship")).scalar() == 0   # still nothing canonical


def test_a_single_candidate_may_carry_more_than_one_fact_kind(world):
    db, company, _, attempt = world
    combined = make_lifecycle(RENAME_ANNOUNCEMENT, company, event=b"Board of Directors approved",
                              name_change=("Lifeward Ltd.", b"Lifeward Ltd."),
                              operating_status=(OperatingStatus.UNKNOWN, b"Board of Directors"))
    stored = repo.persist_lifecycle_event_candidates(db, attempt.id, [combined]).candidates[0]
    assert stored.proposal.name_change is not None and stored.proposal.operating_status is not None


# ---------------- the company: must already exist canonically, never created

def test_the_company_must_already_exist_canonically_and_nothing_is_created(world):
    db, _, _, attempt = world
    before = (canonical_counts(db), untouched_snapshot(db))
    with pytest.raises(NotFoundError) as info:
        repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(uuid.uuid4())])
    assert info.value.code == "company_not_found"
    assert lc_counts(db) == dict.fromkeys(LC_TABLES, 0) and (canonical_counts(db), untouched_snapshot(db)) == before


def test_an_optional_acquirer_or_related_company_id_that_does_not_exist_is_refused(world):
    db, company, _, attempt = world
    bad_acquisition = make_lifecycle(ACQUISITION_NEWS, company, event=b"completed its acquisition",
                                     acquisition=("Siemens Healthineers AG", b"Siemens Healthineers AG", uuid.uuid4()))
    with pytest.raises(NotFoundError) as info:
        repo.persist_lifecycle_event_candidates(db, start_attempt(db, ACQUISITION_NEWS, record_id="bad-acq")[1].id, [bad_acquisition])
    assert info.value.code == "acquirer_company_not_found"

    bad_successor = make_lifecycle(SUCCESSOR_CLAIM_NEWS, company, event=b"possible successor",
                                   successor=("NewCo Robotics", SuccessorRelationshipKind.POSSIBLE_SUCCESSOR, b"NewCo Robotics", uuid.uuid4()))
    with pytest.raises(NotFoundError) as info:
        repo.persist_lifecycle_event_candidates(db, start_attempt(db, SUCCESSOR_CLAIM_NEWS, record_id="bad-succ")[1].id, [bad_successor])
    assert info.value.code == "related_company_not_found"


def test_a_lifecycle_candidate_can_never_create_or_change_a_company(world):
    db, company, _, attempt = world
    before = (canonical_counts(db), untouched_snapshot(db))
    repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)])
    assert (canonical_counts(db), untouched_snapshot(db)) == before


# ---------------- processing attempt

def test_only_a_processing_attempt_accepts_candidates_and_it_is_never_modified(world):
    db, company, _, attempt = world
    before = attempts.get_processing_attempt(db, attempt.id)
    repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)])
    assert attempts.get_processing_attempt(db, attempt.id) == before
    attempts.mark_processed(db, attempt.id)
    frozen = untouched_snapshot(db)
    with pytest.raises(InvariantViolationError) as info:
        repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)])
    assert info.value.code == "attempt_not_processing" and untouched_snapshot(db) == frozen


def test_an_unknown_attempt_is_not_found_and_bad_ids_are_refused(world):
    db, company, _, _ = world
    with pytest.raises(NotFoundError):
        repo.persist_lifecycle_event_candidates(db, 999999, [rename(company)])
    for bad in (0, -1, True, "1", None):
        with pytest.raises(InvalidInputError):
            repo.persist_lifecycle_event_candidates(db, bad, [rename(company)])


def test_only_lifecycle_proposals_are_accepted(world):
    db, _, _, attempt = world
    for bad in ("x", {"company_id": 1}, object()):
        with pytest.raises(InvalidInputError):
            repo.persist_lifecycle_event_candidates(db, attempt.id, [bad])
    assert lc_counts(db) == dict.fromkeys(LC_TABLES, 0)


# ---------------- evidence: missing/unsupported/wrong-payload evidence never gets stored

def test_evidence_from_another_payload_is_rejected_and_nothing_is_stored(world):
    db, company, _, attempt = world
    with pytest.raises(InvalidInputError):
        repo.persist_lifecycle_event_candidates(db, attempt.id, [status_active(company, STATUS_ACTIVE_NEWS)])   # locators hashed over a different payload
    assert lc_counts(db) == dict.fromkeys(LC_TABLES, 0)


def test_a_value_missing_from_its_own_evidence_is_rejected(world):
    db, company, _, attempt = world
    bad = make_lifecycle(RENAME_ANNOUNCEMENT, company, event=b"Board of Directors approved",
                         name_change=("Lifeward Ltd.", b"Board of Directors"))   # the span never states "Lifeward Ltd."
    with pytest.raises(InvalidInputError) as info:
        repo.persist_lifecycle_event_candidates(db, attempt.id, [bad])
    assert info.value.code == "value_not_in_evidence" and lc_counts(db) == dict.fromkeys(LC_TABLES, 0)


@pytest.mark.parametrize("data, event", [(b"%PDF-1.7 Board of Directors approved Lifeward Ltd. stream\x00\x01", b"Board of Directors"),
                                         (b"\x00\x01\x02 binary Board of Directors approved Lifeward Ltd.", b"Board of Directors")])
def test_binary_evidence_is_refused(migrated_db, data, event):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, data)
    proposal = make_lifecycle(data, company, event=event, name_change=("Lifeward Ltd.", b"Lifeward Ltd."))
    with pytest.raises(UnsupportedInputError) as info:
        repo.persist_lifecycle_event_candidates(db, attempt.id, [proposal])
    assert info.value.code == "evidence_media_unsupported" and lc_counts(db) == dict.fromkeys(LC_TABLES, 0)


# ---------------- duplicates and idempotency

def test_replaying_a_batch_does_not_duplicate_and_returns_the_same_candidates(world):
    db, company, _, attempt = world
    first = repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)])
    again = repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)])
    assert first.created == (True,) and again.created == (False,) and first.candidates == again.candidates
    assert lc_counts(db) == {**dict.fromkeys(LC_TABLES, 0), "lifecycle_event_candidate": 1, "lifecycle_event_candidate_name_change": 1}


def test_a_changed_proposal_at_the_same_ordinal_conflicts_and_is_never_overwritten(world):
    db, company, _, attempt = world
    original = repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)]).candidates[0]
    changed = make_lifecycle(RENAME_ANNOUNCEMENT, company, event=b"Board of Directors approved",
                             operating_status=(OperatingStatus.UNKNOWN, b"Board of Directors"))   # a DIFFERENT proposal
    with pytest.raises(ConflictError) as info:
        repo.persist_lifecycle_event_candidates(db, attempt.id, [changed])
    assert info.value.code == "candidate_ordinal_conflict"
    assert repo.get_lifecycle_event_candidate(db, original.id) == original


def test_two_observations_can_yield_two_independent_candidates_about_the_same_company(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, first = start_attempt(db, STATUS_ACTIVE_NEWS)
    _, second = start_attempt(db, STATUS_CEASED_NEWS, record_id="dup-2")
    a = repo.persist_lifecycle_event_candidates(db, first.id, [status_active(company)]).candidates[0]
    b = repo.persist_lifecycle_event_candidates(db, second.id, [status_ceased(company)]).candidates[0]
    assert a.id != b.id and lc_counts(db)["lifecycle_event_candidate"] == 2


# ---------------- atomicity

def test_an_invalid_second_candidate_rolls_back_the_first(world):
    db, company, _, attempt = world
    bad = make_lifecycle(RENAME_ANNOUNCEMENT, company, event=b"Board of Directors approved",
                         name_change=("Wrong Name Inc.", b"Board of Directors"))
    with pytest.raises(InvalidInputError):
        repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company), bad])
    assert lc_counts(db) == dict.fromkeys(LC_TABLES, 0)


def test_a_batch_may_not_exceed_the_cap(world):
    db, company, _, attempt = world
    with pytest.raises(InvalidInputError) as info:
        repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)] * 51)
    assert info.value.code == "too_many_candidates"


# ---------------- provenance

def test_provenance_reaches_the_company_and_separately_the_source_through_the_attempt(world):
    db, company, observation, attempt = world
    stored = repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)]).candidates[0]
    assert stored.proposal.company_id == company
    walked_attempt = attempts.get_processing_attempt(db, stored.processing_attempt_id)
    walked_observation = observations.get_observation_by_id(db, walked_attempt.observation_id)
    payload = raw_payloads.get_raw_payload(db, walked_observation.observation.content_hash, verify=True)
    source = sources.get_source_by_key(db, walked_observation.observation.source_key)
    assert (walked_observation.id, payload.payload_bytes, source.source.source_key) == (observation.id, RENAME_ANNOUNCEMENT, "sec_edgar")


def test_created_at_is_the_database_clock_and_there_is_no_updated_at(world):
    db, company, _, attempt = world
    stored = repo.persist_lifecycle_event_candidates(db, attempt.id, [rename(company)]).candidates[0]
    assert stored.created_at.year >= 2026
    with db.connect() as conn:
        columns = {r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='v2' AND table_name LIKE 'lifecycle_event_candidate%'"))}
    assert "updated_at" not in columns and "updated_time" not in columns
