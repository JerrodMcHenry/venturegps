"""
Regression tests for Phase 7.1A -- Startup Claim & Membership backend
lifecycle: app/database/db.py's startup_claims functions, app/auth.py's
RequireAdmin, and the /startup-claims, /me/startup-claims,
/admin/startup-claims* endpoints in app/api.py.

Reuses the exact same local-RSA-keypair JWT-mocking harness as
test_backend_authentication.py (no live Clerk dependency), and
additionally monkeypatches app.auth._resolve_admin_user_ids the same way
_resolve_authorized_parties is already patched -- ADMIN_USER_IDS is read
fresh from os.environ on every check with no caching, so this is a
faithful stand-in for the real env-var-driven behavior.

Every row here uses a distinctive zztest_claim_* user-id prefix and a
"ZZTest Claims" company-name prefix, cleaned up in a finally block even
on failure. No test here makes an LLM/Tavily call.

Run with:
    python -m app.tests.test_startup_claims
"""

import threading
import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.database.db import (
    engine,
    get_or_create_startup,
    get_rankings,
    discover_startups,
    save_analysis,
    approve_startup_claim,
    create_startup_claim,
    user_has_startup_membership,
)

USER_A = "zztest_claim_user_a"
USER_B = "zztest_claim_user_b"
ADMIN_USER = "zztest_claim_admin"

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_PREFIX = "ZZTest Claims"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


