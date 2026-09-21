"""Pure tests: authority vocabulary, decision shape, normalization policy. No database."""

import uuid
from datetime import datetime, timezone

import pytest

from app.v2.domain.candidate import IdentifierType
from app.v2.domain.company import (
    normalize_domain,
    normalize_identifier,
    normalize_name_for_blocking,
    normalize_website_url,
)
from app.v2.domain.errors import DomainError, InvalidInputError, InvariantViolationError, UnsupportedInputError
from app.v2.domain.resolution import (
    RULE_AUTHORITY,
    RULE_EXACT_IDENTIFIER_MATCH,
    Authority,
    AuthorityKind,
    CandidateResolutionState,
    DecisionKind,
    StoredResolutionDecision,
    derive_candidate_state,
    human_authority,
    names_an_ai_actor,
    rule_authority,
)
NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)


# ---------------- authority: exactly two members, AI cannot be constructed

def test_the_authority_vocabulary_is_exactly_rule_and_human():
    assert {a.value for a in AuthorityKind} == {"rule", "human"}
    assert not any("ai" in a.name.lower().split("_") for a in AuthorityKind)


@pytest.mark.parametrize("kind", ["ai", "AI", "llm", "model", "system", "agent", "", None, 1])
def test_no_api_accepts_an_ai_or_arbitrary_authority_kind(kind):
    with pytest.raises(Exception):
        Authority(kind=kind, id="admin:jerrod")


@pytest.mark.parametrize("actor", ["ai:gpt4", "admin:gpt-4", "admin:claude", "system", "bot:nightly", "admin:openai_key",
                                   "admin", "Admin:x", ":x", "admin:", "admin:has space", "a" * 200])
def test_human_actor_ids_are_bounded_opaque_shapes_and_never_name_an_ai(actor):
    with pytest.raises(InvalidInputError):
        human_authority(actor)


@pytest.mark.parametrize("rule", ["exact_identifier_match", "ai_matcher.v1", "Exact.v1", "exact.v", "x" * 200 + ".v1"])
def test_rule_ids_are_versioned_and_never_generic_or_ai(rule):
    with pytest.raises(DomainError):
        rule_authority(rule)


def test_a_well_formed_but_unregistered_rule_is_readable_history_yet_decides_nothing():
    generic = rule_authority("system.v1")
    assert not any(generic.may_decide(k) for k in DecisionKind)


def test_valid_authorities_and_permissions():
    human = human_authority("admin:jerrod")
    assert human.kind is AuthorityKind.HUMAN and all(human.may_decide(k) for k in DecisionKind)
    rule = rule_authority(RULE_EXACT_IDENTIFIER_MATCH)
    assert [k for k in DecisionKind if rule.may_decide(k)] == [DecisionKind.ATTACH_TO_COMPANY]
    assert RULE_AUTHORITY[RULE_EXACT_IDENTIFIER_MATCH] == {DecisionKind.ATTACH_TO_COMPANY}
    assert not rule_authority("retired_rule.v1").may_decide(DecisionKind.ATTACH_TO_COMPANY)   # unregistered rules decide nothing


def test_ai_name_detection_uses_tokens_not_substrings():
    assert names_an_ai_actor("admin:gpt4") and names_an_ai_actor("bot-1") and names_an_ai_actor("Claude")
    assert not names_an_ai_actor("admin:jerrod") and not names_an_ai_actor("admin:daisy") and not names_an_ai_actor("exact_identifier_match.v1")


# ---------------- decision shape and derived state

def decision(kind, *, company="00000000-0000-0000-0000-000000000001", reason=None, authority=None):
    return StoredResolutionDecision(id=1, candidate_id=1, decision_kind=kind,
                                    company_id=uuid.UUID(company) if company else None,
                                    authority=authority or human_authority("admin:jerrod"), reason_code=reason, created_at=NOW)


def test_decision_shapes():
    assert decision(DecisionKind.CREATE_COMPANY).is_final and decision(DecisionKind.ATTACH_TO_COMPANY).is_final
    assert decision(DecisionKind.REJECT_CANDIDATE, company=None, reason="not_a_company").is_final
    assert not decision(DecisionKind.DEFER_CANDIDATE, company=None, reason="needs_review").is_final
    for bad in (dict(kind=DecisionKind.REJECT_CANDIDATE, company="00000000-0000-0000-0000-000000000001", reason="x1"),
                dict(kind=DecisionKind.DEFER_CANDIDATE, company=None, reason=None),
                dict(kind=DecisionKind.CREATE_COMPANY, company=None),
                dict(kind=DecisionKind.ATTACH_TO_COMPANY, reason="x1")):
        with pytest.raises(InvariantViolationError):
            decision(bad.pop("kind"), **bad)


