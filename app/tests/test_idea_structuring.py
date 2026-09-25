"""
Regression tests for Idea Lab Phase 6.1 -- AI-Assisted Idea Setup:
app/ai/idea_structuring.py's structure_idea()/_sanitize_draft() safety
filter, and POST /ventures/structure-idea in app/api.py.

No test here makes a real LLM call -- app.ai.idea_structuring._call_llm
is monkeypatched to return controlled, deterministic fake responses
(matching this repo's established "mock the LLM, hit the real DB"
convention, e.g. test_analyze_unified.py). This is actually STRONGER
coverage for the safety-critical paths than relying on a real LLM's
variable output: the adversarial-response tests below construct exactly
the failure mode Phase 6.1's core safety rule forbids (a fabricated
"ai_inferred" validation number) and assert the sanitizer strips it,
regardless of what any given LLM call would have actually returned.

Run with:
    python -m app.tests.test_idea_structuring
"""

from fastapi.testclient import TestClient

import app.ai.idea_structuring as idea_structuring
import app.api as api
from app.ai.idea_structuring import IdeaStructuringError, structure_idea
from app.ai.vps_scoring import compute_vps
from app.database.db import engine, get_rankings, discover_startups
from sqlalchemy import text

# Reuse the exact same JWT-mocking harness as test_backend_authentication.py
import time
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_USER = "zztest_idea_structuring_user"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_public_key)


def _make_token(sub: str = TEST_USER, exp_delta: int = 3600) -> str:
    now = int(time.time())
    payload = {"sub": sub, "iss": TEST_ISSUER, "azp": TEST_AZP, "iat": now, "exp": now + exp_delta}
    return pyjwt.encode(payload, _private_key, algorithm="RS256")


class _patched_auth:
    def __enter__(self):
        import app.auth as auth
        self._auth = auth
        self._orig_issuer = auth.CLERK_ISSUER
        self._orig_jwks_client = auth._jwks_client
        self._orig_resolve_parties = auth._resolve_authorized_parties
        auth.CLERK_ISSUER = TEST_ISSUER
        auth._jwks_client = lambda: _FakeJWKSClient()
        auth._resolve_authorized_parties = lambda: [TEST_AZP]
        return self

    def __exit__(self, *exc):
        self._auth.CLERK_ISSUER = self._orig_issuer
        self._auth._jwks_client = self._orig_jwks_client
        self._auth._resolve_authorized_parties = self._orig_resolve_parties
        return False


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token()}"}


class _patched_llm:
    """Monkeypatches app.ai.idea_structuring._call_llm to return a fixed
    dict instead of making a real OpenAI call."""

    def __init__(self, fake_response):
        self.fake_response = fake_response

    def __enter__(self):
        self._original = idea_structuring._call_llm
        idea_structuring._call_llm = lambda description: self.fake_response
        return self

    def __exit__(self, *exc):
        idea_structuring._call_llm = self._original
        return False


class _patched_llm_raises:
    def __enter__(self):
        self._original = idea_structuring._call_llm

        def _raise(description):
            raise RuntimeError("simulated provider outage")

        idea_structuring._call_llm = _raise
        return self

    def __exit__(self, *exc):
        idea_structuring._call_llm = self._original
        return False


DESCRIPTION = "I want to build an AI bookkeeping tool for independent construction contractors."


def _field(value, provenance, source_quote=None):
    return {"value": value, "provenance": provenance, "source_quote": source_quote}


