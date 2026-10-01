"""
Regression tests for Phase 7.1C -- Founder Membership Authorization
Foundation: app/database/db.py's get_startup_memberships_for_user()/
user_has_startup_membership(), app/auth.py's RequireStartupMember, and
the GET /me/startups endpoint in app/api.py.

Reuses the exact same local-RSA-keypair JWT-mocking harness as
test_startup_claims.py/test_backend_authentication.py (no live Clerk
dependency).

Every row here uses a distinctive zztest_membership_* user-id prefix and
a "ZZTest Membership" company-name prefix, cleaned up in a finally block
even on failure. No test here makes an LLM/Tavily call.

Central thesis under test, stated once here as this file's own single
source of truth (mirrors the module-level comment in app/database/db.py's
Phase 7.1C section): a live startup_memberships row is the ONLY current
authorization truth. An approved startup_claims row is historical
evidence that approval happened once -- it is NOT proof of current
access, does not by itself satisfy RequireStartupMember, and is never
consulted by any function in this file's subject under test.

A few tests below INSERT directly into startup_memberships via raw SQL
purely as test setup (to prove authorization does not depend on claim
history existing at all, and to simulate a future membership-removal
event that has no application code path yet). This is test fixture code,
not an application write path -- see test_exactly_one_membership_insert_path_exists,
which audits the real application source for exactly that distinction.

Run with:
    python -m app.tests.test_startup_membership
"""

import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.auth import AuthenticatedUser, require_startup_member
from app.database.db import (
    engine,
    get_or_create_startup,
    get_startup_memberships_for_user,
    user_has_startup_membership,
    save_analysis,
    save_startup_for_user,
    create_modeled_venture,
    approve_startup_claim,
)

USER_A = "zztest_membership_user_a"
USER_B = "zztest_membership_user_b"
USER_C = "zztest_membership_user_c"
ADMIN_USER = "zztest_membership_admin"
ALL_USERS = [USER_A, USER_B, USER_C, ADMIN_USER]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_PREFIX = "ZZTest Membership"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


# --- JWT mocking harness (identical pattern to test_startup_claims.py) ------


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_public_key)


def _make_token(sub: str, exp_delta: int = 3600) -> str:
    now = int(time.time())
    payload = {"sub": sub, "iss": TEST_ISSUER, "azp": TEST_AZP, "iat": now, "exp": now + exp_delta}
    return pyjwt.encode(payload, _private_key, algorithm="RS256")


class _patched_auth:
    def __init__(self, admin_ids=None):
        self._admin_ids = admin_ids if admin_ids is not None else [ADMIN_USER]

    def __enter__(self):
        self._orig_issuer = auth.CLERK_ISSUER
        self._orig_jwks_client = auth._jwks_client
        self._orig_resolve_parties = auth._resolve_authorized_parties
        self._orig_resolve_admins = auth._resolve_admin_user_ids

        auth.CLERK_ISSUER = TEST_ISSUER
        auth._jwks_client = lambda: _FakeJWKSClient()
        auth._resolve_authorized_parties = lambda: [TEST_AZP]
        auth._resolve_admin_user_ids = lambda: self._admin_ids
        return self

    def __exit__(self, *exc):
        auth.CLERK_ISSUER = self._orig_issuer
        auth._jwks_client = self._orig_jwks_client
        auth._resolve_authorized_parties = self._orig_resolve_parties
        auth._resolve_admin_user_ids = self._orig_resolve_admins
        return False


def _auth_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


# --- Test data helpers -------------------------------------------------------


def _canonical_methodology(sps: float = 70.0) -> dict:
    from app.ai.sie_v2_methodology import METHODOLOGY_VERSION

    return {
        "startup_intelligence_score": sps,
        "market": {"score": 7.0},
        "team": {"score": 7.0},
        "product": {"score": 7.0},
        "execution": {"score": 7.0},
        "traction": {"score": 7.0},
        "financial_health": {"score": 7.0},
        "analysis_context": {"methodology_version": METHODOLOGY_VERSION},
    }


def _make_test_startup(name_suffix: str) -> int:
    company_name = f"{TEST_PREFIX} {name_suffix}"
    save_analysis(
        company_text=f"Test company text for {company_name}",
        summary="s", risk_analysis="r", competitor_analysis="c", memo="m",
        structured_analysis={"company_name": company_name, "industry": "SaaS", "stage": "Seed", "business_model": "SaaS"},
        investment_score={}, founder_analysis={}, market_analysis={}, sources=[], traction_analysis={},
        market_score=None, team_score=None, product_score=None, competition_score=None,
        traction_score=None, financial_score=None, overall_score=None, recommendation=None,
        readiness_score=None, readiness_summary=None,
        methodology=_canonical_methodology(),
    )
    return get_or_create_startup(company_name)


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in ALL_USERS:
            connection.execute(
                text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
                {"id": user_id},
            )


