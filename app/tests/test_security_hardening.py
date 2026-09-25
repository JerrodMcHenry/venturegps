"""
Regression tests for Phase 10.1A -- Critical Security + Runtime
Hardening.

Covers the two concrete authorization gaps closed in app/api.py:

1. The five legacy raw-analysis-row endpoints (GET /analyses,
   GET /analyses/{id}, GET /analyses/{id}/pdf, PUT /analyses/{id},
   DELETE /analyses/{id}) now require RequireAdmin. Confirmed by
   repository search (see the audit report) that no current frontend
   code calls any of these five -- GET /analyses/search is the one
   member of the /analyses family that IS still used (by the public
   /search page) and is deliberately left untouched/public here, since
   it only ever returns company_name/summary/overall_score, the same
   public tier as Rankings/Discovery/Startup Profile.

2. The three /migrate/* HTTP routes were removed outright (not merely
   gated) since they were confirmed redundant with the migration
   functions that already run unconditionally at process startup, and
   confirmed unused by the frontend. This file asserts they are no
   longer registered as routes at all.

/analyze-pdf's event-loop-blocking fix has its own dedicated behavioral
(real-uvicorn-server) test in test_analyze_unified_concurrency.py, not
here -- that property needs a real ASGI server, not a TestClient, so it
doesn't fit this file's harness.

Reuses the exact same local-RSA-keypair JWT-mocking harness as every
other phase's test file (no live Clerk dependency). Every row here uses
a distinctive zztest_security_* user-id prefix and a "ZZTest Security"
company-name prefix, cleaned up in a finally block even on failure.

Run with:
    python -m app.tests.test_security_hardening
"""

import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.database.db import engine, get_or_create_startup, save_analysis