def _minimal_fake_response(**overrides) -> dict:
    """A well-formed, mostly-empty response -- every field defaults to
    unknown/null unless overridden."""
    base = {
        "name": _field(None, "unknown"),
        "industry": _field(None, "unknown"),
        "business_model": _field(None, "unknown"),
        "target_customer": _field(None, "unknown"),
        "stage": _field(None, "unknown"),
        "market": {
            "market_description": _field(None, "unknown"),
            "estimated_market_size": _field(None, "unknown"),
            "competition_intensity": _field(None, "unknown"),
        },
        "problem_solution": {
            "problem_statement": _field(None, "unknown"),
            "solution_description": _field(None, "unknown"),
            "differentiation": _field(None, "unknown"),
        },
        "founder": {
            "founder_count": _field(None, "unknown"),
            "relevant_domain_experience_years": _field(None, "unknown"),
            "has_technical_cofounder": _field(None, "unknown"),
            "has_business_cofounder": _field(None, "unknown"),
        },
        "gtm": {
            "primary_acquisition_strategy": _field(None, "unknown"),
            "expected_cac": _field(None, "unknown"),
        },
        "economics": {
            "pricing_model": _field(None, "unknown"),
            "price_point": _field(None, "unknown"),
            "expected_gross_margin_pct": _field(None, "unknown"),
        },
        "validation": {
            "customer_interviews": _field(None, "unknown"),
            "waitlist_signups": _field(None, "unknown"),
            "paying_customers": _field(None, "unknown"),
            "monthly_revenue": _field(None, "unknown"),
        },
        "capital": {
            "starting_capital": _field(None, "unknown"),
            "monthly_burn": _field(None, "unknown"),
        },
    }
    base.update(overrides)
    return base


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM modeled_ventures WHERE user_id = :u"), {"u": TEST_USER})
        connection.execute(text("DELETE FROM users WHERE id = :u"), {"u": TEST_USER})


# --- 1: idea description -> typed structured draft --------------------------


def test_idea_description_produces_typed_structured_draft() -> None:
    fake = _minimal_fake_response(
        industry=_field("Construction Tech", "ai_inferred"),
        target_customer=_field("Independent construction contractors", "user_provided", "construction contractors"),
    )
    with _patched_llm(fake):
        draft = structure_idea(DESCRIPTION)

    expect(draft["industry"]["value"] == "Construction Tech", "Expected the inferred industry to survive sanitization")
    expect(draft["target_customer"]["provenance"] == "user_provided", "Expected user_provided target_customer")


# --- 2-4: structuring endpoint has zero side effects -------------------------


def test_structuring_endpoint_creates_no_database_row() -> None:
    fake = _minimal_fake_response()
    with _patched_llm(fake), _patched_auth():
        with engine.begin() as connection:
            before = connection.execute(text("SELECT COUNT(*) FROM modeled_ventures")).scalar()

        response = client.post("/ventures/structure-idea", json={"description": DESCRIPTION}, headers=_auth_headers())
        expect(response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}")

        with engine.begin() as connection:
            after = connection.execute(text("SELECT COUNT(*) FROM modeled_ventures")).scalar()

        expect(after == before, "structure-idea must never create a modeled_ventures row")


def test_structuring_endpoint_never_computes_vps() -> None:
    fake = _minimal_fake_response()
    with _patched_llm(fake), _patched_auth():
        response = client.post("/ventures/structure-idea", json={"description": DESCRIPTION}, headers=_auth_headers())
        body = response.json()

    expect("vps" not in body["draft"], "The draft response must never contain a vps field")
    expect(
        "model_result" not in body,
        "The structuring response must never contain a model_result -- that's compute_vps()'s own output shape",
    )


def test_structuring_endpoint_creates_no_analyses_row() -> None:
    fake = _minimal_fake_response()
    with engine.begin() as connection:
        before = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()

    with _patched_llm(fake), _patched_auth():
        client.post("/ventures/structure-idea", json={"description": DESCRIPTION}, headers=_auth_headers())

    with engine.begin() as connection:
        after = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()

    expect(after == before, "structure-idea must never create an analyses row (no SPS path)")


# --- 5-7: provenance handling ------------------------------------------------


def test_user_provided_facts_preserve_provenance() -> None:
    fake = _minimal_fake_response(
        target_customer=_field("construction contractors", "user_provided", "construction contractors"),
    )
    with _patched_llm(fake):
        draft = structure_idea(DESCRIPTION)

    expect(draft["target_customer"]["provenance"] == "user_provided", "Verified quote must preserve user_provided")
    expect(draft["target_customer"]["value"] == "construction contractors", "Value must be preserved")


def test_inferred_assumptions_preserve_inferred_provenance() -> None:
    fake = _minimal_fake_response(
        economics={
            "pricing_model": _field("Subscription", "ai_inferred"),
            "price_point": _field(None, "unknown"),
            "expected_gross_margin_pct": _field(None, "unknown"),
        }
    )
    with _patched_llm(fake):
        draft = structure_idea(DESCRIPTION)

    expect(draft["economics"]["pricing_model"]["provenance"] == "ai_inferred", "Non-validation ai_inferred must survive")
    expect(draft["economics"]["pricing_model"]["value"] == "Subscription", "Inferred value must be preserved")


