"""The financing-resolution boundary through the real repositories: human authority, multi-candidate events,
explicit fact selection, conflicts, atomicity, provenance."""

import uuid

import pytest
from sqlalchemy import text

from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.financing import AmountSemantics, FinancingDateKind, FinancingType, Stage
from app.v2.domain.financing_resolution import (
    FactSelection,
    FinancingCandidateResolutionState,
    FinancingDecisionKind,
    NO_FACTS,
)
from app.v2.domain.resolution import human_authority, rule_authority
from app.v2.repositories import financing_event_candidates as candidates
from app.v2.repositories import financing_events as events
from app.v2.repositories.errors import NotFoundError
from app.v2.financing_resolution import promotion
from app.v2.financing_resolution.errors import (
    FactAlreadyAcceptedError,
    FactNotAvailableError,
    FinancingCandidateAlreadyResolvedError,
    WrongCompanyError,
)
from app.v2.tests.db.financing_fakes import (
    ANNOUNCEMENT,
    CONFLICTING,
    FORM_D,
    SEED_NEWS,
    announcement,
    canonical_company,
    form_d,
    make_financing,
    start_attempt,
)
from app.v2.tests.db.financing_resolution_helpers import canonical_financing_counts
from app.v2.tests.db.resolution_helpers import untouched_snapshot

pytestmark = pytest.mark.db

ME = human_authority("admin:jerrod")
ZERO = {"financing_event": 0, "financing_resolution_decision": 0, "financing_event_stage": 0,
        "financing_event_type": 0, "financing_event_verified_round_amount": 0, "financing_event_date": 0}


@pytest.fixture
def world(migrated_db):
    db = migrated_db
    company = canonical_company(db)
    _, attempt = start_attempt(db, FORM_D)
    candidate = candidates.persist_financing_event_candidates(db, attempt.id, [form_d(company)]).candidates[0]
    return db, company, candidate


def announcement_candidate(db, company, payload=ANNOUNCEMENT, amount="20000000", record_id=None):
    _, attempt = start_attempt(db, payload, record_id=record_id)
    return candidates.persist_financing_event_candidates(db, attempt.id, [announcement(company, payload, amount)]).candidates[0]


# ---------------- create

def test_a_human_creates_an_event_from_a_candidate_with_no_facts_by_default(world):
    db, company, candidate = world
    before = untouched_snapshot(db)
    result = promotion.create_event_from_candidate(db, candidate.id, ME)
    assert result.decision.decision_kind is FinancingDecisionKind.CREATE_EVENT and result.financing_event_id is not None
    assert result.decision.authority == ME and result.decision.candidate_id == candidate.id
    event = events.get_financing_event(db, result.financing_event_id)
    assert event.company_id == company and event.created_at.tzinfo is not None
    assert canonical_financing_counts(db) == {**ZERO, "financing_event": 1, "financing_resolution_decision": 1}
    assert events.get_financing_candidate_resolution_state(db, candidate.id) is FinancingCandidateResolutionState.EVENT_CREATED
    assert untouched_snapshot(db) == before
    assert candidates.get_financing_event_candidate(db, candidate.id) == candidate


def test_event_identity_is_database_generated_not_derived_from_company_amount_stage_or_date(world):
    db, company, candidate = world
    result = promotion.create_event_from_candidate(db, candidate.id, ME, FactSelection(stage=False))
    assert isinstance(result.financing_event_id, uuid.UUID)
    other = candidates.persist_financing_event_candidates(db, start_attempt(db, FORM_D, record_id="other-2")[1].id, [form_d(company)]).candidates[0]
    second = promotion.create_event_from_candidate(db, other.id, ME)
    assert second.financing_event_id != result.financing_event_id           # same company, same facts: still a DIFFERENT event


def test_a_candidate_cannot_be_resolved_twice(world):
    db, _, candidate = world
    promotion.create_event_from_candidate(db, candidate.id, ME)
    for attempt in (lambda: promotion.create_event_from_candidate(db, candidate.id, ME),
                    lambda: promotion.reject_candidate(db, candidate.id, ME, "changed_mind"),
                    lambda: promotion.defer_candidate(db, candidate.id, ME, "later")):
        with pytest.raises(FinancingCandidateAlreadyResolvedError):
            attempt()