NORMAL_USER = "zztest_security_normal_user"
ADMIN_USER = "zztest_security_admin_user"
ALL_USERS = [NORMAL_USER, ADMIN_USER]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_PREFIX = "ZZTest Security"

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
        auth._resolve_admin_user_ids = lambda: [ADMIN_USER]
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


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in ALL_USERS:
            connection.execute(text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"), {"id": user_id})


def _make_disposable_analysis(name_suffix: str, submitted_by_user_id: str | None = None) -> int:
    """
    A real, disposable analysis row -- never one of the important dev
    demonstration rows (Linear/Ramp/Retool etc.) reused across every
    prior phase's live walkthroughs. Created fresh per test and deleted
    in _cleanup(), so mutation/deletion tests below can safely exercise
    the real PUT/DELETE code paths without risking real data.

    Portfolio Release Task 3B: submitted_by_user_id defaults to None (a
    historical NULL-owner row -- admin-only/member-only visibility, same
    default as before this task) and is plumbed straight through to
    save_analysis()'s own new parameter for tests that need a specific
    submitter to exercise the new visibility rule end to end.
    """
    from app.ai.sie_v2_methodology import METHODOLOGY_VERSION

    company_name = f"{TEST_PREFIX} {name_suffix}"
    methodology = {
        "startup_intelligence_score": 42.0,
        "context": {"company_stage": "Seed", "industry": "SaaS"},
        "analysis_context": {"methodology_version": METHODOLOGY_VERSION, "evidence_sources": ["company_description"], "analysis_type": "public"},
    }
    analysis_id = save_analysis(
        company_text=f"Disposable test text for {company_name}",
        summary="original summary", risk_analysis="r", competitor_analysis="c", memo="m",
        structured_analysis={"company_name": company_name, "industry": "SaaS", "stage": "Seed", "business_model": "SaaS"},
        investment_score={}, founder_analysis={}, market_analysis={}, sources=[], traction_analysis={},
        market_score=None, team_score=None, product_score=None, competition_score=None,
        traction_score=None, financial_score=None, overall_score=None, recommendation=None,
        readiness_score=None, readiness_summary=None,
        methodology=methodology,
        submitted_by_user_id=submitted_by_user_id,
    )
    get_or_create_startup(company_name)  # keeps startup backfill/canonical tables consistent, unused otherwise
    return analysis_id


def _get_raw_summary(analysis_id: int) -> str | None:
    with engine.begin() as connection:
        return connection.execute(
            text("SELECT summary FROM analyses WHERE id = :id"), {"id": analysis_id}
        ).scalar()


def _analysis_exists(analysis_id: int) -> bool:
    with engine.begin() as connection:
        return connection.execute(
            text("SELECT 1 FROM analyses WHERE id = :id"), {"id": analysis_id}
        ).first() is not None


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM analyses WHERE company_name ILIKE :pattern"), {"pattern": f"{TEST_PREFIX}%"})
        connection.execute(text("DELETE FROM startups WHERE normalized_name LIKE :pattern"), {"pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ALL_USERS})


# --- GET /analyses -----------------------------------------------------------


def test_signed_out_get_analyses_denied() -> None:
    with _patched_auth():
        response = client.get("/analyses")
    expect(response.status_code == 401, f"Expected 401, got {response.status_code}")


def test_normal_user_get_analyses_denied() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.get("/analyses", headers=_auth_headers(NORMAL_USER))
        expect(response.status_code == 403, f"Expected 403, got {response.status_code}")
    finally:
        _cleanup()


def test_admin_get_analyses_allowed() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.get("/analyses", headers=_auth_headers(ADMIN_USER))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(isinstance(response.json(), list), "Expected a list of analyses")
    finally:
        _cleanup()


# --- GET /analyses/{id} -------------------------------------------------------


def test_signed_out_get_analysis_by_id_denied() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("GetByIdSignedOut")
    try:
        with _patched_auth():
            response = client.get(f"/analyses/{analysis_id}")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")
    finally:
        _cleanup()


def test_normal_user_get_analysis_by_id_denied() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("GetByIdNormalUser")
    try:
        with _patched_auth():
            response = client.get(f"/analyses/{analysis_id}", headers=_auth_headers(NORMAL_USER))
        expect(response.status_code == 403, f"Expected 403, got {response.status_code}")
    finally:
        _cleanup()


def test_admin_get_analysis_by_id_allowed() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("GetByIdAdmin")
    try:
        with _patched_auth():
            response = client.get(f"/analyses/{analysis_id}", headers=_auth_headers(ADMIN_USER))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json().get("id") == analysis_id, "Expected the requested analysis back")
    finally:
        _cleanup()


# --- GET /analyses/{id}/pdf ----------------------------------------------------


def test_signed_out_get_analysis_pdf_denied() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("PdfSignedOut")
    try:
        with _patched_auth():
            response = client.get(f"/analyses/{analysis_id}/pdf")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")
    finally:
        _cleanup()


def test_normal_user_get_analysis_pdf_denied() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("PdfNormalUser")
    try:
        with _patched_auth():
            response = client.get(f"/analyses/{analysis_id}/pdf", headers=_auth_headers(NORMAL_USER))
        expect(response.status_code == 403, f"Expected 403, got {response.status_code}")
    finally:
        _cleanup()


def test_admin_get_analysis_pdf_allowed() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("PdfAdmin")
    try:
        with _patched_auth():
            response = client.get(f"/analyses/{analysis_id}/pdf", headers=_auth_headers(ADMIN_USER))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.headers.get("content-type") == "application/pdf", "Expected a PDF response")
    finally:
        _cleanup()


# --- PUT /analyses/{id} -- with mutation-denial proof -------------------------


# A minimal but genuinely-valid body for UpdateAnalysisRequest (which
# wraps a single `methodology: SIEMethodologyAnalysis` field -- see
# test_admin_put_analysis_reaches_handler_not_blocked_by_authorization's
# own docstring below for the full context). Used for every PUT test so
# a 401/403 assertion is never confused with a 422 (body-validation
# failure) -- the body here is deliberately well-formed so the ONLY
# reason a denial could occur is the authorization layer.
_VALID_UPDATE_BODY = {"methodology": {}}


def test_signed_out_put_analysis_denied_and_does_not_mutate() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("PutSignedOut")
    try:
        before = _get_raw_summary(analysis_id)
        with _patched_auth():
            response = client.put(f"/analyses/{analysis_id}", json=_VALID_UPDATE_BODY)
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")
        after = _get_raw_summary(analysis_id)
        expect(before == after, "A denied signed-out PUT must never change the analysis")
    finally:
        _cleanup()


def test_normal_user_put_analysis_denied_and_does_not_mutate() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("PutNormalUser")
    try:
        before = _get_raw_summary(analysis_id)
        with _patched_auth():
            response = client.put(
                f"/analyses/{analysis_id}",
                json=_VALID_UPDATE_BODY,
                headers=_auth_headers(NORMAL_USER),
            )
        expect(response.status_code == 403, f"Expected 403, got {response.status_code}")
        after = _get_raw_summary(analysis_id)
        expect(before == after, "A denied normal-user PUT must never change the analysis")
    finally:
        _cleanup()


def test_admin_put_analysis_reaches_handler_not_blocked_by_authorization() -> None:
    """
    Discovered during Phase 10.1A, out of this phase's narrow scope to
    fix: UpdateAnalysisRequest (app/models/startup.py) was changed at
    some point to wrap a single full `methodology: SIEMethodologyAnalysis`
    field, but update_saved_analysis()'s body still reads the OLD flat
    shape (request.company_text, request.summary, ...) that no longer
    exists on that model -- an AttributeError, unrelated to auth, that
    would fail for ANY caller (admin or not) who reaches this handler.
    This is a pre-existing, separate defect, not something this phase's
    RequireAdmin change introduced or is responsible for fixing (see the
    final report's "Regressions discovered" section).

    FastAPI's TestClient re-raises an unhandled server-side exception in
    the calling test code by default (rather than returning it as a
    normal 500 Response) -- expected and caught here specifically,
    because it is itself proof the request cleared authorization and
    reached the real handler (a 401/403 from RequireAdmin would raise
    HTTPException, which TestClient always turns into a normal Response,
    never a raised AttributeError).

    What this test actually verifies is the property in this phase's
    scope: an admin's request is NOT rejected by the authorization layer
    -- it reaches the real handler and fails there for an unrelated,
    pre-existing reason -- and, critically, that failure happens before
    update_analysis() is ever called, so no partial/corrupt write occurs.
    """
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("PutAdmin")
    try:
        before = _get_raw_summary(analysis_id)
        reached_handler = False

        with _patched_auth():
            try:
                response = client.put(
                    f"/analyses/{analysis_id}",
                    json=_VALID_UPDATE_BODY,
                    headers=_auth_headers(ADMIN_USER),
                )
                expect(
                    response.status_code not in (401, 403),
                    f"Admin must not be blocked by authorization, got {response.status_code}: {response.text}",
                )
                reached_handler = True
            except AttributeError as error:
                expect(
                    "company_text" in str(error),
                    f"Expected the known pre-existing AttributeError (proving the handler was reached), got a different error: {error}",
                )
                reached_handler = True

        expect(reached_handler, "Admin request must reach the real handler, not be silently blocked")
        after = _get_raw_summary(analysis_id)
        expect(before == after, "The pre-existing unrelated bug must fail before any write occurs -- no partial mutation")
    finally:
        _cleanup()


# --- DELETE /analyses/{id} -- with deletion-denial proof ----------------------


def test_signed_out_delete_analysis_denied_and_does_not_delete() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("DeleteSignedOut")
    try:
        with _patched_auth():
            response = client.delete(f"/analyses/{analysis_id}")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")
        expect(_analysis_exists(analysis_id), "A denied signed-out DELETE must never remove the analysis")
    finally:
        _cleanup()


def test_normal_user_delete_analysis_denied_and_does_not_delete() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("DeleteNormalUser")
    try:
        with _patched_auth():
            response = client.delete(f"/analyses/{analysis_id}", headers=_auth_headers(NORMAL_USER))
        expect(response.status_code == 403, f"Expected 403, got {response.status_code}")
        expect(_analysis_exists(analysis_id), "A denied normal-user DELETE must never remove the analysis")
    finally:
        _cleanup()


def test_admin_delete_analysis_allowed() -> None:
    _ensure_test_users()
    analysis_id = _make_disposable_analysis("DeleteAdmin")
    try:
        with _patched_auth():
            response = client.delete(f"/analyses/{analysis_id}", headers=_auth_headers(ADMIN_USER))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(not _analysis_exists(analysis_id), "Expected the admin's DELETE to actually remove the row")
    finally:
        _cleanup()


# --- /analyses/search stays public (regression guard) -------------------------


def test_analyses_search_now_requires_auth() -> None:
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility: /analyses/search
    used to be the one deliberately-public /analyses* route; it now scopes
    results to the caller's own authorized analyses (approved decision),
    so it requires the same auth as /rankings/discover/compare, not the
    RequireAdmin gate the rest of /analyses/* uses.
    """
    with _patched_auth():
        anonymous_response = client.get("/analyses/search", params={"query": "a"})
        expect(
            anonymous_response.status_code == 401,
            f"Expected anonymous /analyses/search to require auth, got {anonymous_response.status_code}",
        )

        authenticated_response = client.get(
            "/analyses/search", params={"query": "a"}, headers=_auth_headers(NORMAL_USER)
        )
        expect(
            authenticated_response.status_code == 200,
            f"Expected an authenticated (non-admin) caller to reach /analyses/search, "
            f"got {authenticated_response.status_code}: {authenticated_response.text}",
        )


# --- /migrate/* routes removed -------------------------------------------------


def test_migrate_routes_no_longer_registered() -> None:
    """
    Behavioral, not just source-string: asks the running FastAPI app
    itself which routes exist, rather than grepping app/api.py's text.
    """
    registered_paths = {route.path for route in api.app.routes}
    for removed_path in (
        "/migrate/add-benchmarking-columns",
        "/migrate/add-company-name-column",
        "/migrate/add-readiness-columns",
    ):
        expect(removed_path not in registered_paths, f"{removed_path} must no longer be a registered route")


def test_migrate_paths_return_404_regardless_of_auth() -> None:
    """
    Belt-and-suspenders over the route-registry check above: an actual
    request to a removed route path returns FastAPI's normal 404 (route
    not found), not a 401/403 (which would suggest the path still exists
    behind an auth gate) and not a 200 (which would mean it's still live).
    """
    for removed_path in (
        "/migrate/add-benchmarking-columns",
        "/migrate/add-company-name-column",
        "/migrate/add-readiness-columns",
    ):
        response = client.post(removed_path)
        expect(response.status_code == 404, f"Expected 404 for removed route {removed_path}, got {response.status_code}")


def test_migration_helper_functions_still_run_at_startup() -> None:
    """
    Confirms Part 3's requirement that removing the HTTP routes did not
    also remove the underlying migration helper functions or their
    startup call sites -- they must still be importable and still be
    called unconditionally when app.api is imported (already proven by
    every other test in this suite successfully importing app.api at
    all, since these calls run at module import time and are idempotent;
    this test asserts the functions themselves are still real, callable
    objects app.api still references).
    """
    from app.database.db import add_benchmarking_columns, add_company_name_column, add_readiness_columns

    expect(callable(add_benchmarking_columns), "add_benchmarking_columns must still exist and be callable")
    expect(callable(add_company_name_column), "add_company_name_column must still exist and be callable")
    expect(callable(add_readiness_columns), "add_readiness_columns must still exist and be callable")

    # Idempotent by construction (see db.py) -- calling them again here is
    # itself proof they still work post-removal-of-the-HTTP-routes, not
    # merely that the names still resolve.
    add_benchmarking_columns()
    add_company_name_column()
    add_readiness_columns()


# --- Public intelligence surfaces remain untouched -----------------------------


# Portfolio Release Task 3B -- Secure Analysis Visibility supersedes every
# "remains public" test below: none of these endpoints are public anymore
# (approved decision -- no public scores-only exception). Each rewritten
# test proves BOTH halves: anonymous access is rejected, and an admin (the
# authorization class this file already has a fixture for) can still
# reach the same data -- complementing test_saved_startups.py's own
# coverage of the SUBMITTER's access to the same routes.


def test_startup_profile_now_requires_auth_admin_can_access() -> None:
    _ensure_test_users()
    _make_disposable_analysis("PublicProfileCheck", submitted_by_user_id=ADMIN_USER)
    try:
        with _patched_auth():
            anonymous_response = client.get(f"/startup/{TEST_PREFIX} PublicProfileCheck")
            expect(
                anonymous_response.status_code == 401,
                f"Expected anonymous Startup Profile access to require auth, got {anonymous_response.status_code}",
            )

            admin_response = client.get(
                f"/startup/{TEST_PREFIX} PublicProfileCheck", headers=_auth_headers(ADMIN_USER)
            )
            expect(admin_response.status_code == 200, f"Expected admin access to succeed, got {admin_response.status_code}")
    finally:
        _cleanup()


def test_rankings_now_requires_auth() -> None:
    with _patched_auth():
        anonymous_response = client.get("/rankings")
        expect(anonymous_response.status_code == 401, f"Expected /rankings to require auth, got {anonymous_response.status_code}")

        authenticated_response = client.get("/rankings", headers=_auth_headers(NORMAL_USER))
        expect(authenticated_response.status_code == 200, f"Expected an authenticated caller to reach /rankings, got {authenticated_response.status_code}")


def test_discovery_now_requires_auth() -> None:
    with _patched_auth():
        anonymous_response = client.get("/discover")
        expect(anonymous_response.status_code == 401, f"Expected /discover to require auth, got {anonymous_response.status_code}")

        authenticated_response = client.get("/discover", headers=_auth_headers(NORMAL_USER))
        expect(authenticated_response.status_code == 200, f"Expected an authenticated caller to reach /discover, got {authenticated_response.status_code}")


def test_compare_now_requires_auth() -> None:
    with _patched_auth():
        anonymous_response = client.get("/compare", params={"startups": "1,2"})
        expect(anonymous_response.status_code == 401, f"Expected /compare to require auth, got {anonymous_response.status_code}")

        authenticated_response = client.get("/compare", params={"startups": "1,2"}, headers=_auth_headers(NORMAL_USER))
        expect(
            authenticated_response.status_code in (200, 400),
            f"Expected an authenticated caller to reach /compare (200 or a clean 400 for unresolvable ids), "
            f"got {authenticated_response.status_code}",
        )


def test_sps_history_now_requires_auth_admin_can_access() -> None:
    _ensure_test_users()
    _make_disposable_analysis("SpsHistoryCheck", submitted_by_user_id=ADMIN_USER)
    try:
        with _patched_auth():
            anonymous_response = client.get(f"/startup/{TEST_PREFIX} SpsHistoryCheck/sps-history")
            expect(
                anonymous_response.status_code == 401,
                f"Expected anonymous SPS history access to require auth, got {anonymous_response.status_code}",
            )

            admin_response = client.get(
                f"/startup/{TEST_PREFIX} SpsHistoryCheck/sps-history", headers=_auth_headers(ADMIN_USER)
            )
            expect(admin_response.status_code == 200, f"Expected admin access to succeed, got {admin_response.status_code}")
    finally:
        _cleanup()


TESTS = [
    test_signed_out_get_analyses_denied,
    test_normal_user_get_analyses_denied,
    test_admin_get_analyses_allowed,
    test_signed_out_get_analysis_by_id_denied,
    test_normal_user_get_analysis_by_id_denied,
    test_admin_get_analysis_by_id_allowed,
    test_signed_out_get_analysis_pdf_denied,
    test_normal_user_get_analysis_pdf_denied,
    test_admin_get_analysis_pdf_allowed,
    test_signed_out_put_analysis_denied_and_does_not_mutate,
    test_normal_user_put_analysis_denied_and_does_not_mutate,
    test_admin_put_analysis_reaches_handler_not_blocked_by_authorization,
    test_signed_out_delete_analysis_denied_and_does_not_delete,
    test_normal_user_delete_analysis_denied_and_does_not_delete,
    test_admin_delete_analysis_allowed,
    test_analyses_search_now_requires_auth,
    test_migrate_routes_no_longer_registered,
    test_migrate_paths_return_404_regardless_of_auth,
    test_migration_helper_functions_still_run_at_startup,
    test_startup_profile_now_requires_auth_admin_can_access,
    test_rankings_now_requires_auth,
    test_discovery_now_requires_auth,
    test_compare_now_requires_auth,
    test_sps_history_now_requires_auth_admin_can_access,
]


def main() -> None:
    print("\nPhase 10.1A -- Critical Security + Runtime Hardening tests")
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
