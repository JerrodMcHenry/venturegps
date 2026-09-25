"""
Regression tests for SIE Authentication Phase 2: FastAPI backend
enforcement of Clerk-issued identity (app/auth.py's get_current_user()/
RequireAuth, wired into all four analyze endpoints in app/api.py).

Runs entirely offline -- no live Clerk instance is contacted. A local
RSA keypair stands in for Clerk's own signing key: app.auth._jwks_client
is monkeypatched to a fake JWKS client whose get_signing_key_from_jwt()
returns this local public key, so every test below exercises the REAL
verification logic in get_current_user() (signature check, issuer check,
expiry check, azp check, sub extraction) against tokens this file signs
itself with the matching local private key -- not a bypassed/stubbed
dependency. app.auth.CLERK_ISSUER and _resolve_authorized_parties() are
monkeypatched to a fixed test issuer/origin so tokens can be crafted
deterministically.

A handful of tests (the "lazy users-table synchronization" group) hit
the real configured DATABASE_URL, like test_startup_write_path.py --
there is no separate test database in this project. Every row created
there uses a distinctive "zztest_auth_phase2_" user-id prefix that
cannot collide with a real Clerk user id, and is deleted in a finally
block, even on failure.

No test in this file makes a real LLM/Tavily call: authenticated
requests that need to reach past the 401 gate use a deliberately empty
request body, which the endpoint's own pre-existing "provide at least
one source" validation rejects with a fast 400 -- the same technique
used for live verification of this phase. This proves the auth gate
passed (a 401 would mean it didn't) without spending anything or
touching the real pipeline.

Run with:
    python -m app.tests.test_backend_authentication
"""

import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.database.db import engine

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_USER_ID = "zztest_auth_phase2_user"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()

# A second, unrelated keypair -- used only to prove a token signed by
# anyone other than the trusted issuer's real key is rejected (a forged
# token, not just a malformed one).
_other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    """Stands in for PyJWKClient: hands back the local test public key
    for every token, regardless of its kid. Real signature verification
    still happens inside jwt.decode() -- this only replaces key
    *discovery*, not verification."""

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_public_key)


def _make_token(
    sub: str | None = TEST_USER_ID,
    iss: str | None = TEST_ISSUER,
    azp: str | None = TEST_AZP,
    exp_delta: int = 3600,
    iat_delta: int = 0,
    extra: dict | None = None,
    signing_key=None,
    algorithm: str = "RS256",
    omit_claims: tuple[str, ...] = (),
) -> str:
    now = int(time.time())
    payload = {}
    if "iat" not in omit_claims:
        payload["iat"] = now + iat_delta
    if "exp" not in omit_claims:
        payload["exp"] = now + exp_delta
    if sub is not None and "sub" not in omit_claims:
        payload["sub"] = sub
    if iss is not None and "iss" not in omit_claims:
        payload["iss"] = iss
    if azp is not None:
        payload["azp"] = azp
    if extra:
        payload.update(extra)

    key = signing_key if signing_key is not None else _private_key
    return pyjwt.encode(payload, key, algorithm=algorithm)


class _patched_auth:
    """Points app.auth at the local test issuer/keypair/authorized
    parties for the duration of the block, restoring the real values
    (including the real @lru_cache-wrapped _jwks_client) on exit."""

    def __enter__(self):
        self._orig_issuer = auth.CLERK_ISSUER
        self._orig_jwks_client = auth._jwks_client
        self._orig_resolve_parties = auth._resolve_authorized_parties

        auth.CLERK_ISSUER = TEST_ISSUER
        auth._jwks_client = lambda: _FakeJWKSClient()
        auth._resolve_authorized_parties = lambda: [TEST_AZP]
        return self

    def __exit__(self, *exc):
        auth.CLERK_ISSUER = self._orig_issuer
        auth._jwks_client = self._orig_jwks_client
        auth._resolve_authorized_parties = self._orig_resolve_parties
        return False