def test_a_rule_can_only_appear_as_an_attach():
    rule = rule_authority(RULE_EXACT_IDENTIFIER_MATCH)
    assert decision(DecisionKind.ATTACH_TO_COMPANY, authority=rule).authority.kind is AuthorityKind.RULE
    for kind, company, reason in ((DecisionKind.CREATE_COMPANY, "00000000-0000-0000-0000-000000000001", None),
                                  (DecisionKind.REJECT_CANDIDATE, None, "nope_1")):
        with pytest.raises(InvariantViolationError):
            decision(kind, company=company, reason=reason, authority=rule)


def test_resolution_state_is_derived_from_history_and_contradictions_are_refused():
    K = DecisionKind
    assert derive_candidate_state([]) is CandidateResolutionState.UNRESOLVED
    assert derive_candidate_state([K.DEFER_CANDIDATE, K.DEFER_CANDIDATE]) is CandidateResolutionState.DEFERRED
    assert derive_candidate_state([K.DEFER_CANDIDATE, K.CREATE_COMPANY]) is CandidateResolutionState.COMPANY_CREATED
    assert derive_candidate_state([K.ATTACH_TO_COMPANY]) is CandidateResolutionState.ATTACHED
    assert derive_candidate_state([K.REJECT_CANDIDATE]) is CandidateResolutionState.REJECTED
    with pytest.raises(InvariantViolationError):
        derive_candidate_state([K.CREATE_COMPANY, K.REJECT_CANDIDATE])


# ---------------- normalization policy (documented in app.v2.domain.company)

@pytest.mark.parametrize("raw, expected", [
    ("Example.com", "example.com"), ("example.com", "example.com"), ("www.example.com", "example.com"),
    ("WWW.Example.COM.", "example.com"), ("app.example.com", "app.example.com"), ("www.app.example.com", "app.example.com"),
    ("www.com", "www.com"), ("wwwexample.com", "wwwexample.com"), ("www.www.example.com", "www.example.com"),
    ("example.co.uk", "example.co.uk"), ("xn--bcher-kva.example", "xn--bcher-kva.example"),
])
def test_domain_normalization(raw, expected):
    assert normalize_domain(raw) == expected == normalize_identifier(IdentifierType.DOMAIN, raw)


@pytest.mark.parametrize("bad", ["", "not a domain", "localhost", "example..com", "-a.com", "http://example.com", "exa mple.com", None, 5])
def test_invalid_domains_are_refused(bad):
    with pytest.raises(DomainError):
        normalize_domain(bad)


@pytest.mark.parametrize("raw, expected", [
    ("https://example.com", "https://example.com/"), ("HTTPS://Example.COM/Path", "https://example.com/Path"),
    ("https://www.example.com/", "https://www.example.com/"),                 # www is kept in URLs
    ("http://example.com/", "http://example.com/"),                           # http is not upgraded
    ("https://example.com:443/a", "https://example.com/a"), ("http://example.com:80", "http://example.com/"),
    ("https://example.com:8443/a", "https://example.com:8443/a"), ("http://example.com:443/", "http://example.com:443/"),
    ("https://example.com/a#frag", "https://example.com/a"), ("https://example.com/a/", "https://example.com/a/"),
    ("https://example.com/A?Q=1&b=2", "https://example.com/A?Q=1&b=2"), ("https://example.com?x=1", "https://example.com/?x=1"),
    ("https://example.com/?", "https://example.com/"),
])
def test_website_url_normalization_is_minimal(raw, expected):
    assert normalize_website_url(raw) == expected == normalize_identifier(IdentifierType.WEBSITE_URL, raw)


@pytest.mark.parametrize("bad", ["ftp://example.com", "https://user:pw@example.com", "https://[::1]/", "https://", "example.com",
                                 "https://exa mple.com", "javascript:alert(1)", None])
def test_invalid_or_unsupported_urls_are_refused(bad):
    with pytest.raises((InvalidInputError, UnsupportedInputError)):
        normalize_website_url(bad)


def test_normalization_is_idempotent():
    for raw in ("WWW.Example.com.", "www.a.b.c", "www.com"):
        once = normalize_domain(raw)
        assert normalize_domain(once) == once
    for raw in ("HTTPS://Www.Example.com:443/A?b=1#f", "http://x.io:80"):
        once = normalize_website_url(raw)
        assert normalize_website_url(once) == once


def test_name_blocking_is_a_search_aid_and_never_an_identifier_type():
    assert normalize_name_for_blocking("Acme") == normalize_name_for_blocking("Acme Inc.") == normalize_name_for_blocking("ACME") == "acme"
    assert {t.value for t in IdentifierType} == {"domain", "website_url"}                    # names are not identifiers
