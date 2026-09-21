"""The promotion boundary through the real repositories: human authority, the exact-identifier rule, atomicity,
provenance, and the layers that must never change."""

import pytest
from sqlalchemy import text

from app.v2.domain.candidate import IdentifierType
from app.v2.domain.errors import InvalidInputError, InvariantViolationError
from app.v2.domain.resolution import (
    RULE_EXACT_IDENTIFIER_MATCH,
    Authority,
    AuthorityKind,
    CandidateResolutionState,
    DecisionKind,
    human_authority,
    rule_authority,
)
from app.v2.repositories import company_candidates as candidates
from app.v2.repositories import companies
from app.v2.repositories.errors import NotFoundError
from app.v2.resolution import promotion, rules
from app.v2.resolution.errors import CandidateAlreadyResolvedError, IdentifierConflictError
from app.v2.resolution.rules import RuleOutcomeKind
from app.v2.tests.db.resolution_helpers import HUMAN, canonical_counts, make_candidate, untouched_snapshot

pytestmark = pytest.mark.db

ME = human_authority(HUMAN)
RULE = rule_authority(RULE_EXACT_IDENTIFIER_MATCH)
ZERO = {"company": 0, "resolution_decision": 0, "company_name": 0, "company_identifier": 0}


def acme(db, **kw):
    return make_candidate(db, "Acme Robotics, Inc.", domain="acmerobotics.com", url="https://www.acmerobotics.com", **kw)


# ---------------- nothing is canonical until a decision says so

def test_a_valid_candidate_creates_nothing_canonical_by_itself(migrated_db):
    candidate = acme(migrated_db)
    assert canonical_counts(migrated_db) == ZERO
    assert companies.get_candidate_resolution_state(migrated_db, candidate.id) is CandidateResolutionState.UNRESOLVED


# ---------------- human create

def test_a_human_creates_a_company_from_a_candidate_atomically(migrated_db):
    db = migrated_db
    candidate = acme(db)
    before = untouched_snapshot(db)
    result = promotion.create_company_from_candidate(db, candidate.id, ME)
    assert result.decision.decision_kind is DecisionKind.CREATE_COMPANY and result.company_id is not None
    assert result.decision.authority == ME and result.decision.candidate_id == candidate.id     # actor preserved
    assert canonical_counts(db) == {"company": 1, "resolution_decision": 1, "company_name": 1, "company_identifier": 2}
    company = companies.get_company(db, result.company_id)
    assert company is not None and company.created_at.tzinfo is not None
    (name,) = companies.list_company_names(db, company.id)
    assert (name.name, name.name_role.value, name.resolution_decision_id) == ("Acme Robotics, Inc.", "canonical", result.decision.id)
    idents = {(i.identifier_type, i.identifier_value) for i in companies.list_company_identifiers(db, company.id)}
    assert idents == {(IdentifierType.DOMAIN, "acmerobotics.com"), (IdentifierType.WEBSITE_URL, "https://www.acmerobotics.com/")}
    assert companies.get_candidate_resolution_state(db, candidate.id) is CandidateResolutionState.COMPANY_CREATED
    assert untouched_snapshot(db) == before                                                        # candidate, attempt, evidence unchanged
    assert candidates.get_company_candidate(db, candidate.id) == candidate


def test_a_company_id_is_database_generated_and_names_are_not_identity(migrated_db):
    db = migrated_db
    a = promotion.create_company_from_candidate(db, make_candidate(db, "Same Name").id, ME)
    b = promotion.create_company_from_candidate(db, make_candidate(db, "Same Name").id, ME)       # same name: a different company
    assert a.company_id != b.company_id and canonical_counts(db)["company"] == 2
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM v2.company_name WHERE name = 'Same Name'")).scalar() == 2


def test_a_create_that_conflicts_on_an_identifier_rolls_back_everything(migrated_db):
    db = migrated_db
    promotion.create_company_from_candidate(db, acme(db).id, ME)
    other = make_candidate(db, "Acme Robotics International", domain="www.acmerobotics.com", domain_needle=b"www.acmerobotics.com")
    before = canonical_counts(db)
    with pytest.raises(IdentifierConflictError):
        promotion.create_company_from_candidate(db, other.id, ME)
    assert canonical_counts(db) == before                                                        # no half-promoted Company
    assert companies.get_candidate_resolution_state(db, other.id) is CandidateResolutionState.UNRESOLVED