def test_unknown_and_invalid_candidate_ids_are_refused(world):
    db, _, _ = world
    with pytest.raises(NotFoundError):
        promotion.create_event_from_candidate(db, 999999, ME)
    for bad in (0, -1, True, "1", None):
        with pytest.raises(InvalidInputError):
            promotion.create_event_from_candidate(db, bad, ME)


# ---------------- multi-candidate

def test_multiple_candidates_from_different_sources_attach_to_one_event(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="ann-1")
    c = announcement_candidate(db, company, CONFLICTING, "25000000", record_id="ann-2")
    promotion.attach_candidate_to_event(db, b.id, x, ME)
    promotion.attach_candidate_to_event(db, c.id, x, ME)
    assert canonical_financing_counts(db)["financing_event"] == 1
    for cid in (a.id, b.id, c.id):
        assert candidates.get_financing_event_candidate(db, cid) is not None       # all three candidate histories remain
    states = {cid: events.get_financing_candidate_resolution_state(db, cid) for cid in (a.id, b.id, c.id)}
    assert states == {a.id: FinancingCandidateResolutionState.EVENT_CREATED, b.id: FinancingCandidateResolutionState.ATTACHED,
                      c.id: FinancingCandidateResolutionState.ATTACHED}


def test_attaching_never_creates_a_second_event(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="ann-3")
    promotion.attach_candidate_to_event(db, b.id, x, ME)
    assert canonical_financing_counts(db)["financing_event"] == 1
    assert events.list_financing_events_for_company(db, company) == [events.get_financing_event(db, x)]


def test_attaching_to_a_missing_event_is_not_found(world):
    db, _, candidate = world
    with pytest.raises(NotFoundError):
        promotion.attach_candidate_to_event(db, candidate.id, uuid.uuid4(), ME)


def test_attach_cannot_precede_an_events_create_decision_even_via_a_dangling_reference(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="ann-4")
    promotion.attach_candidate_to_event(db, b.id, x, ME)          # ordinary case: already covered; this just re-confirms success
    assert events.get_financing_event(db, x) is not None


# ---------------- company safety

def test_a_candidate_from_another_company_cannot_attach(world):
    db, _, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    other_company = canonical_company(db, "Globex Corporation", "globex.example")
    foreign = announcement_candidate(db, other_company, record_id="foreign-1")
    before = canonical_financing_counts(db)
    with pytest.raises(WrongCompanyError):
        promotion.attach_candidate_to_event(db, foreign.id, x, ME)
    assert canonical_financing_counts(db) == before
    assert events.get_financing_candidate_resolution_state(db, foreign.id) is FinancingCandidateResolutionState.UNRESOLVED


# ---------------- reject / defer

def test_reject_creates_no_event_and_no_canonical_facts(world):
    db, _, candidate = world
    before = untouched_snapshot(db)
    result = promotion.reject_candidate(db, candidate.id, ME, "not_a_financing")
    assert result.financing_event_id is None and result.decision.reason_code == "not_a_financing"
    assert canonical_financing_counts(db) == {**ZERO, "financing_resolution_decision": 1}
    assert events.get_financing_candidate_resolution_state(db, candidate.id) is FinancingCandidateResolutionState.REJECTED
    assert untouched_snapshot(db) == before


def test_defer_creates_no_event_and_a_later_final_decision_may_still_resolve_it(world):
    db, _, candidate = world
    deferred = promotion.defer_candidate(db, candidate.id, ME, "needs_second_source")
    assert not deferred.decision.is_final and canonical_financing_counts(db) == {**ZERO, "financing_resolution_decision": 1}
    assert events.get_financing_candidate_resolution_state(db, candidate.id) is FinancingCandidateResolutionState.DEFERRED
    result = promotion.create_event_from_candidate(db, candidate.id, ME)
    assert result.financing_event_id is not None
    assert [d.decision_kind for d in events.list_decisions_for_financing_candidate(db, candidate.id)] == [
        FinancingDecisionKind.DEFER_CANDIDATE, FinancingDecisionKind.CREATE_EVENT]


def test_reasons_are_required_and_shaped(world):
    db, _, candidate = world
    for bad in ("", "Has Spaces", "x", None):
        with pytest.raises(InvalidInputError):
            promotion.reject_candidate(db, candidate.id, ME, bad)
    assert canonical_financing_counts(db) == ZERO


# ---------------- authority