# --- JWT + admin mocking harness --------------------------------------------


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
    """Patches JWT verification (same as test_backend_authentication.py)
    AND app.auth._resolve_admin_user_ids -- both read fresh on every call,
    no caching, so this is a faithful stand-in for the real env-var path."""

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
        for user_id in (USER_A, USER_B, ADMIN_USER):
            connection.execute(
                text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
                {"id": user_id},
            )


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                DELETE FROM startup_memberships
                WHERE user_id = ANY(:ids)
                   OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
            """),
            {"ids": [USER_A, USER_B, ADMIN_USER], "pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("""
                DELETE FROM startup_claims
                WHERE user_id = ANY(:ids)
                   OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
            """),
            {"ids": [USER_A, USER_B, ADMIN_USER], "pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("DELETE FROM saved_startups WHERE user_id = ANY(:ids)"),
            {"ids": [USER_A, USER_B, ADMIN_USER]},
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
            {"ids": [USER_A, USER_B, ADMIN_USER]},
        )


# --- 1-3: baseline submission behavior ---------------------------------------


def test_startup_memberships_untouched_by_submission() -> None:
    _ensure_test_users()
    try:
        with engine.begin() as connection:
            before = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()

        with _patched_auth():
            _, startup_id = "n/a", _make_test_startup("Baseline")
            response = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "I am the founder"},
                headers=_auth_headers(USER_A),
            )
            expect(response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}")

        with engine.begin() as connection:
            after = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()

        expect(after == before, "Claim submission must never create a startup_memberships row")
    finally:
        _cleanup()


def test_unauthenticated_submission_rejected() -> None:
    with _patched_auth():
        response = client.post("/startup-claims", json={"startup_id": 1, "justification": "x"})
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")


def test_authenticated_submission_creates_pending_claim() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("Pending")
        with _patched_auth():
            response = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "I am the founder"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}")
        expect(response.json()["status"] == "pending", "New claim must be pending")
    finally:
        _cleanup()


# --- 4-7: client cannot assign identity/state --------------------------------


def test_user_id_cannot_be_spoofed() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("SpoofUser")
        with _patched_auth():
            body = {"startup_id": startup_id, "justification": "x", "user_id": USER_B}
            response = client.post("/startup-claims", json=body, headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Create failed: {response.text}")

        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT user_id FROM startup_claims WHERE id = :id"), {"id": response.json()["id"]}
            ).mappings().first()
        expect(row["user_id"] == USER_A, f"Expected owner {USER_A}, got {row['user_id']!r} -- spoofed user_id must be ignored")
    finally:
        _cleanup()


def test_status_cannot_be_client_assigned() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("SpoofStatus")
        with _patched_auth():
            body = {"startup_id": startup_id, "justification": "x", "status": "approved"}
            response = client.post("/startup-claims", json=body, headers=_auth_headers(USER_A))
        expect(response.json()["status"] == "pending", "Client-supplied status must be ignored -- always pending")
    finally:
        _cleanup()


def test_verification_method_cannot_be_client_assigned() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("SpoofMethod")
        with _patched_auth():
            body = {"startup_id": startup_id, "justification": "x", "verification_method": "dns_proof"}
            response = client.post("/startup-claims", json=body, headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT verification_method FROM startup_claims WHERE id = :id"), {"id": response.json()["id"]}
            ).mappings().first()
        expect(row["verification_method"] == "manual_review", f"Expected manual_review, got {row['verification_method']!r}")
    finally:
        _cleanup()


def test_role_cannot_be_client_assigned() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("SpoofRole")
        with _patched_auth():
            body = {"startup_id": startup_id, "justification": "x", "role": "owner"}
            response = client.post("/startup-claims", json=body, headers=_auth_headers(USER_A))
            approve_response = client.post(
                f"/admin/startup-claims/{response.json()['id']}/approve", headers=_auth_headers(ADMIN_USER)
            )
        expect(approve_response.status_code == 200, f"Approve failed: {approve_response.text}")

        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT role FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).mappings().first()
        expect(row["role"] == "member", f"Role must always be 'member' regardless of client input, got {row['role']!r}")
    finally:
        _cleanup()


# --- 8-12: validation / lifecycle rules --------------------------------------


def test_nonexistent_startup_rejected_cleanly() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.post(
                "/startup-claims",
                json={"startup_id": 999999999, "justification": "x"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_duplicate_pending_claim_blocked() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("Duplicate")
        with _patched_auth():
            first = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            expect(first.status_code == 200, f"First claim failed: {first.text}")
            second = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "y"}, headers=_auth_headers(USER_A))
        expect(second.status_code == 409, f"Expected 409 for duplicate pending claim, got {second.status_code}")
    finally:
        _cleanup()


def test_rejected_claim_can_be_resubmitted() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("Resubmit")
        with _patched_auth():
            first = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            claim_id = first.json()["id"]
            reject_response = client.post(
                f"/admin/startup-claims/{claim_id}/reject",
                json={"rejection_reason": "Not enough evidence"},
                headers=_auth_headers(ADMIN_USER),
            )
            expect(reject_response.status_code == 200, f"Reject failed: {reject_response.text}")

            second = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "more context"}, headers=_auth_headers(USER_A))
        expect(second.status_code == 200, f"Resubmission after rejection should succeed, got {second.status_code}: {second.text}")
    finally:
        _cleanup()


def test_cancelled_claim_can_be_resubmitted() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("ResubmitCancel")
        with _patched_auth():
            first = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            claim_id = first.json()["id"]
            cancel_response = client.post(f"/me/startup-claims/{claim_id}/cancel", headers=_auth_headers(USER_A))
            expect(cancel_response.status_code == 200, f"Cancel failed: {cancel_response.text}")

            second = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "trying again"}, headers=_auth_headers(USER_A))
        expect(second.status_code == 200, f"Resubmission after cancellation should succeed, got {second.status_code}: {second.text}")
    finally:
        _cleanup()


def test_existing_member_cannot_create_unnecessary_claim() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("AlreadyMember")
        with _patched_auth():
            first = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            client.post(f"/admin/startup-claims/{first.json()['id']}/approve", headers=_auth_headers(ADMIN_USER))

            second = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "again"}, headers=_auth_headers(USER_A))
        expect(second.status_code == 409, f"Expected 409 for an already-a-member claim, got {second.status_code}")
    finally:
        _cleanup()


# --- 13-17: admin authorization ----------------------------------------------


def test_non_admin_cannot_list_admin_claims() -> None:
    with _patched_auth():
        response = client.get("/admin/startup-claims", headers=_auth_headers(USER_A))
        expect(response.status_code == 403, f"Expected 403, got {response.status_code}")


def test_non_admin_cannot_approve() -> None:
    with _patched_auth():
        response = client.post("/admin/startup-claims/1/approve", headers=_auth_headers(USER_A))
        expect(response.status_code == 403, f"Expected 403, got {response.status_code}")


def test_non_admin_cannot_reject() -> None:
    with _patched_auth():
        response = client.post(
            "/admin/startup-claims/1/reject",
            json={"rejection_reason": "no"},
            headers=_auth_headers(USER_A),
        )
        expect(response.status_code == 403, f"Expected 403, got {response.status_code}")


def test_empty_admin_user_ids_grants_nobody_admin() -> None:
    with _patched_auth(admin_ids=[]):
        response = client.get("/admin/startup-claims", headers=_auth_headers(ADMIN_USER))
        expect(response.status_code == 403, f"Empty ADMIN_USER_IDS must grant nobody admin, got {response.status_code}")


def test_admin_can_list_pending_claims() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("AdminList")
        with _patched_auth():
            client.post("/startup-claims", json={"startup_id": startup_id, "justification": "review me"}, headers=_auth_headers(USER_A))
            response = client.get("/admin/startup-claims", headers=_auth_headers(ADMIN_USER))
        expect(response.status_code == 200, f"Expected 200, got {response.status_code}")
        matching = [c for c in response.json() if c["startup_id"] == startup_id]
        expect(len(matching) == 1, "Admin should see the pending claim")
        expect(matching[0]["justification"] == "review me", "Admin should see the justification")
    finally:
        _cleanup()


# --- 18-24: approval/rejection semantics --------------------------------------


def test_approval_creates_exactly_one_membership() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("ApproveOne")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            client.post(f"/admin/startup-claims/{created.json()['id']}/approve", headers=_auth_headers(ADMIN_USER))

        with engine.begin() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).scalar()
        expect(count == 1, f"Expected exactly one membership, got {count}")
    finally:
        _cleanup()


def test_approved_membership_role_is_member() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("RoleCheck")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            client.post(f"/admin/startup-claims/{created.json()['id']}/approve", headers=_auth_headers(ADMIN_USER))

        with engine.begin() as connection:
            role = connection.execute(
                text("SELECT role FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).scalar()
        expect(role == "member", f"Expected role='member', got {role!r}")
    finally:
        _cleanup()


def test_approval_changes_claim_to_approved() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("StatusApproved")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            response = client.post(f"/admin/startup-claims/{created.json()['id']}/approve", headers=_auth_headers(ADMIN_USER))
        expect(response.json()["status"] == "approved", "Claim status must be 'approved'")
    finally:
        _cleanup()


def test_approval_records_reviewed_by() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("ReviewedBy")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            client.post(f"/admin/startup-claims/{created.json()['id']}/approve", headers=_auth_headers(ADMIN_USER))

        with engine.begin() as connection:
            reviewed_by = connection.execute(
                text("SELECT reviewed_by FROM startup_claims WHERE id = :id"), {"id": created.json()["id"]}
            ).scalar()
        expect(reviewed_by == ADMIN_USER, f"Expected reviewed_by={ADMIN_USER}, got {reviewed_by!r}")
    finally:
        _cleanup()


def test_duplicate_approval_does_not_duplicate_membership() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("DupApprove")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            claim_id = created.json()["id"]
            first_approve = client.post(f"/admin/startup-claims/{claim_id}/approve", headers=_auth_headers(ADMIN_USER))
            second_approve = client.post(f"/admin/startup-claims/{claim_id}/approve", headers=_auth_headers(ADMIN_USER))

        expect(first_approve.status_code == 200, "First approval should succeed")
        expect(second_approve.status_code == 409, f"Second approval on an already-approved claim should fail cleanly, got {second_approve.status_code}")

        with engine.begin() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).scalar()
        expect(count == 1, f"Expected exactly one membership after duplicate approval attempts, got {count}")
    finally:
        _cleanup()


def test_rejection_creates_zero_membership() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("RejectZero")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            client.post(
                f"/admin/startup-claims/{created.json()['id']}/reject",
                json={"rejection_reason": "Insufficient evidence"},
                headers=_auth_headers(ADMIN_USER),
            )

        with engine.begin() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).scalar()
        expect(count == 0, f"Rejection must create zero memberships, got {count}")
    finally:
        _cleanup()


def test_rejected_claim_contains_review_metadata() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("RejectMeta")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            client.post(
                f"/admin/startup-claims/{created.json()['id']}/reject",
                json={"rejection_reason": "Insufficient evidence"},
                headers=_auth_headers(ADMIN_USER),
            )
            my_claims = client.get("/me/startup-claims", headers=_auth_headers(USER_A))

        matching = next(c for c in my_claims.json() if c["id"] == created.json()["id"])
        expect(matching["status"] == "rejected", "Claim must show rejected status")
        expect(matching["rejection_reason"] == "Insufficient evidence", "Claimant must see their own rejection reason")
        expect(matching["reviewed_at"] is not None, "reviewed_at must be set")
    finally:
        _cleanup()


# --- 25-26: cross-user isolation on founder endpoints -----------------------


def test_one_user_cannot_inspect_another_users_claim() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("CrossUser")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "private reason"}, headers=_auth_headers(USER_A))
            b_claims = client.get("/me/startup-claims", headers=_auth_headers(USER_B))

        expect(
            all(c["id"] != created.json()["id"] for c in b_claims.json()),
            "USER_B must never see USER_A's claim via GET /me/startup-claims",
        )
    finally:
        _cleanup()


def test_guessing_claim_ids_does_not_bypass_authorization() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("GuessId")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            claim_id = created.json()["id"]

            # USER_B guesses USER_A's real claim_id and tries to cancel it.
            cancel_attempt = client.post(f"/me/startup-claims/{claim_id}/cancel", headers=_auth_headers(USER_B))
        expect(cancel_attempt.status_code == 404, f"Expected 404 (non-leaking), got {cancel_attempt.status_code}")

        with engine.begin() as connection:
            status = connection.execute(text("SELECT status FROM startup_claims WHERE id = :id"), {"id": claim_id}).scalar()
        expect(status == "pending", "USER_A's claim must be unaffected by USER_B's guess")
    finally:
        _cleanup()


# --- 27-28: multi-user / multi-startup ---------------------------------------


def test_two_users_can_submit_legitimate_claims_for_same_startup() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("Cofounders")
        with _patched_auth():
            claim_a = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "I'm a cofounder"}, headers=_auth_headers(USER_A))
            claim_b = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "I'm also a cofounder"}, headers=_auth_headers(USER_B))
        expect(claim_a.status_code == 200 and claim_b.status_code == 200, "Two different users must both be able to claim the same startup")
    finally:
        _cleanup()


def test_one_user_can_claim_multiple_startups() -> None:
    _ensure_test_users()
    try:
        startup_1 = _make_test_startup("Multi1")
        startup_2 = _make_test_startup("Multi2")
        with _patched_auth():
            claim_1 = client.post("/startup-claims", json={"startup_id": startup_1, "justification": "x"}, headers=_auth_headers(USER_A))
            claim_2 = client.post("/startup-claims", json={"startup_id": startup_2, "justification": "y"}, headers=_auth_headers(USER_A))
        expect(claim_1.status_code == 200 and claim_2.status_code == 200, "One user must be able to claim multiple different startups")
    finally:
        _cleanup()


# --- 29: approval race ------------------------------------------------------


def test_approval_race_cannot_create_duplicate_memberships() -> None:
    """Two threads call approve_startup_claim() on the SAME claim_id at
    (as close to) the same instant -- proves the FOR UPDATE row lock +
    ON CONFLICT DO NOTHING actually hold under real concurrent access."""
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("Race")
        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
        claim_id = created.json()["id"]

        results = []
        start_barrier = threading.Barrier(2)

        def worker():
            start_barrier.wait()
            results.append(approve_startup_claim(claim_id, ADMIN_USER))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [r for r in results if r is not None]
        expect(len(successes) == 1, f"Expected exactly one thread to win the approval race, got {len(successes)}")

        with engine.begin() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).scalar()
        expect(count == 1, f"Expected exactly one membership after a concurrent approval race, got {count}")
    finally:
        _cleanup()


# --- 30-31: no cross-contamination with other systems -----------------------


def test_claim_submission_never_modifies_saved_startups() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("NoSavedEffect")
        with engine.begin() as connection:
            before = connection.execute(text("SELECT COUNT(*) FROM saved_startups")).scalar()

        with _patched_auth():
            client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))

        with engine.begin() as connection:
            after = connection.execute(text("SELECT COUNT(*) FROM saved_startups")).scalar()
        expect(after == before, "Claim submission must never touch saved_startups")
    finally:
        _cleanup()


def test_claim_lifecycle_never_modifies_analyses_or_sps() -> None:
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("NoAnalysesEffect")
        with engine.begin() as connection:
            before_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()
            before_methodology = connection.execute(
                text("SELECT methodology FROM analyses WHERE startup_id = :s ORDER BY id DESC LIMIT 1"),
                {"s": startup_id},
            ).scalar()

        with _patched_auth():
            created = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            client.post(f"/admin/startup-claims/{created.json()['id']}/approve", headers=_auth_headers(ADMIN_USER))

        with engine.begin() as connection:
            after_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()
            after_methodology = connection.execute(
                text("SELECT methodology FROM analyses WHERE startup_id = :s ORDER BY id DESC LIMIT 1"),
                {"s": startup_id},
            ).scalar()

        expect(after_analyses == before_analyses, "Claim lifecycle must never create/delete an analyses row")
        expect(before_methodology == after_methodology, "Claim lifecycle must never alter methodology/SPS JSONB")
    finally:
        _cleanup()


# --- 32: intelligence endpoints now require auth -----------------------------


def test_intelligence_endpoints_now_require_auth() -> None:
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility supersedes this
    test's original "remain public" assertion (approved decision: no
    public scores-only exception). /rankings and /discover now require
    auth; an authenticated admin (this file's own existing fixture) can
    still reach them.
    """
    _ensure_test_users()
    with _patched_auth():
        expect(client.get("/rankings").status_code == 401, "/rankings must require auth")
        expect(client.get("/discover").status_code == 401, "/discover must require auth")

        expect(
            client.get("/rankings", headers=_auth_headers(ADMIN_USER)).status_code == 200,
            "An authenticated caller must still reach /rankings",
        )
        expect(
            client.get("/discover", headers=_auth_headers(ADMIN_USER)).status_code == 200,
            "An authenticated caller must still reach /discover",
        )

    # DB-layer: admin bypass, same reasoning as this file's other
    # unrelated-to-authorization sanity checks.
    expect(len(get_rankings("__task3b_sanity_admin__", True)) >= 0, "get_rankings() must still run")
    expect(len(discover_startups("__task3b_sanity_admin__", True)) >= 0, "discover_startups() must still run")