def _auth_headers(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


# Phase 10.1B: /analyze-startup, /analyze-website, and /analyze-pdf were
# removed entirely (zero frontend/product consumers) -- POST /analyze is
# now the only paid endpoint, so it's the only one left in this list. See
# test_analysis_usage_protection.py for the tests proving the removed
# three now 404 for every caller, not just an unauthenticated one.
PAID_ENDPOINTS = [
    ("POST", "/analyze", {}, {}),
]


def _call(method: str, path: str, data: dict, files: dict, token: str | None):
    return client.request(
        method, path, data=data, files=files, headers=_auth_headers(token)
    )


# --- 1-3: rejection cases (no pipeline reached, no monkeypatching of
# app.api needed -- Depends() short-circuits before the endpoint body) --


def test_missing_token_rejected_on_every_paid_endpoint() -> None:
    with _patched_auth():
        for method, path, data, files in PAID_ENDPOINTS:
            response = _call(method, path, data, files, token=None)
            expect(
                response.status_code == 401,
                f"{path} without a token: expected 401, got {response.status_code}",
            )


def test_malformed_bearer_token_rejected() -> None:
    with _patched_auth():
        for bad_header in ["not-a-bearer-scheme x.y.z", "Bearer", "Bearer   ", "Basic abc123"]:
            response = client.post(
                "/analyze", data={}, files={}, headers={"Authorization": bad_header}
            )
            expect(
                response.status_code == 401,
                f"Malformed header {bad_header!r}: expected 401, got {response.status_code}",
            )


def test_invalid_signature_rejected() -> None:
    """A token whose claims look valid but is signed by a key OTHER than
    the trusted issuer's -- a forged token, not just a garbled string."""
    with _patched_auth():
        forged = _make_token(signing_key=_other_private_key)
        response = _call("POST", "/analyze", {}, {}, token=forged)
        expect(response.status_code == 401, f"Forged signature: expected 401, got {response.status_code}")


def test_expired_token_rejected() -> None:
    with _patched_auth():
        expired = _make_token(exp_delta=-3600, iat_delta=-7200)
        response = _call("POST", "/analyze", {}, {}, token=expired)
        expect(response.status_code == 401, f"Expired token: expected 401, got {response.status_code}")


def test_wrong_issuer_rejected() -> None:
    with _patched_auth():
        wrong_iss = _make_token(iss="https://some-other-app.clerk.accounts.dev")
        response = _call("POST", "/analyze", {}, {}, token=wrong_iss)
        expect(response.status_code == 401, f"Wrong issuer: expected 401, got {response.status_code}")


def test_wrong_authorized_party_rejected() -> None:
    with _patched_auth():
        wrong_azp = _make_token(azp="https://evil.example.com")
        response = _call("POST", "/analyze", {}, {}, token=wrong_azp)
        expect(response.status_code == 401, f"Wrong azp: expected 401, got {response.status_code}")


def test_missing_azp_claim_is_allowed() -> None:
    """Clerk's own documented rule: no azp claim at all means the check
    is skipped, not failed -- not every token carries one."""
    with _patched_auth():
        no_azp = _make_token(azp=None)
        response = _call("POST", "/analyze", {}, {}, token=no_azp)
        expect(
            response.status_code != 401,
            f"Token with no azp claim should not be rejected on that basis, got {response.status_code}",
        )


def test_missing_sub_claim_rejected() -> None:
    with _patched_auth():
        no_sub = _make_token(omit_claims=("sub",))
        response = _call("POST", "/analyze", {}, {}, token=no_sub)
        expect(response.status_code == 401, f"Missing sub: expected 401, got {response.status_code}")


def test_alg_none_attack_rejected() -> None:
    """The classic JWT 'alg: none' forgery -- must never be accepted
    regardless of what the header claims."""
    with _patched_auth():
        forged = pyjwt.encode(
            {"sub": TEST_USER_ID, "iss": TEST_ISSUER, "iat": int(time.time()), "exp": int(time.time()) + 3600},
            key="",
            algorithm="none",
        )
        response = _call("POST", "/analyze", {}, {}, token=forged)
        expect(response.status_code == 401, f"alg=none forgery: expected 401, got {response.status_code}")


# --- 4: valid token reaches the endpoint body (dependency resolves) -------


def test_valid_token_passes_auth_gate() -> None:
    """Empty body -> the endpoint's own pre-existing validation rejects
    it with 400, not 401 -- proving the request passed the auth
    dependency and reached real business logic, without spending
    anything or touching the real pipeline. Mirrors the live browser
    verification performed for this phase."""
    with _patched_auth():
        token = _make_token()
        response = _call("POST", "/analyze", {}, {}, token=token)
        expect(
            response.status_code == 400,
            f"Valid token should reach endpoint body (400 for empty sources), got {response.status_code}: {response.text}",
        )


# --- 5-8: lazy users-table sync + ownership-fabrication guardrails
# (real DB) --------------------------------------------------------------


def _cleanup_test_user() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM users WHERE id = :id"), {"id": TEST_USER_ID}
        )


def test_first_valid_request_creates_one_users_row() -> None:
    _cleanup_test_user()
    try:
        with engine.begin() as connection:
            before = connection.execute(
                text("SELECT COUNT(*) FROM startup_memberships")
            ).scalar()
            before_saved = connection.execute(
                text("SELECT COUNT(*) FROM saved_startups")
            ).scalar()

        with _patched_auth():
            token = _make_token()
            response = _call("POST", "/analyze", {}, {}, token=token)
            expect(response.status_code == 400, f"Unexpected status: {response.status_code}")

        with engine.begin() as connection:
            rows = connection.execute(
                text("SELECT id, email FROM users WHERE id = :id"), {"id": TEST_USER_ID}
            ).mappings().all()
            after = connection.execute(
                text("SELECT COUNT(*) FROM startup_memberships")
            ).scalar()
            after_saved = connection.execute(
                text("SELECT COUNT(*) FROM saved_startups")
            ).scalar()

        expect(len(rows) == 1, f"Expected exactly one users row, got {len(rows)}")
        expect(rows[0]["id"] == TEST_USER_ID, "users row has wrong id")
        expect(
            after == before,
            f"startup_memberships changed ({before} -> {after}): authentication must never create ownership",
        )
        expect(
            after_saved == before_saved,
            f"saved_startups changed ({before_saved} -> {after_saved}): authentication must never create a saved startup",
        )
    finally:
        _cleanup_test_user()