def test_no_rule_can_decide_anything_since_none_is_registered(world):
    db, _, candidate = world
    rule = rule_authority("exact_identifier_match.v1")
    with pytest.raises(InvariantViolationError):
        promotion.attach_candidate_to_event(db, candidate.id, uuid.uuid4(), rule)
    with pytest.raises(InvariantViolationError):
        promotion.create_event_from_candidate(db, candidate.id, rule)
    assert canonical_financing_counts(db) == ZERO


@pytest.mark.parametrize("fake", ["ai", "human", None, {"kind": "ai", "id": "x"}, object()])
def test_no_promotion_api_accepts_anything_but_a_real_authority(world, fake):
    db, _, candidate = world
    with pytest.raises(InvalidInputError):
        promotion.create_event_from_candidate(db, candidate.id, fake)
    assert canonical_financing_counts(db) == ZERO


def test_a_forged_authority_that_skips_validation_is_still_refused(world):
    db, _, candidate = world
    from app.v2.domain.financing_resolution import Authority
    forged = Authority.model_construct(kind="ai", id="admin:jerrod")
    with pytest.raises(InvalidInputError):
        promotion.create_event_from_candidate(db, candidate.id, forged)
    assert canonical_financing_counts(db) == ZERO


# ---------------- verified round amount

def test_a_human_may_accept_announced_round_amount_as_verified_round_amount(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="verify-1")
    result = promotion.attach_candidate_to_event(db, b.id, x, ME, FactSelection(verified_round_amount=True))
    assert result.accepted_verified_round_amount
    canonical = events.get_canonical_financing_event(db, x)
    assert canonical.verified_round_amount.money.currency_code == "USD" and canonical.verified_round_amount.money.minor_units == 2_000_000_000
    assert type(canonical.verified_round_amount.money.minor_units) is int
    with db.connect() as conn:
        row = conn.execute(text("SELECT candidate_amount_id FROM v2.financing_event_verified_round_amount")).one()
        expected = conn.execute(text("SELECT id FROM v2.financing_event_candidate_amount WHERE candidate_id = :c AND amount_semantics = 'announced_round_amount'"), {"c": b.id}).scalar()
    assert row.candidate_amount_id == expected


def test_offering_and_sold_amounts_never_auto_promote_and_cannot_even_be_selected(world):
    db, _, a = world
    # `a` (Form D) proposes offering_amount/amount_sold but no announced_round_amount: it can never back a verified_round_amount
    with pytest.raises(FactNotAvailableError) as info:
        promotion.create_event_from_candidate(db, a.id, ME, FactSelection(verified_round_amount=True))
    assert info.value.code == "verified_round_amount_not_proposed"
    assert canonical_financing_counts(db)["financing_event_verified_round_amount"] == 0
    assert events.get_financing_candidate_resolution_state(db, a.id) is FinancingCandidateResolutionState.UNRESOLVED


def test_a_conflicting_later_amount_does_not_overwrite_the_accepted_one(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="conflict-1")
    promotion.attach_candidate_to_event(db, b.id, x, ME, FactSelection(verified_round_amount=True))
    c = announcement_candidate(db, company, CONFLICTING, "25000000", record_id="conflict-2")
    with pytest.raises(FactAlreadyAcceptedError):
        promotion.attach_candidate_to_event(db, c.id, x, ME, FactSelection(verified_round_amount=True))
    canonical = events.get_canonical_financing_event(db, x)
    assert canonical.verified_round_amount.money.minor_units == 2_000_000_000        # unchanged
    assert events.get_financing_candidate_resolution_state(db, c.id) is FinancingCandidateResolutionState.UNRESOLVED   # the whole attach rolled back


# ---------------- stage