def _insert_membership_directly(user_id: str, startup_id: int, role: str = "member") -> None:
    """Test-fixture-only helper -- bypasses the claim lifecycle entirely to
    prove authorization doesn't depend on claim history existing at all
    (test 10), and to simulate a membership that existed and was later
    removed (tests 9/18), since no application removal path exists yet.
    Never called from application code -- see this file's own docstring."""
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO startup_memberships (user_id, startup_id, role)
            VALUES (:user_id, :startup_id, :role)
            ON CONFLICT (user_id, startup_id) DO NOTHING
        """), {"user_id": user_id, "startup_id": startup_id, "role": role})


def _remove_membership_directly(user_id: str, startup_id: int) -> None:
    """Test-fixture-only helper simulating a future membership-removal
    event. No application code path does this yet (Part 6/Part 8's
    'membership removal immediately removes authorization' is tested
    this way precisely because no removal feature exists to test through
    its own endpoint)."""
    with engine.begin() as connection:
        connection.execute(text("""
            DELETE FROM startup_memberships WHERE user_id = :user_id AND startup_id = :startup_id
        """), {"user_id": user_id, "startup_id": startup_id})


def _submit_and_approve_claim(user_id: str, startup_id: int, admin_id: str = ADMIN_USER) -> int:
    with _patched_auth(admin_ids=[admin_id]):
        response = client.post(
            "/startup-claims",
            json={"startup_id": startup_id, "justification": "I am the founder"},
            headers=_auth_headers(user_id),
        )
        expect(response.status_code == 200, f"Claim submission failed: {response.text}")
        claim_id = response.json()["id"]

        approve_response = client.post(
            f"/admin/startup-claims/{claim_id}/approve", headers=_auth_headers(admin_id)
        )
        expect(approve_response.status_code == 200, f"Approval failed: {approve_response.text}")

    return claim_id


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                DELETE FROM startup_memberships
                WHERE user_id = ANY(:ids)
                   OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
            """),
            {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("""
                DELETE FROM startup_claims
                WHERE user_id = ANY(:ids)
                   OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
            """),
            {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("DELETE FROM saved_startups WHERE user_id = ANY(:ids)"),
            {"ids": ALL_USERS},
        )
        connection.execute(
            text("DELETE FROM modeled_ventures WHERE user_id = ANY(:ids)"),
            {"ids": ALL_USERS},
        )
        connection.execute(
            text("""
                DELETE FROM analyses
                WHERE startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
            """),
            {"pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("DELETE FROM startups WHERE normalized_name LIKE :pattern"),
            {"pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("DELETE FROM users WHERE id = ANY(:ids)"),
            {"ids": ALL_USERS},
        )


# --- 1-2: baseline /me/startups behavior -------------------------------------


def test_unauthenticated_me_startups_rejected() -> None:
    with _patched_auth():
        response = client.get("/me/startups")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")


def test_zero_memberships_returns_empty_list() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.get("/me/startups", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}")
        expect(response.json() == [], f"Expected an honest empty list, got {response.json()!r}")
    finally:
        _cleanup()


# --- 3-5: per-user scoping and multi-startup/multi-member --------------------


def test_user_sees_only_own_memberships() -> None:
    _ensure_test_users()
    try:
        startup_a = _make_test_startup("OwnA")
        startup_b = _make_test_startup("OwnB")
        _submit_and_approve_claim(USER_A, startup_a)
        _submit_and_approve_claim(USER_B, startup_b)

        with _patched_auth():
            response = client.get("/me/startups", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        ids = {row["startup_id"] for row in response.json()}
        expect(ids == {startup_a}, f"USER_A must see only their own membership, got {ids}")
    finally:
        _cleanup()


def test_user_with_multiple_memberships_receives_all() -> None:
    _ensure_test_users()
    try:
        startup_1 = _make_test_startup("Multi1")
        startup_2 = _make_test_startup("Multi2")
        startup_3 = _make_test_startup("Multi3")
        _submit_and_approve_claim(USER_A, startup_1)
        _submit_and_approve_claim(USER_A, startup_2)
        _submit_and_approve_claim(USER_A, startup_3)

        with _patched_auth():
            response = client.get("/me/startups", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        ids = [row["startup_id"] for row in response.json()]
        expect(
            sorted(ids) == sorted([startup_1, startup_2, startup_3]),
            f"Expected all three memberships exactly once each, got {ids}",
        )
        expect(len(ids) == len(set(ids)), "Each membership must appear exactly once, no duplicates")
    finally:
        _cleanup()


def test_multiple_users_can_belong_to_same_startup() -> None:
    _ensure_test_users()
    try:
        shared_startup = _make_test_startup("Shared")
        _submit_and_approve_claim(USER_A, shared_startup)
        _submit_and_approve_claim(USER_B, shared_startup)

        with engine.begin() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM startup_memberships WHERE startup_id = :s"),
                {"s": shared_startup},
            ).scalar()
        expect(count == 2, f"Expected 2 independent members for one startup, got {count}")

        expect(user_has_startup_membership(USER_A, shared_startup), "USER_A must be authorized")
        expect(user_has_startup_membership(USER_B, shared_startup), "USER_B must be authorized")
    finally:
        _cleanup()


# --- 6-8: claim status alone never appears as membership ---------------------


def test_pending_claim_does_not_appear_in_my_startups() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("PendingClaim")
        with _patched_auth():
            client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "x"},
                headers=_auth_headers(USER_A),
            )
            response = client.get("/me/startups", headers=_auth_headers(USER_A))
        expect(response.json() == [], "A pending claim must not appear as a membership")
        expect(not user_has_startup_membership(USER_A, startup_id), "Pending claim must not authorize")
    finally:
        _cleanup()


def test_rejected_claim_does_not_appear_in_my_startups() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("RejectedClaim")
        with _patched_auth():
            submitted = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "x"},
                headers=_auth_headers(USER_A),
            )
            claim_id = submitted.json()["id"]
            client.post(
                f"/admin/startup-claims/{claim_id}/reject",
                json={"rejection_reason": "Not verifiable"},
                headers=_auth_headers(ADMIN_USER),
            )
            response = client.get("/me/startups", headers=_auth_headers(USER_A))
        expect(response.json() == [], "A rejected claim must not appear as a membership")
        expect(not user_has_startup_membership(USER_A, startup_id), "Rejected claim must not authorize")
    finally:
        _cleanup()