def test_unsupported_fields_remain_null() -> None:
    fake = _minimal_fake_response()  # everything unknown/null
    with _patched_llm(fake):
        draft = structure_idea(DESCRIPTION)

    expect(draft["founder"]["founder_count"]["value"] is None, "Unsupported field must stay null")
    expect(draft["founder"]["founder_count"]["provenance"] == "unknown", "Unsupported field must be 'unknown'")


# --- 8-10: validation fields cannot be inferred ------------------------------


def test_paying_customers_cannot_be_inferred() -> None:
    # Adversarial: the fake LLM tries to claim ai_inferred with a real
    # number, exactly the failure mode Phase 6.1 forbids.
    fake = _minimal_fake_response(
        validation={
            "customer_interviews": _field(None, "unknown"),
            "waitlist_signups": _field(None, "unknown"),
            "paying_customers": _field(5, "ai_inferred"),
            "monthly_revenue": _field(None, "unknown"),
        }
    )
    with _patched_llm(fake):
        draft = structure_idea(DESCRIPTION)

    expect(draft["validation"]["paying_customers"]["value"] is None, "An inferred paying_customers claim must be stripped to null")
    expect(draft["validation"]["paying_customers"]["provenance"] == "unknown", "Must be forced to 'unknown'")


def test_revenue_cannot_be_inferred() -> None:
    fake = _minimal_fake_response(
        validation={
            "customer_interviews": _field(None, "unknown"),
            "waitlist_signups": _field(None, "unknown"),
            "paying_customers": _field(None, "unknown"),
            "monthly_revenue": _field(10000, "ai_inferred"),
        }
    )
    with _patched_llm(fake):
        draft = structure_idea(DESCRIPTION)

    expect(draft["validation"]["monthly_revenue"]["value"] is None, "An inferred revenue claim must be stripped to null")


def test_customer_interviews_cannot_be_inferred() -> None:
    fake = _minimal_fake_response(
        validation={
            "customer_interviews": _field(20, "ai_inferred"),
            "waitlist_signups": _field(None, "unknown"),
            "paying_customers": _field(None, "unknown"),
            "monthly_revenue": _field(None, "unknown"),
        }
    )
    with _patched_llm(fake):
        draft = structure_idea(DESCRIPTION)

    expect(draft["validation"]["customer_interviews"]["value"] is None, "An inferred interview count must be stripped to null")


# --- 10b: Phase 26, Part 14 -- "name" can never be inferred ------------------


def test_venture_name_cannot_be_inferred() -> None:
    # Adversarial: the fake LLM tries to invent a plausible-sounding brand
    # name as "ai_inferred" -- exactly the failure mode Part 14 forbids
    # ("Do not invent a brand name from the idea unless explicitly
    # requested"). This must be stripped just like an inferred
    # paying_customers/customer_interviews claim above, even though
    # "name" isn't in the validation group.
    fake = _minimal_fake_response(name=_field("ContractorBooks AI", "ai_inferred"))
    with _patched_llm(fake):
        draft = structure_idea(DESCRIPTION)

    expect(draft["name"]["value"] is None, "An inferred venture name must be stripped to null")
    expect(draft["name"]["provenance"] == "unknown", "Must be forced to 'unknown', never a guessed brand name")


def test_venture_name_preserved_when_explicitly_stated() -> None:
    description = "ContractorBooks is an AI bookkeeping tool for independent construction contractors."
    fake = _minimal_fake_response(name=_field("ContractorBooks", "user_provided", "ContractorBooks"))
    with _patched_llm(fake):
        draft = structure_idea(description)

    expect(draft["name"]["value"] == "ContractorBooks", "An explicitly stated, verifiable name must be preserved")
    expect(draft["name"]["provenance"] == "user_provided", "Must keep user_provided provenance")


# --- 11: explicitly stated validation CAN be preserved -----------------------