# --- Phase 32A -- Trust-State Consistency ------------------------------------
#
# GET /me/startup-claims/{startup_id} (ClaimStartupButton.tsx's own data
# source) now exposes verification_method -- the exact same column
# list_startup_claims_for_user() already returned, just missing from this
# one response. venture_graduation-tagged claims are never created
# through the public POST /startup-claims endpoint (see
# test_verification_method_cannot_be_client_assigned above) -- graduation
# only ever creates and self-approves one internally, via
# create_startup_claim()/approve_startup_claim() directly, exactly as
# _ensure_graduation_membership() in app/database/db.py does. These tests
# call those same two functions the same way, rather than re-implementing
# the graduation HTTP flow, to isolate what's actually being verified
# here: the exposed field, not the graduation mechanism itself (already
# covered by test_venture_graduation.py, untouched by this phase).


def test_graduation_relationship_exposes_venture_graduation() -> None:
    """A. Idea -> Startup graduation relationship renders Founder-managed
    -- i.e. the field the frontend branches on is exactly
    "venture_graduation" for a self-approved graduation claim."""
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("GradTrust")
        claim_id = create_startup_claim(
            user_id=USER_A,
            startup_id=startup_id,
            justification="Created via venture graduation.",
            contact_email=None,
            verification_method="venture_graduation",
        )
        approve_startup_claim(claim_id, admin_user_id=USER_A)  # self-approval, exactly as graduation does

        with _patched_auth():
            response = client.get(f"/me/startup-claims/{startup_id}", headers=_auth_headers(USER_A))

        expect(response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}")
        body = response.json()
        expect(body is not None, "A self-approved graduation claim must be visible to its own creator")
        expect(
            body["verification_method"] == "venture_graduation",
            f"Expected verification_method 'venture_graduation', got {body.get('verification_method')!r}",
        )
    finally:
        _cleanup()