def test_a_candidate_cannot_be_resolved_twice(migrated_db):
    db = migrated_db
    candidate = acme(db)
    promotion.create_company_from_candidate(db, candidate.id, ME)
    for attempt in (lambda: promotion.create_company_from_candidate(db, candidate.id, ME),
                    lambda: promotion.reject_candidate(db, candidate.id, ME, "changed_mind"),
                    lambda: promotion.defer_candidate(db, candidate.id, ME, "later")):
        with pytest.raises(CandidateAlreadyResolvedError):
            attempt()
    assert canonical_counts(db) == {"company": 1, "resolution_decision": 1, "company_name": 1, "company_identifier": 2}


def test_unknown_candidates_and_invalid_ids_are_refused(migrated_db):
    with pytest.raises(NotFoundError):
        promotion.create_company_from_candidate(migrated_db, 999999, ME)
    for bad in (0, -1, True, "1", None):
        with pytest.raises(InvalidInputError):
            promotion.create_company_from_candidate(migrated_db, bad, ME)


# ---------------- human attach

def test_a_human_attaches_a_candidate_and_accepts_only_what_is_new(migrated_db):
    db = migrated_db
    company_id = promotion.create_company_from_candidate(db, acme(db).id, ME).company_id
    other = make_candidate(db, "Acme Robotics", domain="acmerobotics.io")                       # a new alias and one new identifier
    result = promotion.attach_candidate_to_company(db, other.id, company_id, ME)
    assert (result.company_id, result.accepted_name, result.accepted_identifier_count) == (company_id, True, 1)
    assert [(n.name, n.name_role.value) for n in companies.list_company_names(db, company_id)] == [
        ("Acme Robotics, Inc.", "canonical"), ("Acme Robotics", "alias")]
    assert canonical_counts(db) == {"company": 1, "resolution_decision": 2, "company_name": 2, "company_identifier": 3}
    assert companies.get_candidate_resolution_state(db, other.id) is CandidateResolutionState.ATTACHED


def test_attaching_to_a_missing_company_or_across_owned_identifiers_is_refused_with_no_merge(migrated_db):
    db = migrated_db
    first = promotion.create_company_from_candidate(db, make_candidate(db, "One Co", domain="one.example").id, ME).company_id
    second = promotion.create_company_from_candidate(db, make_candidate(db, "Two Co", domain="two.example").id, ME).company_id
    bridging = make_candidate(db, "One Two Co", domain="one.example")                            # its identifier belongs to `first`
    before = canonical_counts(db)
    with pytest.raises(IdentifierConflictError):
        promotion.attach_candidate_to_company(db, bridging.id, second, ME)                      # ...so it cannot join `second`
    assert canonical_counts(db) == before
    import uuid
    with pytest.raises(NotFoundError):
        promotion.attach_candidate_to_company(db, bridging.id, uuid.uuid4(), ME)
    promotion.attach_candidate_to_company(db, bridging.id, first, ME)                           # the same owner: fine
    assert canonical_counts(db)["company"] == 2                                                   # never merged


# ---------------- reject / defer

def test_reject_and_defer_record_the_actor_and_reason_and_change_nothing_else(migrated_db):
    db = migrated_db
    candidate = acme(db)
    before = untouched_snapshot(db)
    deferred = promotion.defer_candidate(db, candidate.id, ME, "needs_second_source")
    assert deferred.company_id is None and not deferred.decision.is_final and deferred.decision.reason_code == "needs_second_source"
    assert companies.get_candidate_resolution_state(db, candidate.id) is CandidateResolutionState.DEFERRED
    promotion.defer_candidate(db, candidate.id, human_authority("admin:other"), "still_unsure")   # deferral is not final
    rejected = promotion.reject_candidate(db, candidate.id, ME, "not_a_company")
    assert rejected.decision.authority == ME and rejected.decision.is_final
    assert companies.get_candidate_resolution_state(db, candidate.id) is CandidateResolutionState.REJECTED
    assert [d.decision_kind for d in companies.list_decisions_for_candidate(db, candidate.id)] == [
        DecisionKind.DEFER_CANDIDATE, DecisionKind.DEFER_CANDIDATE, DecisionKind.REJECT_CANDIDATE]
    assert canonical_counts(db) == {"company": 0, "resolution_decision": 3, "company_name": 0, "company_identifier": 0}
    assert untouched_snapshot(db) == before


def test_a_later_final_decision_may_follow_a_deferral(migrated_db):
    db = migrated_db
    candidate = acme(db)
    promotion.defer_candidate(db, candidate.id, ME, "later")
    assert promotion.create_company_from_candidate(db, candidate.id, ME).company_id is not None


def test_reasons_are_required_and_shaped(migrated_db):
    candidate = acme(migrated_db)
    for bad in ("", "Has Spaces", "x", None):
        with pytest.raises(InvalidInputError):
            promotion.reject_candidate(migrated_db, candidate.id, ME, bad)
    assert canonical_counts(migrated_db) == ZERO


