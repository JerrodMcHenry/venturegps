"""
Regression tests for Phase 7.2 -- Founder Workspace V1:
app/database/db.py's get_founder_startup_workspace(), and the
GET /founder/startups/{startup_id} endpoint in app/api.py (gated by
app/auth.py's RequireStartupMember).

Reuses the exact same local-RSA-keypair JWT-mocking harness as
test_startup_claims.py/test_startup_membership.py (no live Clerk
dependency). Every row here uses a distinctive zztest_founder_* user-id
prefix and a "ZZTest Founder" company-name prefix, cleaned up in a
finally block even on failure. No test here makes an LLM/Tavily call.

Central thesis under test: GET /founder/startups/{startup_id} is
authorized ONLY by a live startup_memberships row (via
RequireStartupMember) -- never by startup_claims history, saved_startups,
modeled_ventures, or anything client-supplied -- and it never fabricates
intelligence for a startup with no canonical analysis yet.

Run with:
    python -m app.tests.test_founder_workspace
"""

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
    save_analysis,
    save_startup_for_user,
    create_modeled_venture,
)

USER_A = "zztest_founder_user_a"
USER_B = "zztest_founder_user_b"
ADMIN_USER = "zztest_founder_admin"
ALL_USERS = [USER_A, USER_B, ADMIN_USER]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_PREFIX = "ZZTest Founder"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


# --- JWT mocking harness (identical pattern to prior phases' tests) --------


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


def _make_analyzed_startup(name_suffix: str, submitted_by_user_id: str | None = None, sps: float = 70.0) -> int:
    company_name = f"{TEST_PREFIX} {name_suffix}"
    save_analysis(
        company_text=f"Test company text for {company_name}",
        summary="s", risk_analysis="r", competitor_analysis="c", memo="m",
        structured_analysis={"company_name": company_name, "industry": "SaaS", "stage": "Seed", "business_model": "SaaS"},
        investment_score={}, founder_analysis={}, market_analysis={}, sources=[], traction_analysis={},
        market_score=None, team_score=None, product_score=None, competition_score=None,
        traction_score=None, financial_score=None, overall_score=None, recommendation=None,
        readiness_score=None, readiness_summary=None,
        methodology=_canonical_methodology(sps),
        submitted_by_user_id=submitted_by_user_id,
    )
    return get_or_create_startup(company_name)


def _make_unanalyzed_startup(name_suffix: str) -> int:
    """A startup that exists (startups row) but has zero canonical
    analyses -- e.g. reachable only via a claim, never via /analyze."""
    return get_or_create_startup(f"{TEST_PREFIX} {name_suffix}")


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in ALL_USERS:
            connection.execute(
                text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
                {"id": user_id},
            )