def test_reviewed_claim_exposes_manual_review() -> None:
    """B. An independently reviewed (admin-approved) claim renders
    Verified -- verification_method is "manual_review", the real
    endpoint's own default for every claim a founder submits themselves."""
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("VerifiedTrust")
        with _patched_auth():
            created = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "I run this company"},
                headers=_auth_headers(USER_A),
            )
            expect(created.status_code == 200, f"Expected 200, got {created.status_code}: {created.text}")
            approve = client.post(f"/admin/startup-claims/{created.json()['id']}/approve", headers=_auth_headers(ADMIN_USER))
            expect(approve.status_code == 200, f"Expected 200, got {approve.status_code}: {approve.text}")

            response = client.get(f"/me/startup-claims/{startup_id}", headers=_auth_headers(USER_A))

        expect(response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}")
        body = response.json()
        expect(body is not None, "An approved claim must be visible to its own creator")
        expect(
            body["verification_method"] == "manual_review",
            f"Expected verification_method 'manual_review', got {body.get('verification_method')!r}",
        )
    finally:
        _cleanup()


def test_founder_managed_never_reads_as_manual_review() -> None:
    """C. Founder-managed cannot accidentally render Verified -- the exact
    value ClaimStartupButton.tsx checks against ('venture_graduation')
    must never collapse into the 'manual_review' bucket for a graduation
    claim, however it's read back."""
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("NoFalseVerified")
        claim_id = create_startup_claim(
            user_id=USER_A,
            startup_id=startup_id,
            justification="Created via venture graduation.",
            contact_email=None,
            verification_method="venture_graduation",
        )
        approve_startup_claim(claim_id, admin_user_id=USER_A)

        with _patched_auth():
            response = client.get(f"/me/startup-claims/{startup_id}", headers=_auth_headers(USER_A))

        body = response.json()
        expect(
            body["verification_method"] != "manual_review",
            "A venture-graduation claim must never expose verification_method='manual_review' -- that would render as the wrong trust badge (Verified instead of Founder-managed)",
        )
    finally:
        _cleanup()