# ---------------- authority

def test_only_humans_may_create_reject_or_defer_and_rules_only_attach(migrated_db):
    db = migrated_db
    candidate = acme(db)
    for call in (lambda: promotion.create_company_from_candidate(db, candidate.id, RULE),
                 lambda: promotion.reject_candidate(db, candidate.id, RULE, "no_reason"),
                 lambda: promotion.defer_candidate(db, candidate.id, RULE, "no_reason")):
        with pytest.raises(InvariantViolationError) as info:
            call()
        assert info.value.code == "authority_exceeded"                                             # refused by the service, before the database
    assert canonical_counts(db) == ZERO


@pytest.mark.parametrize("fake", ["ai", "human", None, {"kind": "ai", "id": "x"}, object()])
def test_no_promotion_api_accepts_anything_but_a_real_authority(migrated_db, fake):
    candidate = acme(migrated_db)
    for call in (lambda: promotion.create_company_from_candidate(migrated_db, candidate.id, fake),
                 lambda: promotion.reject_candidate(migrated_db, candidate.id, fake, "why_not"),
                 lambda: promotion.defer_candidate(migrated_db, candidate.id, fake, "why_not")):
        with pytest.raises(InvalidInputError):
            call()
    assert canonical_counts(migrated_db) == ZERO


def test_a_forged_authority_that_skips_validation_is_still_refused(migrated_db):
    candidate = acme(migrated_db)
    forged = Authority.model_construct(kind="ai", id="admin:jerrod")                               # bypasses validators
    forged_id = Authority.model_construct(kind=AuthorityKind.HUMAN, id="ai:gpt")
    for authority in (forged, forged_id):
        with pytest.raises(InvalidInputError):
            promotion.create_company_from_candidate(migrated_db, candidate.id, authority)
    assert canonical_counts(migrated_db) == ZERO


def test_the_promotion_api_has_no_generic_or_confidence_driven_entry_point():
    import inspect
    public = {n for n, f in vars(promotion).items() if inspect.isfunction(f) and not n.startswith("_") and f.__module__ == promotion.__name__}
    assert public == {"create_company_from_candidate", "attach_candidate_to_company", "reject_candidate", "defer_candidate"}
    for fn in (promotion.create_company_from_candidate, promotion.attach_candidate_to_company, promotion.reject_candidate,
               promotion.defer_candidate, rules.resolve_by_exact_identifier):
        assert not {"confidence", "score", "model", "action", "kind"} & set(inspect.signature(fn).parameters)


# ---------------- the exact-identifier rule

def test_the_rule_attaches_on_an_exact_normalized_identifier_match_and_records_its_id(migrated_db):
    db = migrated_db
    company_id = promotion.create_company_from_candidate(db, acme(db).id, ME).company_id
    later = make_candidate(db, "Different Display Name", domain="www.acmerobotics.com", domain_needle=b"www.acmerobotics.com")
    before = canonical_counts(db)
    outcome = rules.resolve_by_exact_identifier(db, later.id)
    assert outcome.kind is RuleOutcomeKind.ATTACHED and outcome.company_id == company_id
    decision = outcome.decision
    assert (decision.authority.kind, decision.authority.id) == (AuthorityKind.RULE, "exact_identifier_match.v1")
    assert decision.decision_kind is DecisionKind.ATTACH_TO_COMPANY
    after = canonical_counts(db)
    assert after == {**before, "resolution_decision": before["resolution_decision"] + 1}          # a rule accepts no new facts
    assert companies.get_candidate_resolution_state(db, later.id) is CandidateResolutionState.ATTACHED


def test_the_rule_never_matches_on_name_alone(migrated_db):
    db = migrated_db
    promotion.create_company_from_candidate(db, make_candidate(db, "Acme", domain="acme.example").id, ME)
    for name in ("Acme", "Acme Inc.", "ACME"):
        candidate = make_candidate(db, name)                                                        # no identifiers at all
        before = canonical_counts(db)
        outcome = rules.resolve_by_exact_identifier(db, candidate.id)
        assert outcome.kind is RuleOutcomeKind.NO_IDENTIFIER_MATCH and outcome.decision is None
        assert canonical_counts(db) == before                                                       # writes nothing when it does not decide
        assert companies.get_candidate_resolution_state(db, candidate.id) is CandidateResolutionState.UNRESOLVED