def _grant_membership(user_id: str, startup_id: int, role: str = "member") -> None:
    """Test-fixture-only direct insert -- see test_startup_membership.py's
    identical helper for why this is test setup, not an application write
    path (the real path is approve_startup_claim(), exercised elsewhere)."""
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO startup_memberships (user_id, startup_id, role)
            VALUES (:user_id, :startup_id, :role)
            ON CONFLICT (user_id, startup_id) DO NOTHING
        """), {"user_id": user_id, "startup_id": startup_id, "role": role})


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


# --- 1-2: authentication gate -------------------------------------------------


def test_unauthenticated_workspace_access_rejected() -> None:
    startup_id = _make_analyzed_startup("Unauth")
    try:
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")
    finally:
        _cleanup()


def test_signed_in_no_membership_denied() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoMembership")
    try:
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


# --- 3: member can access their own workspace ---------------------------------


def test_member_can_access_own_workspace() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("OwnAccess")
    try:
        _grant_membership(USER_A, startup_id)

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")

        body = response.json()
        expect(body["startup_id"] == startup_id, "startup_id must match")
        expect(body["canonical_name"] == f"{TEST_PREFIX} OwnAccess", f"Unexpected canonical_name {body['canonical_name']!r}")
        expect(body["methodology"] is not None, "Expected real methodology for an analyzed startup")
        expect(body["methodology"]["startup_intelligence_score"] == 70.0, "SPS must match the stored analysis")
        expect(len(body["sps_history"]) == 1, f"Expected 1 history point, got {len(body['sps_history'])}")
    finally:
        _cleanup()


# --- 4-5: cross-startup isolation and ID-guessing -----------------------------


def test_member_cannot_access_other_startup_by_changing_url() -> None:
    _ensure_test_users()
    startup_a = _make_analyzed_startup("MineA")
    startup_b = _make_analyzed_startup("NotMineB")
    try:
        _grant_membership(USER_A, startup_a)

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_b}", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
        # Confirms this wasn't a data leak dressed as a different status --
        # no methodology/canonical_name for Startup B should ever be
        # present in the response body a non-member receives.
        expect("methodology" not in response.json() or response.json().get("methodology") in (None,), "Response must not leak Startup B's data")
    finally:
        _cleanup()


def test_guessing_startup_id_reveals_nothing() -> None:
    _ensure_test_users()
    real_other_startup = _make_analyzed_startup("RealNotMine")
    nonexistent_startup_id = 999999999
    try:
        with _patched_auth():
            response_real = client.get(f"/founder/startups/{real_other_startup}", headers=_auth_headers(USER_A))
            response_fake = client.get(f"/founder/startups/{nonexistent_startup_id}", headers=_auth_headers(USER_A))

        expect(response_real.status_code == 404, f"Expected 404, got {response_real.status_code}")
        expect(response_fake.status_code == 404, f"Expected 404, got {response_fake.status_code}")
        expect(
            response_real.json() == response_fake.json(),
            "A real-but-unowned startup and a nonexistent one must return identical responses",
        )
    finally:
        _cleanup()


# --- 6-8: adjacent tables never authorize Founder Workspace -------------------


def test_approved_claim_without_membership_does_not_authorize_workspace() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ApprovedNoMembership")
    try:
        with _patched_auth(admin_ids=[ADMIN_USER]):
            submitted = client.post(
                "/startup-claims",
                json={"startup_id": startup_id, "justification": "x"},
                headers=_auth_headers(USER_A),
            )
            claim_id = submitted.json()["id"]
            approved = client.post(f"/admin/startup-claims/{claim_id}/approve", headers=_auth_headers(ADMIN_USER))
            expect(approved.status_code == 200, f"Approval failed: {approved.text}")

            # Simulate the membership being removed later while the claim
            # row still reads 'approved' -- no removal feature exists yet
            # (Phase 7.1C's own documented limitation), so this is done
            # directly, purely to prove the read side never trusts claim
            # history alone.
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                    {"u": USER_A, "s": startup_id},
                )

            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"An approved-but-removed membership must not authorize Founder Workspace, got {response.status_code}")
    finally:
        _cleanup()


def test_saved_startup_does_not_authorize_workspace() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SavedNotMember")
    try:
        save_startup_for_user(USER_A, startup_id)

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Saving a startup must not authorize Founder Workspace, got {response.status_code}")
    finally:
        _cleanup()


def test_modeled_venture_does_not_authorize_workspace() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("VentureNotMember")
    try:
        create_modeled_venture(
            user_id=USER_A, name="Some idea", description=None, industry=None,
            business_model=None, target_customer=None, stage=None,
            assumptions={}, model_result=None,
        )

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"A modeled venture must not authorize Founder Workspace, got {response.status_code}")
    finally:
        _cleanup()


# --- 9-10: response shape and honesty about missing intelligence -------------


def test_multiple_users_each_see_only_their_own_startup() -> None:
    _ensure_test_users()
    startup_a = _make_analyzed_startup("MultiUserA")
    startup_b = _make_analyzed_startup("MultiUserB")
    try:
        _grant_membership(USER_A, startup_a)
        _grant_membership(USER_B, startup_b)

        with _patched_auth():
            response_a = client.get(f"/founder/startups/{startup_a}", headers=_auth_headers(USER_A))
            response_b = client.get(f"/founder/startups/{startup_b}", headers=_auth_headers(USER_B))
            cross_a = client.get(f"/founder/startups/{startup_b}", headers=_auth_headers(USER_A))
            cross_b = client.get(f"/founder/startups/{startup_a}", headers=_auth_headers(USER_B))

        expect(response_a.status_code == 200 and response_a.json()["startup_id"] == startup_a, "USER_A must access their own startup")
        expect(response_b.status_code == 200 and response_b.json()["startup_id"] == startup_b, "USER_B must access their own startup")
        expect(cross_a.status_code == 404, "USER_A must not access Startup B")
        expect(cross_b.status_code == 404, "USER_B must not access Startup A")
    finally:
        _cleanup()


# --- 9b-9d: final security review -- membership is not a general grant ------
#
# Found and fixed during the Task 3B pre-commit security review:
# get_founder_startup_workspace() picked the latest analysis for a
# startup_id by RequireStartupMember-verified membership alone, with no
# reference to submitted_by_user_id at all -- so an approved member could
# read a *different* member's privately-submitted analysis of the same
# startup, the exact cross-user confidentiality bug
# _analysis_visibility_clause() was tightened to prevent everywhere else.
# These tests cover the two members sharing one startup_memberships-
# gated startup, which the earlier single-owner tests above never
# exercised (their fixtures only ever created NULL-owner analyses).


def test_approved_member_cannot_read_another_members_private_analysis() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SharedPrivate", submitted_by_user_id=USER_A, sps=91.0)
    try:
        _grant_membership(USER_A, startup_id)
        _grant_membership(USER_B, startup_id)  # also approved -- not the submitter

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_B))
        expect(response.status_code == 200, f"Expected 200 (workspace still resolves): {response.text}")

        body = response.json()
        expect(
            body["methodology"] is None,
            "An approved member who did not submit the analysis must not see another member's private "
            f"analysis content -- got methodology={body['methodology']!r}",
        )
        expect(body["sps_history"] == [], "The other member's private analysis must not appear in sps_history either")
    finally:
        _cleanup()


def test_submitting_founder_still_sees_their_own_report_via_workspace() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SubmitterAccess", submitted_by_user_id=USER_A, sps=91.0)
    try:
        _grant_membership(USER_A, startup_id)

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")

        body = response.json()
        expect(body["methodology"] is not None, "The submitter must still see their own just-submitted report")
        expect(body["methodology"]["startup_intelligence_score"] == 91.0, "The submitter's real score must be returned")
        expect(len(body["sps_history"]) == 1, "The submitter's own analysis must appear in their own sps_history")
    finally:
        _cleanup()


def test_approved_member_still_sees_historical_null_owner_analysis() -> None:
    """Preserving existing founder access: a member who did NOT submit a
    historical (pre-migration, NULL-owner) analysis must still see it --
    only a real, different submitter blocks visibility, not membership
    itself."""
    _ensure_test_users()
    startup_id = _make_analyzed_startup("HistoricalStillVisible", submitted_by_user_id=None, sps=55.0)
    try:
        _grant_membership(USER_B, startup_id)  # never submitted anything

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_B))
        expect(response.status_code == 200, f"Expected 200: {response.text}")

        body = response.json()
        expect(body["methodology"] is not None, "A historical NULL-owner analysis must remain visible to an approved member")
        expect(body["methodology"]["startup_intelligence_score"] == 55.0, "The historical score must be returned")
    finally:
        _cleanup()


def test_unanalyzed_startup_never_fabricates_intelligence() -> None:
    _ensure_test_users()
    startup_id = _make_unanalyzed_startup("NeverAnalyzed")
    try:
        _grant_membership(USER_A, startup_id)

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")

        body = response.json()
        expect(body["methodology"] is None, "A startup with zero canonical analyses must report methodology=None, never a fabricated score")
        expect(body["created_at"] is None, "created_at must be None with no canonical analysis")
        expect(body["sps_history"] == [], "sps_history must be an honest empty list")
        expect(body["canonical_name"] == f"{TEST_PREFIX} NeverAnalyzed", "canonical_name must still resolve from the startups row itself")
    finally:
        _cleanup()


def test_workspace_access_creates_no_membership_side_effects() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoSideEffects")
    try:
        _grant_membership(USER_A, startup_id)

        with engine.begin() as connection:
            before = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()

        with _patched_auth():
            for _ in range(3):
                response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
                expect(response.status_code == 200, f"Expected 200: {response.text}")

        with engine.begin() as connection:
            after = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()
        expect(after == before, "Reading Founder Workspace must never create/modify startup_memberships rows")
    finally:
        _cleanup()


TESTS = [
    test_unauthenticated_workspace_access_rejected,
    test_signed_in_no_membership_denied,
    test_member_can_access_own_workspace,
    test_member_cannot_access_other_startup_by_changing_url,
    test_guessing_startup_id_reveals_nothing,
    test_approved_claim_without_membership_does_not_authorize_workspace,
    test_saved_startup_does_not_authorize_workspace,
    test_modeled_venture_does_not_authorize_workspace,
    test_multiple_users_each_see_only_their_own_startup,
    test_approved_member_cannot_read_another_members_private_analysis,
    test_submitting_founder_still_sees_their_own_report_via_workspace,
    test_approved_member_still_sees_historical_null_owner_analysis,
    test_unanalyzed_startup_never_fabricates_intelligence,
    test_workspace_access_creates_no_membership_side_effects,
]


def main() -> None:
    print("\nPhase 7.2 -- Founder Workspace V1 tests")
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