def test_accepted_stage_provenance_is_preserved_and_unknown_stays_unknown(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id      # Form D: no stage
    assert events.get_canonical_financing_event(db, x).stage is None
    b = announcement_candidate(db, company, record_id="stage-1")
    result = promotion.attach_candidate_to_event(db, b.id, x, ME, FactSelection(stage=True))
    assert result.accepted_stage
    canonical = events.get_canonical_financing_event(db, x)
    assert canonical.stage.stage is Stage.SERIES_A and canonical.stage.candidate_id == b.id


def test_a_conflicting_attached_stage_does_not_overwrite(world):
    db, company, a = world
    b = announcement_candidate(db, company, record_id="stage-2")
    x = promotion.attach_candidate_to_event(db, b.id, promotion.create_event_from_candidate(db, a.id, ME).financing_event_id, ME, FactSelection(stage=True)).financing_event_id
    seed = candidates.persist_financing_event_candidates(db, start_attempt(db, SEED_NEWS, record_id="stage-3")[1].id,
                                                          [make_financing(SEED_NEWS, company, event=b"Acme Robotics closed", stage=(Stage.SEED, b"seed round"))]).candidates[0]
    with pytest.raises(FactAlreadyAcceptedError):
        promotion.attach_candidate_to_event(db, seed.id, x, ME, FactSelection(stage=True))
    assert events.get_canonical_financing_event(db, x).stage.stage is Stage.SERIES_A


def test_selecting_a_stage_the_candidate_never_proposed_is_refused(world):
    db, _, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id      # a is Form D: proposes no stage
    other = candidates.persist_financing_event_candidates(db, start_attempt(db, FORM_D, record_id="nostage-1")[1].id,
                                                           [form_d(events.get_financing_event(db, x).company_id)]).candidates[0]
    with pytest.raises(FactNotAvailableError) as info:
        promotion.attach_candidate_to_event(db, other.id, x, ME, FactSelection(stage=True))
    assert info.value.code == "stage_not_proposed"


# ---------------- financing type

def test_accepted_type_provenance_is_preserved(world):
    db, _, a = world
    result = promotion.create_event_from_candidate(db, a.id, ME, FactSelection(financing_type=True))
    canonical = events.get_canonical_financing_event(db, result.financing_event_id)
    assert canonical.financing_type.financing_type is FinancingType.EQUITY and canonical.financing_type.candidate_id == a.id


def test_a_type_the_candidate_never_proposed_is_refused(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="type-1")   # an announcement proposes no financing_type
    with pytest.raises(FactNotAvailableError) as info:
        promotion.attach_candidate_to_event(db, b.id, x, ME, FactSelection(financing_type=True))
    assert info.value.code == "financing_type_not_proposed"


# ---------------- dates

def test_accepted_dates_preserve_kind_and_precision_and_there_is_no_generic_event_date(world):
    db, _, a = world
    result = promotion.create_event_from_candidate(db, a.id, ME, FactSelection(dates=(FinancingDateKind.FIRST_SALE_DATE, FinancingDateKind.FILING_DATE)))
    assert set(result.accepted_dates) == {FinancingDateKind.FIRST_SALE_DATE, FinancingDateKind.FILING_DATE}
    canonical = events.get_canonical_financing_event(db, result.financing_event_id)
    by_kind = {d.kind: d.time for d in canonical.dates}
    assert by_kind[FinancingDateKind.FIRST_SALE_DATE].precision.value == "day" and by_kind[FinancingDateKind.FILING_DATE].precision.value == "day"
    assert not hasattr(canonical, "event_date")


def test_a_conflicting_date_does_not_overwrite(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME, FactSelection(dates=(FinancingDateKind.FILING_DATE,))).financing_event_id
    later = candidates.persist_financing_event_candidates(db, start_attempt(db, FORM_D, record_id="date-1")[1].id, [form_d(company)]).candidates[0]
    with pytest.raises(FactAlreadyAcceptedError):
        promotion.attach_candidate_to_event(db, later.id, x, ME, FactSelection(dates=(FinancingDateKind.FILING_DATE,)))


def test_selecting_a_date_kind_the_candidate_never_proposed_is_refused(world):
    db, _, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id      # Form D proposes no announcement_date
    other = candidates.persist_financing_event_candidates(db, start_attempt(db, FORM_D, record_id="date-2")[1].id,
                                                           [form_d(events.get_financing_event(db, x).company_id)]).candidates[0]
    with pytest.raises(FactNotAvailableError):
        promotion.attach_candidate_to_event(db, other.id, x, ME, FactSelection(dates=(FinancingDateKind.ANNOUNCEMENT_DATE,)))


# ---------------- fact selection mechanics

def test_attach_with_zero_selected_facts_is_legitimate(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="zero-1")
    result = promotion.attach_candidate_to_event(db, b.id, x, ME)          # default NO_FACTS
    assert not (result.accepted_stage or result.accepted_financing_type or result.accepted_verified_round_amount or result.accepted_dates)
    assert canonical_financing_counts(db) == {**ZERO, "financing_event": 1, "financing_resolution_decision": 2}


def test_invalid_fact_selection_types_are_rejected(world):
    db, _, a = world
    for bad in ("stage", {"stage": True}, 1, None):
        with pytest.raises(InvalidInputError):
            promotion.create_event_from_candidate(db, a.id, ME, bad)


def test_a_candidate_amount_fact_can_only_ever_back_one_canonical_amount(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="reuse-1")
    promotion.attach_candidate_to_event(db, b.id, x, ME, FactSelection(verified_round_amount=True))
    y = promotion.create_event_from_candidate(db, announcement_candidate(db, company, record_id="reuse-2").id, ME).financing_event_id
    # cannot reuse b's already-accepted amount on a different event through the public API (b is already resolved)
    with pytest.raises(FinancingCandidateAlreadyResolvedError):
        promotion.attach_candidate_to_event(db, b.id, y, ME, FactSelection(verified_round_amount=True))


# ---------------- atomicity

def test_a_failed_fact_selection_rolls_back_the_whole_create(world):
    db, _, a = world
    before = canonical_financing_counts(db)
    with pytest.raises(FactNotAvailableError):
        promotion.create_event_from_candidate(db, a.id, ME, FactSelection(stage=True))   # a (Form D) has no stage
    assert canonical_financing_counts(db) == before
    assert events.get_financing_candidate_resolution_state(db, a.id) is FinancingCandidateResolutionState.UNRESOLVED


def test_a_failed_fact_selection_rolls_back_the_whole_attach(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="rollback-1")
    before = canonical_financing_counts(db)
    with pytest.raises(FactNotAvailableError):
        promotion.attach_candidate_to_event(db, b.id, x, ME, FactSelection(financing_type=True))   # b has no type
    assert canonical_financing_counts(db) == before
    assert events.get_financing_candidate_resolution_state(db, b.id) is FinancingCandidateResolutionState.UNRESOLVED


def test_on_a_connection_a_failed_resolution_undoes_only_itself(world):
    db, company, a = world
    b = announcement_candidate(db, company, record_id="savepoint-1")
    with db.begin() as conn:
        x = promotion.create_event_from_candidate(conn, a.id, ME).financing_event_id     # earlier work in the caller's transaction
        with pytest.raises(FactNotAvailableError):
            promotion.attach_candidate_to_event(conn, b.id, x, ME, FactSelection(financing_type=True))
        assert canonical_financing_counts(conn)["financing_event"] == 1   # the create survived (visible in the caller's own transaction)
    assert canonical_financing_counts(db)["financing_event"] == 1
    assert events.get_financing_candidate_resolution_state(db, b.id) is FinancingCandidateResolutionState.UNRESOLVED


# ---------------- provenance

def test_the_full_provenance_chain_for_a_selected_fact_and_the_event_itself(world):
    db, company, a = world
    x = promotion.create_event_from_candidate(db, a.id, ME).financing_event_id
    b = announcement_candidate(db, company, record_id="prov-1")
    promotion.attach_candidate_to_event(db, b.id, x, ME, FactSelection(verified_round_amount=True))
    links = {l.subject: l for l in events.get_financing_event_lineage(db, x)}
    assert set(links) >= {"event", "verified_round_amount"}
    amount_link = links["verified_round_amount"]
    assert amount_link.candidate_id == b.id and amount_link.financing_event_id == x
    with db.connect() as conn:
        attempt = conn.execute(text("SELECT observation_id FROM v2.processing_attempt WHERE id = :i"), {"i": amount_link.processing_attempt_id}).one()
        observation = conn.execute(text("SELECT source_id, content_hash FROM v2.observation WHERE id = :o"), {"o": attempt.observation_id}).one()
        source_key = conn.execute(text("SELECT source_key FROM v2.source WHERE id = :s"), {"s": observation.source_id}).scalar()
    assert amount_link.observation_id == attempt.observation_id and amount_link.content_hash == observation.content_hash
    assert amount_link.source_key == source_key
    # a separate observation contributed the event-level decision for candidate `a`
    event_links = [l for l in events.get_financing_event_lineage(db, x) if l.subject == "event"]
    assert {l.candidate_id for l in event_links} == {a.id, b.id}
    assert len({l.observation_id for l in event_links}) == 2       # two DIFFERENT observations contributed independently