def test_repeated_authenticated_requests_reuse_same_users_row() -> None:
    _cleanup_test_user()
    try:
        with _patched_auth():
            token = _make_token()
            for _ in range(3):
                response = _call("POST", "/analyze", {}, {}, token=token)
                expect(response.status_code == 400, f"Unexpected status: {response.status_code}")

        with engine.begin() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM users WHERE id = :id"), {"id": TEST_USER_ID}
            ).scalar()

        expect(count == 1, f"Expected exactly one users row after repeated requests, got {count}")
    finally:
        _cleanup_test_user()


# --- 9-11: no legacy endpoint can bypass auth ------------------------------


# --- Phase 10.1B: legacy paid endpoints removed, not just re-auth-gated ----
# /analyze-startup, /analyze-website, /analyze-pdf's own "cannot bypass
# auth" coverage was removed along with the routes themselves (a 401 test
# no longer applies to a route that doesn't exist at all -- it now 404s
# for every caller regardless of auth). See
# test_analysis_usage_protection.py for the tests proving that.


# --- 12-16: public read endpoints remain fully public ----------------------


def test_public_endpoints_require_no_auth() -> None:
    # Portfolio Release Task 3B -- Secure Analysis Visibility: /analytics,
    # /rankings, and /analyses/search moved OUT of this list -- they now
    # return per-user-authorized analysis content (scores, summaries) and
    # correctly require auth (see test_analysis_content_endpoints_require_auth
    # below for their own coverage). Only genuinely content-free endpoints
    # remain here.
    with _patched_auth():
        checks = [
            ("GET", "/health", {}),
            ("GET", "/version", {}),
        ]
        for method, path, params in checks:
            response = client.request(method, path, params=params)
            expect(
                response.status_code != 401,
                f"Public endpoint {path} must not require auth, got {response.status_code}",
            )


def test_analysis_content_endpoints_require_auth() -> None:
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility: every endpoint
    that can return analysis content (scores, summaries, evidence-derived
    text) or aggregate it across analyses now requires a verified,
    authenticated caller -- a missing/invalid token gets the same 401 the
    paid /analyze endpoint already used, not a silent public response.
    """
    with _patched_auth():
        checks = [
            ("GET", "/analytics", {}),
            ("GET", "/rankings", {}),
            ("GET", "/analyses/search", {"query": "a"}),
            ("GET", "/discover", {}),
            ("GET", "/discover/filter-options", {}),
            ("GET", "/compare", {"startups": "1,2"}),
            ("GET", "/score-history/ZZTest Co", {}),
            ("GET", "/startup-trends/ZZTest Co", {}),
            ("GET", "/top-startups", {}),
            ("GET", "/top-improving-startups", {}),
            ("GET", "/startup/ZZTest Co", {}),
            ("GET", "/startup/ZZTest Co/sps-history", {}),
        ]
        for method, path, params in checks:
            response = client.request(method, path, params=params)
            expect(
                response.status_code == 401,
                f"Expected {path} to require auth (401) with no token, got {response.status_code}",
            )


# --- 17: failure responses never leak internals ----------------------------


def test_failure_responses_never_leak_token_or_internals() -> None:
    with _patched_auth():
        forged = _make_token(signing_key=_other_private_key)
        expired = _make_token(exp_delta=-3600, iat_delta=-7200)

        for bad_token in [forged, expired, "not.a.valid.jwt"]:
            response = _call("POST", "/analyze", {}, {}, token=bad_token)
            body_text = response.text

            expect(response.status_code == 401, f"Expected 401, got {response.status_code}")
            expect(bad_token not in body_text, "Response body must never echo the raw token")
            for leaky_fragment in ["Traceback", "jwt.exceptions", "PyJWKClient", "cryptography."]:
                expect(
                    leaky_fragment not in body_text,
                    f"Response body leaked internal detail {leaky_fragment!r}: {body_text}",
                )


TESTS = [
    test_missing_token_rejected_on_every_paid_endpoint,
    test_malformed_bearer_token_rejected,
    test_invalid_signature_rejected,
    test_expired_token_rejected,
    test_wrong_issuer_rejected,
    test_wrong_authorized_party_rejected,
    test_missing_azp_claim_is_allowed,
    test_missing_sub_claim_rejected,
    test_alg_none_attack_rejected,
    test_valid_token_passes_auth_gate,
    test_first_valid_request_creates_one_users_row,
    test_repeated_authenticated_requests_reuse_same_users_row,
    test_public_endpoints_require_no_auth,
    test_analysis_content_endpoints_require_auth,
    test_failure_responses_never_leak_token_or_internals,
]


def main() -> None:
    print("\nSIE Authentication Phase 2: FastAPI backend authentication tests")
    print("-" * 72)

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

    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