def test_verified_never_reads_as_venture_graduation() -> None:
    """D. A Verified claim cannot accidentally render Founder-managed --
    the mirror image of C, for the ordinary admin-reviewed path."""
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("NoFalseFounderManaged")
        with _patched_auth():
            created = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "I run this company"},
                headers=_auth_headers(USER_A),
            )
            client.post(f"/admin/startup-claims/{created.json()['id']}/approve", headers=_auth_headers(ADMIN_USER))
            response = client.get(f"/me/startup-claims/{startup_id}", headers=_auth_headers(USER_A))

        body = response.json()
        expect(
            body["verification_method"] != "venture_graduation",
            "An admin-reviewed claim must never expose verification_method='venture_graduation' -- that would render as the wrong trust badge (Founder-managed instead of Verified)",
        )
    finally:
        _cleanup()


def test_founder_workspace_access_unchanged_by_trust_state() -> None:
    """E. Existing Founder Workspace access behavior is unchanged: a
    self-approved (Founder-managed) membership grants exactly the same
    real startup_memberships row -- and therefore the same
    RequireStartupMember-gated access -- as an admin-reviewed (Verified)
    one. Exposing verification_method on the read side must not have
    touched who can get in."""
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("AccessUnchanged")
        claim_id = create_startup_claim(
            user_id=USER_A,
            startup_id=startup_id,
            justification="Created via venture graduation.",
            contact_email=None,
            verification_method="venture_graduation",
        )
        approve_startup_claim(claim_id, admin_user_id=USER_A)

        expect(
            user_has_startup_membership(USER_A, startup_id),
            "A self-approved graduation-style claim must still grant a real startup_memberships row, exactly as before this phase",
        )

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Founder-managed membership must still pass RequireStartupMember -- expected 200, got {response.status_code}: {response.text}")
    finally:
        _cleanup()


