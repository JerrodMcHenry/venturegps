"""
Regression tests for Portfolio Release Task 4 -- My Analyses:
GET /me/analyses (app/api.py) and app/database/db.py's get_my_analyses().

Central thesis under test: My Analyses is scoped by ONE rule only --
analyses.submitted_by_user_id = the caller -- never by startup_memberships,
never by saved_startups, and never by admin status. Two users analyzing the
SAME company each see only their own submission in their own list, newest
first, and each entry's startup_id/company_name is enough to reopen the
exact same authorized report GET /startup/{name} already gates.

Reuses the exact same local-RSA-keypair JWT-mocking harness every other
app/tests/*.py file in this session already uses. Every row here uses a
distinctive zztest_myanalyses_* user-id prefix and "ZZTest MyAnalyses"
company-name prefix, cleaned up in a finally block even on failure. No test
here makes an LLM/Tavily call.

Run with:
    python -m app.tests.test_my_analyses
"""

import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.ai.sie_v2_methodology import METHODOLOGY_VERSION
from app.database.db import engine, get_or_create_startup, get_my_analyses, save_analysis

TEST_PREFIX = "ZZTest MyAnalyses"
USER_A = "zztest_myanalyses_user_a"
USER_B = "zztest_myanalyses_user_b"
ALL_USERS = [USER_A, USER_B]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"

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


def _make_token(sub: str) -> str:
    now = int(time.time())
    payload = {"sub": sub, "iss": TEST_ISSUER, "azp": TEST_AZP, "iat": now, "exp": now + 3600}
    return pyjwt.encode(payload, _private_key, algorithm="RS256")


class _patched_auth:
    def __enter__(self):
        self._orig_issuer = auth.CLERK_ISSUER
        self._orig_jwks_client = auth._jwks_client
        self._orig_resolve_parties = auth._resolve_authorized_parties
        self._orig_resolve_admins = auth._resolve_admin_user_ids

        auth.CLERK_ISSUER = TEST_ISSUER
        auth._jwks_client = lambda: _FakeJWKSClient()
        auth._resolve_authorized_parties = lambda: [TEST_AZP]
        auth._resolve_admin_user_ids = lambda: []
        return self

    def __exit__(self, *exc):
        auth.CLERK_ISSUER = self._orig_issuer
        auth._jwks_client = self._orig_jwks_client
        auth._resolve_authorized_parties = self._orig_resolve_parties
        auth._resolve_admin_user_ids = self._orig_resolve_admins
        return False


def _auth_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in ALL_USERS:
            connection.execute(
                text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"), {"id": user_id}
            )


def _canonical_methodology(sps: float) -> dict:
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


def _submit(company_name: str, submitted_by_user_id: str, sps: float = 70.0) -> int:
    """Real save_analysis() call -- returns the new analyses.id."""
    return save_analysis(
        company_text=f"Confidential test company text for {company_name}",
        summary="s", risk_analysis="r", competitor_analysis="c", memo="m",
        structured_analysis={"company_name": company_name, "industry": "SaaS", "stage": "Seed", "business_model": "SaaS"},
        investment_score={}, founder_analysis={}, market_analysis={}, sources=[], traction_analysis={},
        market_score=None, team_score=None, product_score=None, competition_score=None,
        traction_score=None, financial_score=None, overall_score=None, recommendation=None,
        readiness_score=None, readiness_summary=None,
        methodology=_canonical_methodology(sps),
        submitted_by_user_id=submitted_by_user_id,
    )