def test_cancelled_claim_does_not_appear_in_my_startups() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("CancelledClaim")
        with _patched_auth():
            submitted = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "x"},
                headers=_auth_headers(USER_A),
            )
            claim_id = submitted.json()["id"]
            client.post(
                f"/me/startup-claims/{claim_id}/cancel",
                headers=_auth_headers(USER_A),
            )
            response = client.get("/me/startups", headers=_auth_headers(USER_A))
        expect(response.json() == [], "A cancelled claim must not appear as a membership")
        expect(not user_has_startup_membership(USER_A, startup_id), "Cancelled claim must not authorize")
    finally:
        _cleanup()


# --- 9-10: claim-history vs current-membership distinction -------------------


def test_approved_claim_without_membership_does_not_authorize() -> None:
    """The central Phase 7.1C thesis: an approved claim is historical
    evidence, not current authorization. Simulates a membership that was
    later removed (no removal feature exists yet -- see
    _remove_membership_directly's own docstring) while the claim row
    keeps reading 'approved' forever, and proves authorization tracks
    the membership row, never the claim's historical status."""
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("ApprovedThenRemoved")
        _submit_and_approve_claim(USER_A, startup_id)
        expect(user_has_startup_membership(USER_A, startup_id), "Sanity: approval must grant membership")

        _remove_membership_directly(USER_A, startup_id)

        with engine.begin() as connection:
            claim_status = connection.execute(
                text("SELECT status FROM startup_claims WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).scalar()
        expect(claim_status == "approved", "The historical claim must still read 'approved'")

        expect(
            not user_has_startup_membership(USER_A, startup_id),
            "Membership removal must immediately revoke authorization even though the claim is still 'approved'",
        )

        try:
            require_startup_member(startup_id=startup_id, current_user=AuthenticatedUser(user_id=USER_A))
            raise AssertionError("require_startup_member must reject a removed membership")
        except HTTPException as e:
            expect(e.status_code == 404, f"Expected 404, got {e.status_code}")

        with _patched_auth():
            response = client.get("/me/startups", headers=_auth_headers(USER_A))
        expect(response.json() == [], "An approved-but-removed membership must not appear in /me/startups")
    finally:
        _cleanup()


def test_membership_without_claim_history_authorizes() -> None:
    """Proves the inverse: a live startup_memberships row authorizes on
    its own, with zero startup_claims rows ever existing for this
    user/startup pair. See _insert_membership_directly's own docstring
    for why this direct insert is test-fixture code, not a new
    application write path."""
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("MembershipNoClaim")
        _insert_membership_directly(USER_A, startup_id)

        with engine.begin() as connection:
            claim_count = connection.execute(
                text("SELECT COUNT(*) FROM startup_claims WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).scalar()
        expect(claim_count == 0, "Sanity: zero claims must exist for this pair")

        expect(user_has_startup_membership(USER_A, startup_id), "A live membership must authorize regardless of claim history")

        result = require_startup_member(startup_id=startup_id, current_user=AuthenticatedUser(user_id=USER_A))
        expect(result.user_id == USER_A, "require_startup_member must pass through the authenticated user")

        with _patched_auth():
            response = client.get("/me/startups", headers=_auth_headers(USER_A))
        ids = {row["startup_id"] for row in response.json()}
        expect(startup_id in ids, "A claim-less membership must still appear in /me/startups")
    finally:
        _cleanup()


# --- 11-12: adjacent tables never authorize -----------------------------------


def test_saved_startup_does_not_authorize() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("SavedOnly")
        save_startup_for_user(USER_A, startup_id)

        expect(not user_has_startup_membership(USER_A, startup_id), "Saving a startup must never authorize access")

        try:
            require_startup_member(startup_id=startup_id, current_user=AuthenticatedUser(user_id=USER_A))
            raise AssertionError("require_startup_member must reject a saved-only startup")
        except HTTPException as e:
            expect(e.status_code == 404, f"Expected 404, got {e.status_code}")
    finally:
        _cleanup()


def test_modeled_venture_does_not_authorize() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("VentureAdjacent")
        create_modeled_venture(
            user_id=USER_A, name="Some idea", description=None, industry=None,
            business_model=None, target_customer=None, stage=None,
            assumptions={}, model_result=None,
        )

        expect(
            not user_has_startup_membership(USER_A, startup_id),
            "Having a modeled venture must never authorize access to any real canonical startup",
        )

        with _patched_auth():
            response = client.get("/me/startups", headers=_auth_headers(USER_A))
        expect(response.json() == [], "A modeled venture must never appear as, or create, a startup membership")
    finally:
        _cleanup()


# --- 13-14: client cannot spoof identity or role ------------------------------


def test_user_id_cannot_be_spoofed_in_me_startups() -> None:
    _ensure_test_users()
    try:
        startup_a = _make_test_startup("SpoofUserA")
        _submit_and_approve_claim(USER_A, startup_a)

        with _patched_auth():
            # /me/startups takes no user-identifying parameter at all --
            # this extra query param has nowhere to be read from, proving
            # the endpoint cannot be redirected to another user's data.
            response = client.get(
                "/me/startups", params={"user_id": USER_B}, headers=_auth_headers(USER_B)
            )
        expect(response.json() == [], "USER_B must see their own (empty) list regardless of a spoofed user_id param")
    finally:
        _cleanup()


def test_role_cannot_be_spoofed_via_membership() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("SpoofRoleMembership")
        with _patched_auth():
            submitted = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "x", "role": "owner"},
                headers=_auth_headers(USER_A),
            )
            claim_id = submitted.json()["id"]
            client.post(f"/admin/startup-claims/{claim_id}/approve", headers=_auth_headers(ADMIN_USER))
            response = client.get("/me/startups", headers=_auth_headers(USER_A))

        rows = [row for row in response.json() if row["startup_id"] == startup_id]
        expect(len(rows) == 1, "Expected exactly one membership row")
        expect(rows[0]["role"] == "member", f"role must always be 'member', got {rows[0]['role']!r}")
    finally:
        _cleanup()


# --- 15-18: RequireStartupMember authorization primitive ---------------------


def test_member_authorization_succeeds_for_own_startup() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("OwnSuccess")
        _submit_and_approve_claim(USER_A, startup_id)

        result = require_startup_member(startup_id=startup_id, current_user=AuthenticatedUser(user_id=USER_A))
        expect(result.user_id == USER_A, "Must return the authenticated user on success")
    finally:
        _cleanup()


def test_member_authorization_fails_for_other_startup() -> None:
    _ensure_test_users()
    try:
        startup_a = _make_test_startup("MineOnly")
        startup_b = _make_test_startup("NotMine")
        _submit_and_approve_claim(USER_A, startup_a)

        try:
            require_startup_member(startup_id=startup_b, current_user=AuthenticatedUser(user_id=USER_A))
            raise AssertionError("Must not authorize a startup the user has no membership for")
        except HTTPException as e:
            expect(e.status_code == 404, f"Expected 404, got {e.status_code}")
    finally:
        _cleanup()


def test_guessing_startup_id_does_not_bypass_authorization() -> None:
    _ensure_test_users()
    try:
        real_other_startup = _make_test_startup("RealButNotMine")
        nonexistent_startup_id = 999999999

        for candidate in (real_other_startup, nonexistent_startup_id):
            try:
                require_startup_member(startup_id=candidate, current_user=AuthenticatedUser(user_id=USER_A))
                raise AssertionError(f"Must not authorize startup_id={candidate}")
            except HTTPException as e:
                expect(e.status_code == 404, f"Expected 404 for startup_id={candidate}, got {e.status_code}")
                expect(
                    e.detail == "Startup not found.",
                    "A real-but-unowned startup and a nonexistent one must be indistinguishable",
                )
    finally:
        _cleanup()


def test_membership_removal_immediately_removes_authorization() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("RemovalTiming")
        _submit_and_approve_claim(USER_A, startup_id)

        result = require_startup_member(startup_id=startup_id, current_user=AuthenticatedUser(user_id=USER_A))
        expect(result.user_id == USER_A, "Sanity: must authorize before removal")

        _remove_membership_directly(USER_A, startup_id)

        try:
            require_startup_member(startup_id=startup_id, current_user=AuthenticatedUser(user_id=USER_A))
            raise AssertionError("Must reject immediately after membership removal")
        except HTTPException as e:
            expect(e.status_code == 404, f"Expected 404, got {e.status_code}")
    finally:
        _cleanup()


# --- 19-20: existing public surfaces remain public ----------------------------


# Task 33 item 15: these two tests predate a later, intentional
# security-hardening phase that put GET /startup/{name}, /rankings,
# /discover, and /compare behind RequireAuth (see app/tests/test_
# security_hardening.py's own currently-passing test_rankings_now_
# requires_auth et al., and app/api.py's own "Portfolio Release Task
# 3B -- Secure Analysis Visibility" comment on /startup/{name}). The
# ORIGINAL "stays public, no auth" assertions here are stale -- root
# cause confirmed as Category A (an intentional contract change these
# two tests were never updated for), not a production regression.
# Rewritten to the CURRENT, correct, two-sided contract: unauthenticated
# access is rejected, authenticated access succeeds -- these tests now
# actively guard the auth requirement instead of assuming its opposite.


def test_startup_profile_requires_auth_then_succeeds_when_authenticated() -> None:
    startup_id = _make_test_startup("AuthRequired")
    try:
        with engine.begin() as connection:
            name = connection.execute(
                text("SELECT canonical_name FROM startups WHERE id = :id"), {"id": startup_id}
            ).scalar()

        unauth_response = client.get(f"/startup/{name}")
        expect(unauth_response.status_code == 401, f"Expected 401 with no auth, got {unauth_response.status_code}")

        with _patched_auth():
            auth_response = client.get(f"/startup/{name}", headers=_auth_headers(USER_A))
        expect(auth_response.status_code == 200, f"Expected 200 once authenticated, got {auth_response.status_code}")
    finally:
        _cleanup()


def test_rankings_discovery_compare_require_auth_then_succeed_when_authenticated() -> None:
    startup_1 = _make_test_startup("PublicSurfaces1")
    startup_2 = _make_test_startup("PublicSurfaces2")
    try:
        unauth_rankings = client.get("/rankings")
        expect(unauth_rankings.status_code == 401, f"Rankings expected 401 with no auth, got {unauth_rankings.status_code}")
        unauth_discover = client.get("/discover")
        expect(unauth_discover.status_code == 401, f"Discovery expected 401 with no auth, got {unauth_discover.status_code}")
        unauth_compare = client.get("/compare", params={"startups": f"{startup_1},{startup_2}"})
        expect(unauth_compare.status_code == 401, f"Compare expected 401 with no auth, got {unauth_compare.status_code}")

        with _patched_auth():
            response = client.get("/rankings", headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Rankings expected 200 once authenticated, got {response.status_code}")

            response = client.get("/discover", headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Discovery expected 200 once authenticated, got {response.status_code}")

            # /compare requires >= MIN_COMPARISON_STARTUPS (2) well-formed ids.
            response = client.get("/compare", params={"startups": f"{startup_1},{startup_2}"}, headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Compare expected 200 once authenticated, got {response.status_code}: {response.text}")
    finally:
        _cleanup()


# --- 21-22: no new write path introduced --------------------------------------


def test_claim_submission_behavior_unchanged() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("SubmissionUnchanged")
        with engine.begin() as connection:
            before = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()

        with _patched_auth():
            response = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "I am the founder"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}")
        expect(response.json()["status"] == "pending", "New claim must still be pending")
        expect(set(response.json().keys()) == {"id", "startup_id", "status"}, "Response shape must be unchanged")

        with engine.begin() as connection:
            after = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()
        expect(after == before, "Claim submission must still never create a startup_memberships row")
    finally:
        _cleanup()


def test_exactly_one_membership_insert_path_exists() -> None:
    """Repo-wide audit: exactly one real `INSERT INTO startup_memberships`
    statement may exist in application source (app/database/db.py's
    approve_startup_claim(), per that function's own module-level
    invariant comment). Fails loudly if Phase 7.1C -- or anything else --
    ever introduces a second one."""
    import pathlib
    import re

    app_dir = pathlib.Path(__file__).resolve().parent.parent
    insert_pattern = re.compile(r"INSERT\s+INTO\s+startup_memberships", re.IGNORECASE)
    def_pattern = re.compile(r"^\s*def\s+(\w+)\s*\(")

    matches: list[tuple[pathlib.Path, int, str]] = []
    for path in app_dir.rglob("*.py"):
        if "tests" in path.parts:
            continue  # test fixtures may insert directly; audited separately, not application code
        lines = path.read_text().splitlines()
        for line_number, line in enumerate(lines, start=1):
            match = insert_pattern.search(line)
            # Skip comment/prose mentions (e.g. a docstring or `#` note
            # describing the invariant) -- only a real statement counts.
            # A real SQL statement here is always inside a text("""...
            # ...""") block, never preceded by a `#` on the same line.
            if match and "#" in line[: match.start()]:
                continue
            if match:
                # Walk backward to the nearest enclosing `def` to name
                # which function this INSERT lives inside.
                enclosing_function = "<module level>"
                for prior_line in reversed(lines[:line_number - 1]):
                    def_match = def_pattern.match(prior_line)
                    if def_match:
                        enclosing_function = def_match.group(1)
                        break
                matches.append((path, line_number, enclosing_function))

    locations = [f"{path.name}:{line_number} (in {fn})" for path, line_number, fn in matches]
    expect(
        len(matches) == 1,
        f"Expected exactly one application INSERT INTO startup_memberships, found {len(matches)}: {locations}",
    )
    expect(
        matches[0][0].name == "db.py" and matches[0][2] == "approve_startup_claim",
        f"The one INSERT must live inside db.py's approve_startup_claim(); found {locations}",
    )


TESTS = [
    test_unauthenticated_me_startups_rejected,
    test_zero_memberships_returns_empty_list,
    test_user_sees_only_own_memberships,
    test_user_with_multiple_memberships_receives_all,
    test_multiple_users_can_belong_to_same_startup,
    test_pending_claim_does_not_appear_in_my_startups,
    test_rejected_claim_does_not_appear_in_my_startups,
    test_cancelled_claim_does_not_appear_in_my_startups,
    test_approved_claim_without_membership_does_not_authorize,
    test_membership_without_claim_history_authorizes,
    test_saved_startup_does_not_authorize,
    test_modeled_venture_does_not_authorize,
    test_user_id_cannot_be_spoofed_in_me_startups,
    test_role_cannot_be_spoofed_via_membership,
    test_member_authorization_succeeds_for_own_startup,
    test_member_authorization_fails_for_other_startup,
    test_guessing_startup_id_does_not_bypass_authorization,
    test_membership_removal_immediately_removes_authorization,
    test_startup_profile_requires_auth_then_succeeds_when_authenticated,
    test_rankings_discovery_compare_require_auth_then_succeed_when_authenticated,
    test_claim_submission_behavior_unchanged,
    test_exactly_one_membership_insert_path_exists,
]


def main() -> None:
    print("\nPhase 7.1C -- Founder Membership Authorization Foundation tests")
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