def test_claim_and_graduation_mechanics_unchanged() -> None:
    """F. Existing claim/graduation mechanics are unchanged: submission,
    approval, and membership-granting all behave exactly as they did
    before this phase -- this phase only added a SELECT column and a
    response field, never touched a write path."""
    _ensure_test_users()
    try:
        startup_id = _make_test_startup("MechanicsUnchanged")
        with _patched_auth():
            created = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "x"},
                headers=_auth_headers(USER_A),
            )
        expect(created.status_code == 200, f"Expected 200, got {created.status_code}: {created.text}")
        expect(created.json()["status"] == "pending", "New claim must still be pending before approval")
        expect(
            not user_has_startup_membership(USER_A, startup_id),
            "Submitting a claim must still never create a membership on its own",
        )

        with _patched_auth():
            approve = client.post(f"/admin/startup-claims/{created.json()['id']}/approve", headers=_auth_headers(ADMIN_USER))
        expect(approve.status_code == 200, f"Expected 200, got {approve.status_code}: {approve.text}")
        expect(
            user_has_startup_membership(USER_A, startup_id),
            "Approval must still grant a real startup_memberships row",
        )
    finally:
        _cleanup()


TESTS = [
    test_startup_memberships_untouched_by_submission,
    test_unauthenticated_submission_rejected,
    test_authenticated_submission_creates_pending_claim,
    test_user_id_cannot_be_spoofed,
    test_status_cannot_be_client_assigned,
    test_verification_method_cannot_be_client_assigned,
    test_role_cannot_be_client_assigned,
    test_nonexistent_startup_rejected_cleanly,
    test_duplicate_pending_claim_blocked,
    test_rejected_claim_can_be_resubmitted,
    test_cancelled_claim_can_be_resubmitted,
    test_existing_member_cannot_create_unnecessary_claim,
    test_non_admin_cannot_list_admin_claims,
    test_non_admin_cannot_approve,
    test_non_admin_cannot_reject,
    test_empty_admin_user_ids_grants_nobody_admin,
    test_admin_can_list_pending_claims,
    test_approval_creates_exactly_one_membership,
    test_approved_membership_role_is_member,
    test_approval_changes_claim_to_approved,
    test_approval_records_reviewed_by,
    test_duplicate_approval_does_not_duplicate_membership,
    test_rejection_creates_zero_membership,
    test_rejected_claim_contains_review_metadata,
    test_one_user_cannot_inspect_another_users_claim,
    test_guessing_claim_ids_does_not_bypass_authorization,
    test_two_users_can_submit_legitimate_claims_for_same_startup,
    test_one_user_can_claim_multiple_startups,
    test_approval_race_cannot_create_duplicate_memberships,
    test_claim_submission_never_modifies_saved_startups,
    test_claim_lifecycle_never_modifies_analyses_or_sps,
    test_intelligence_endpoints_now_require_auth,
    test_graduation_relationship_exposes_venture_graduation,
    test_reviewed_claim_exposes_manual_review,
    test_founder_managed_never_reads_as_manual_review,
    test_verified_never_reads_as_venture_graduation,
    test_founder_workspace_access_unchanged_by_trust_state,
    test_claim_and_graduation_mechanics_unchanged,
]


def main() -> None:
    print("\nPhase 7.1A -- Startup Claim & Membership tests")
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