def _grant_membership(user_id: str, startup_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO startup_memberships (user_id, startup_id, role)
                VALUES (:user_id, :startup_id, 'member')
                ON CONFLICT (user_id, startup_id) DO NOTHING
            """),
            {"user_id": user_id, "startup_id": startup_id},
        )


def _save_bookmark(user_id: str, startup_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO saved_startups (user_id, startup_id)
                VALUES (:user_id, :startup_id)
                ON CONFLICT (user_id, startup_id) DO NOTHING
            """),
            {"user_id": user_id, "startup_id": startup_id},
        )


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                DELETE FROM startup_memberships WHERE startup_id IN (
                    SELECT id FROM startups WHERE normalized_name LIKE :pattern
                )
            """),
            {"pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("""
                DELETE FROM saved_startups WHERE startup_id IN (
                    SELECT id FROM startups WHERE normalized_name LIKE :pattern
                )
            """),
            {"pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("DELETE FROM analyses WHERE company_name ILIKE :pattern"), {"pattern": f"{TEST_PREFIX}%"}
        )
        connection.execute(
            text("DELETE FROM startups WHERE normalized_name LIKE :pattern"), {"pattern": f"{TEST_PREFIX.lower()}%"}
        )
        connection.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ALL_USERS})


# --- 1: anonymous access rejected -------------------------------------------


def test_anonymous_access_rejected() -> None:
    response = client.get("/me/analyses")
    expect(response.status_code == 401, f"Expected 401 for anonymous access, got {response.status_code}")


# --- 2: owner sees their own submissions, newest first ----------------------


def test_owner_sees_own_analyses_newest_first() -> None:
    _ensure_test_users()
    older = f"{TEST_PREFIX} Older"
    newer = f"{TEST_PREFIX} Newer"
    try:
        _submit(older, USER_A, sps=40.0)
        time.sleep(0.01)
        _submit(newer, USER_A, sps=91.0)

        with _patched_auth():
            response = client.get("/me/analyses", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")

        body = response.json()
        names = [row["company_name"] for row in body]
        expect(names[:2] == [newer, older], f"Expected newest first, got {names[:2]!r}")
        expect(body[0]["overall_score"] == 91.0, "Newest entry's score must be the real submitted score")
    finally:
        _cleanup()


# --- 3: an unrelated user's list never includes another user's analysis ----


def test_analyses_scoped_strictly_to_submitter() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} ScopedToSubmitter"
    try:
        _submit(company_name, USER_A, sps=55.0)

        with _patched_auth():
            b_response = client.get("/me/analyses", headers=_auth_headers(USER_B))
        expect(b_response.status_code == 200, f"Expected 200: {b_response.text}")
        expect(
            all(row["company_name"] != company_name for row in b_response.json()),
            "USER_B's My Analyses must never include USER_A's submission",
        )
    finally:
        _cleanup()


# --- 4: two users analyzing the same company each see only their own -------


def test_two_users_same_company_each_see_only_their_own_submission() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} SameCompany"
    try:
        _submit(company_name, USER_A, sps=12.0)
        time.sleep(0.01)
        _submit(company_name, USER_B, sps=88.0)

        with _patched_auth():
            a_response = client.get("/me/analyses", headers=_auth_headers(USER_A))
            b_response = client.get("/me/analyses", headers=_auth_headers(USER_B))

        a_rows = [r for r in a_response.json() if r["company_name"] == company_name]
        b_rows = [r for r in b_response.json() if r["company_name"] == company_name]

        expect(len(a_rows) == 1 and a_rows[0]["overall_score"] == 12.0, f"Expected USER_A's own (12.0) score only, got {a_rows}")
        expect(len(b_rows) == 1 and b_rows[0]["overall_score"] == 88.0, f"Expected USER_B's own (88.0) score only, got {b_rows}")
    finally:
        _cleanup()


# --- 5: bookmarks and startup membership never grant My Analyses visibility -


def test_bookmark_does_not_surface_another_users_analysis() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} BookmarkNoGrant"
    try:
        analysis_id = _submit(company_name, USER_A, sps=33.0)
        startup_id = get_or_create_startup(company_name)
        _save_bookmark(USER_B, startup_id)

        with _patched_auth():
            b_response = client.get("/me/analyses", headers=_auth_headers(USER_B))
        expect(
            all(row["company_name"] != company_name for row in b_response.json()),
            "Bookmarking a startup another user analyzed must never surface that analysis in My Analyses",
        )

        # DB-layer double check, no HTTP involved.
        b_direct = get_my_analyses(USER_B)
        expect(
            all(row["analysis_id"] != analysis_id for row in b_direct),
            "get_my_analyses() itself must never include a bookmarked-but-not-submitted analysis",
        )
    finally:
        _cleanup()


def test_startup_membership_does_not_surface_another_users_analysis() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} MembershipNoGrant"
    try:
        _submit(company_name, USER_A, sps=44.0)
        startup_id = get_or_create_startup(company_name)
        _grant_membership(USER_B, startup_id)

        with _patched_auth():
            b_response = client.get("/me/analyses", headers=_auth_headers(USER_B))
        expect(
            all(row["company_name"] != company_name for row in b_response.json()),
            "Being an approved member of USER_A's startup must never surface USER_A's analysis in USER_B's My Analyses",
        )
    finally:
        _cleanup()


# --- 6: each entry carries enough to reopen the correct authorized report ---


def test_entry_reopens_the_correct_authorized_report() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Reopen"
    try:
        _submit(company_name, USER_A, sps=77.0)
        startup_id = get_or_create_startup(company_name)

        with _patched_auth():
            list_response = client.get("/me/analyses", headers=_auth_headers(USER_A))
            row = next(r for r in list_response.json() if r["company_name"] == company_name)
            expect(row["startup_id"] == startup_id, "Entry's startup_id must match the real canonical startup")

            profile_response = client.get(f"/startup/{company_name}", headers=_auth_headers(USER_A))
        expect(profile_response.status_code == 200, f"Expected 200 reopening the report: {profile_response.text}")
        expect(
            profile_response.json()["methodology"]["startup_intelligence_score"] == 77.0,
            "Reopening via the entry's own company_name must show the same real score",
        )
    finally:
        _cleanup()


TESTS = [
    test_anonymous_access_rejected,
    test_owner_sees_own_analyses_newest_first,
    test_analyses_scoped_strictly_to_submitter,
    test_two_users_same_company_each_see_only_their_own_submission,
    test_bookmark_does_not_surface_another_users_analysis,
    test_startup_membership_does_not_surface_another_users_analysis,
    test_entry_reopens_the_correct_authorized_report,
]


def main() -> None:
    print("\nPortfolio Release Task 4 -- My Analyses tests")
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