def test_the_rule_does_not_match_different_or_only_related_identifiers(migrated_db):
    db = migrated_db
    promotion.create_company_from_candidate(db, make_candidate(db, "Acme", domain="acme.example").id, ME)
    for domain in ("app.acme.example", "acme.example.org", "notacme.example"):
        outcome = rules.resolve_by_exact_identifier(db, make_candidate(db, "Acme", domain=domain).id)
        assert outcome.kind is RuleOutcomeKind.NO_IDENTIFIER_MATCH


def test_the_rule_refuses_ambiguous_identifiers_and_a_human_must_decide(migrated_db):
    db = migrated_db
    a = promotion.create_company_from_candidate(db, make_candidate(db, "One Co", domain="one.example").id, ME).company_id
    b = promotion.create_company_from_candidate(db, make_candidate(db, "Two Co", domain="two.example").id, ME).company_id
    both = make_candidate(db, "One and Two", domain="one.example", url="https://two.example")   # identifiers of two DIFFERENT companies
    promotion.attach_candidate_to_company(db, make_candidate(db, "Two url", url="https://two.example").id, b, ME)
    before = canonical_counts(db)
    outcome = rules.resolve_by_exact_identifier(db, both.id)
    assert outcome.kind is RuleOutcomeKind.AMBIGUOUS_IDENTIFIERS and outcome.decision is None and canonical_counts(db) == before
    assert a != b


def test_the_rule_does_not_reresolve_and_a_missing_candidate_is_an_error(migrated_db):
    db = migrated_db
    candidate = acme(db)
    promotion.create_company_from_candidate(db, candidate.id, ME)
    assert rules.resolve_by_exact_identifier(db, candidate.id).kind is RuleOutcomeKind.ALREADY_RESOLVED
    with pytest.raises(NotFoundError):
        rules.resolve_by_exact_identifier(db, 424242)


def test_the_rule_cannot_be_used_to_attach_without_a_match_even_when_called_directly(migrated_db):
    db = migrated_db
    company_id = promotion.create_company_from_candidate(db, make_candidate(db, "One Co", domain="one.example").id, ME).company_id
    unrelated = make_candidate(db, "One Co", domain="elsewhere.example")
    before = canonical_counts(db)
    with pytest.raises(InvariantViolationError):                                                    # the database re-verifies the match
        promotion.attach_candidate_to_company(db, unrelated.id, company_id, RULE)
    assert canonical_counts(db) == before


# ---------------- provenance

def test_the_full_provenance_chain_is_reconstructable(migrated_db):
    db = migrated_db
    candidate = acme(db)
    company_id = promotion.create_company_from_candidate(db, candidate.id, ME).company_id
    links = companies.get_company_lineage(db, company_id)
    assert sorted(l.fact_kind for l in links) == ["identifier", "identifier", "name"]
    with db.connect() as conn:
        attempt = conn.execute(text("SELECT id, observation_id FROM v2.processing_attempt WHERE id = :a"),
                               {"a": candidate.processing_attempt_id}).one()
        observation = conn.execute(text("SELECT id, source_id, content_hash FROM v2.observation WHERE id = :o"), {"o": attempt.observation_id}).one()
        source_key = conn.execute(text("SELECT source_key FROM v2.source WHERE id = :s"), {"s": observation.source_id}).scalar()
        payload_exists = conn.execute(text("SELECT count(*) FROM v2.raw_payload WHERE content_hash = :h"), {"h": observation.content_hash}).scalar()
    for link in links:
        assert link.company_id == company_id and link.candidate_id == candidate.id
        assert link.processing_attempt_id == attempt.id and link.observation_id == observation.id
        assert link.content_hash == observation.content_hash and link.source_id == observation.source_id and link.source_key == source_key
        assert link.resolution_decision_id == companies.list_decisions_for_candidate(db, candidate.id)[0].id
    assert payload_exists == 1


def test_provenance_survives_an_attach_from_a_different_source_observation(migrated_db):
    db = migrated_db
    company_id = promotion.create_company_from_candidate(db, make_candidate(db, "One Co", domain="one.example").id, ME).company_id
    second = make_candidate(db, "One Company", domain="one.example", url="https://one.example/about")
    promotion.attach_candidate_to_company(db, second.id, company_id, ME)
    by_candidate = {(l.fact_kind, l.candidate_id) for l in companies.get_company_lineage(db, company_id)}
    assert ("name", second.id) in by_candidate and ("identifier", second.id) in by_candidate       # the alias traces to ITS candidate


def test_reads_and_the_derived_state_never_write(migrated_db):
    db = migrated_db
    candidate = acme(db)
    before = (canonical_counts(db), untouched_snapshot(db))
    companies.get_candidate_resolution_state(db, candidate.id)
    companies.list_decisions_for_candidate(db, candidate.id)
    assert (canonical_counts(db), untouched_snapshot(db)) == before