def test_explicitly_stated_validation_is_preserved_when_quote_verifies() -> None:
    description = "I have already talked to 12 contractors about this idea."
    fake = _minimal_fake_response(
        validation={
            "customer_interviews": _field(12, "user_provided", "talked to 12 contractors"),
            "waitlist_signups": _field(None, "unknown"),
            "paying_customers": _field(None, "unknown"),
            "monthly_revenue": _field(None, "unknown"),
        }
    )
    with _patched_llm(fake):
        draft = structure_idea(description)

    expect(draft["validation"]["customer_interviews"]["value"] == 12, "A verified user_provided claim must be preserved")
    expect(draft["validation"]["customer_interviews"]["provenance"] == "user_provided", "Provenance must remain user_provided")


def test_unverifiable_user_provided_claim_is_stripped() -> None:
    """The LLM claims 'user_provided' but the quote is fabricated -- does
    not actually appear in the founder's text. This is the failure mode
    a prompt instruction alone cannot prevent; the independent quote
    verification is what catches it."""
    fake = _minimal_fake_response(
        validation={
            "customer_interviews": _field(None, "unknown"),
            "waitlist_signups": _field(None, "unknown"),
            "paying_customers": _field(7, "user_provided", "we already have 7 paying customers"),
            "monthly_revenue": _field(None, "unknown"),
        }
    )
    with _patched_llm(fake):
        draft = structure_idea(DESCRIPTION)  # DESCRIPTION does NOT mention any paying customers

    expect(
        draft["validation"]["paying_customers"]["value"] is None,
        "An unverifiable 'user_provided' claim (fabricated quote) must be stripped to null",
    )


# --- 12-13: safe failure on malformed/failed LLM responses ------------------


def test_malformed_llm_response_fails_safely() -> None:
    # The LLM returned syntactically valid JSON, but not a JSON object at
    # all (e.g. a bare string or list) -- structure_idea() must reject
    # this itself rather than let a downstream .get() call blow up with
    # an unhandled AttributeError.
    with _patched_llm("this is not a JSON object"), _patched_auth():
        response = client.post("/ventures/structure-idea", json={"description": DESCRIPTION}, headers=_auth_headers())

    expect(response.status_code == 502, f"Expected 502, got {response.status_code}")
    expect(
        "AttributeError" not in response.text and "Traceback" not in response.text,
        "A malformed response must never leak a raw Python exception",
    )


def test_provider_failure_fails_safely() -> None:
    with _patched_llm_raises(), _patched_auth():
        response = client.post("/ventures/structure-idea", json={"description": DESCRIPTION}, headers=_auth_headers())

    expect(response.status_code == 502, f"Expected 502, got {response.status_code}")
    expect(response.json()["detail"] == "We couldn't structure that idea right now. Please try again.", "Expected the generic safe message")


# --- 14-15: auth + input bounds ----------------------------------------------


def test_unauthenticated_structuring_request_rejected() -> None:
    with _patched_auth():
        response = client.post("/ventures/structure-idea", json={"description": DESCRIPTION})
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")


def test_oversized_and_empty_input_rejected() -> None:
    # Phase 35D-A §20: StructureIdeaRequest.description's max_length was
    # intentionally raised from 4000 to 8000 during the SIE Intelligence
    # Reset (see app/models/idea_lab.py's own comment on the field --
    # the ApexGrid regression case, real evidence silently truncated at
    # exactly 4000 characters). This test's threshold was never updated
    # to match, so it asserted a 422 at 4001 chars that the current,
    # intentional contract correctly accepts (200) -- a stale test, not a
    # product regression. Updated to exercise the actual current
    # boundary: 8000 is accepted, 8001 is rejected.
    with _patched_auth():
        empty = client.post("/ventures/structure-idea", json={"description": ""}, headers=_auth_headers())
        expect(empty.status_code == 422, f"Expected 422 for empty description, got {empty.status_code}")

        # 8000 chars must clear request validation and reach the (mocked)
        # LLM call -- never a real network call in this test suite.
        fake = _minimal_fake_response()
        with _patched_llm(fake):
            at_limit = client.post("/ventures/structure-idea", json={"description": "x" * 8000}, headers=_auth_headers())
        expect(at_limit.status_code != 422, f"Expected the 8000-char contract limit to be accepted, got {at_limit.status_code}")

        # 8001 chars must be rejected by request validation alone -- no
        # LLM call should happen, so this one is deliberately NOT patched.
        oversized = client.post("/ventures/structure-idea", json={"description": "x" * 8001}, headers=_auth_headers())
        expect(oversized.status_code == 422, f"Expected 422 for oversized description, got {oversized.status_code}")


# --- 16-17: existing Idea Lab CRUD + deterministic VPS unaffected -----------


def test_existing_venture_crud_and_vps_endpoints_still_present() -> None:
    with _patched_auth():
        expect(client.get("/ventures").status_code == 401, "GET /ventures must still exist and require auth")
        expect(
            client.post("/ventures/scenario-compare", json={"current_assumptions": {}, "modified_assumptions": {}}).status_code == 401,
            "scenario-compare must still exist and require auth",
        )


def test_deterministic_vps_scoring_unaffected() -> None:
    sample = {"validation": {"customer_interviews": 25, "waitlist_signups": 100, "paying_customers": 5, "monthly_revenue": 2000}}
    result1 = compute_vps(sample)
    result2 = compute_vps(sample)
    expect(result1 == result2, "compute_vps must remain a pure, deterministic function after Phase 6.1")


# --- 18-20: canonical population unaffected ----------------------------------


def test_canonical_population_unaffected_by_structuring_calls() -> None:
    before_startups = None
    with engine.begin() as connection:
        before_startups = connection.execute(text("SELECT COUNT(*) FROM startups")).scalar()
        before_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()
    # Portfolio Release Task 3B: get_rankings()/discover_startups() now
    # require a viewer to scope by -- an admin bypass here so this
    # population-count sanity check keeps seeing the full population,
    # unaffected by the new, orthogonal authorization feature.
    before_rankings = len(get_rankings("__task3b_sanity_admin__", True))
    before_discovery = len(discover_startups("__task3b_sanity_admin__", True))

    fake = _minimal_fake_response()
    with _patched_llm(fake), _patched_auth():
        for _ in range(3):
            client.post("/ventures/structure-idea", json={"description": DESCRIPTION}, headers=_auth_headers())

    with engine.begin() as connection:
        after_startups = connection.execute(text("SELECT COUNT(*) FROM startups")).scalar()
        after_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()

    expect(after_startups == before_startups, "startups count must be unaffected by idea structuring")
    expect(after_analyses == before_analyses, "analyses count must be unaffected by idea structuring")
    expect(len(get_rankings("__task3b_sanity_admin__", True)) == before_rankings, "Rankings population must be unaffected")
    expect(len(discover_startups("__task3b_sanity_admin__", True)) == before_discovery, "Discovery population must be unaffected")


TESTS = [
    test_idea_description_produces_typed_structured_draft,
    test_structuring_endpoint_creates_no_database_row,
    test_structuring_endpoint_never_computes_vps,
    test_structuring_endpoint_creates_no_analyses_row,
    test_user_provided_facts_preserve_provenance,
    test_inferred_assumptions_preserve_inferred_provenance,
    test_unsupported_fields_remain_null,
    test_paying_customers_cannot_be_inferred,
    test_revenue_cannot_be_inferred,
    test_customer_interviews_cannot_be_inferred,
    test_venture_name_cannot_be_inferred,
    test_venture_name_preserved_when_explicitly_stated,
    test_explicitly_stated_validation_is_preserved_when_quote_verifies,
    test_unverifiable_user_provided_claim_is_stripped,
    test_malformed_llm_response_fails_safely,
    test_provider_failure_fails_safely,
    test_unauthenticated_structuring_request_rejected,
    test_oversized_and_empty_input_rejected,
    test_existing_venture_crud_and_vps_endpoints_still_present,
    test_deterministic_vps_scoring_unaffected,
    test_canonical_population_unaffected_by_structuring_calls,
]


def main() -> None:
    print("\nIdea Lab Phase 6.1 -- AI-Assisted Idea Setup tests")
    print("-" * 72)

    _cleanup()

    failures: list[str] = []

    for test in TESTS:
        name = test.__name__

        try:
            test()
        except AssertionError as error:
            print(f"FAIL  {name}\n      {error}")
            failures.append(name)
        else:
            print(f"PASS  {name}")

    _cleanup()

    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
