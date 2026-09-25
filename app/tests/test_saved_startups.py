"""
Regression tests for Saved Startups / Watchlist Phase 1 --
app/database/db.py's save_startup_for_user()/unsave_startup_for_user()/
is_startup_saved_by_user()/get_saved_startups_for_user(), and the four
/me/saved-startups endpoints in app/api.py.

Two layers of coverage:

- DB-layer tests call the four functions directly against the real
  configured DATABASE_URL (same "no separate test database" convention
  as test_startup_write_path.py) -- every row uses a distinctive
  "ZZTest Saved Startups" company-name prefix / zztest_saved_startups_*
  user-id prefix, cleaned up in a finally block even on failure.

- API-layer tests exercise the real FastAPI endpoints through
  TestClient, reusing the exact same local-RSA-keypair JWT-mocking
  harness as test_backend_authentication.py (no live Clerk dependency)
  -- this proves auth/isolation is enforced end-to-end through the real
  routes, not just that the DB functions behave correctly in isolation.

No test here makes an LLM/Tavily call, and none creates a
startup_membership -- saving a startup is a watchlist/bookmark
relationship only.

Run with:
    python -m app.tests.test_saved_startups
"""

import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.ai.sie_v2_methodology import METHODOLOGY_VERSION
from app.database.db import (
    engine,
    get_or_create_startup,
    get_saved_startups_for_user,
    is_startup_saved_by_user,
    save_analysis,
    save_startup_for_user,
    unsave_startup_for_user,
)

TEST_PREFIX = "ZZTest Saved Startups"
USER_A = "zztest_saved_startups_user_a"
USER_B = "zztest_saved_startups_user_b"

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


# --- JWT mocking harness (mirrors test_backend_authentication.py) ---------


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_public_key)


def _make_token(sub: str, exp_delta: int = 3600) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": TEST_ISSUER,
        "azp": TEST_AZP,
        "iat": now,
        "exp": now + exp_delta,
    }
    return pyjwt.encode(payload, _private_key, algorithm="RS256")


class _patched_auth:
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


def _auth_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


# --- Test data helpers ------------------------------------------------------


def _save_test_analysis(
    company_name: str,
    stage: str = "Seed",
    methodology: dict | None = None,
    submitted_by_user_id: str | None = None,
) -> int:
    """Minimal save_analysis() call -- mirrors test_startup_write_path.py's
    own helper, with `stage` added (needed here since
    get_saved_startups_for_user() surfaces it) and `methodology` exposed
    so callers can create a canonical (methodology_version-matching) row
    on demand.

    Portfolio Release Task 3B: submitted_by_user_id defaults to None (a
    "historical NULL-owner" row, same as before this task -- the default
    for tests not specifically about ownership/visibility), and is
    plumbed straight through to save_analysis()'s own new parameter for
    tests that need a specific submitter."""
    return save_analysis(
        company_text=f"Test company text for {company_name}",
        summary="s",
        risk_analysis="r",
        competitor_analysis="c",
        memo="m",
        structured_analysis={
            "company_name": company_name,
            "industry": "SaaS",
            "stage": stage,
            "business_model": "Subscription",
        },
        investment_score={},
        founder_analysis={},
        market_analysis={},
        sources=[],
        traction_analysis={},
        market_score=None,
        team_score=None,
        product_score=None,
        competition_score=None,
        traction_score=None,
        financial_score=None,
        overall_score=None,
        recommendation=None,
        readiness_score=None,
        readiness_summary=None,
        methodology=methodology,
        submitted_by_user_id=submitted_by_user_id,
    )


def _canonical_methodology(sps: float) -> dict:
    return {
        "startup_intelligence_score": sps,
        "analysis_context": {"methodology_version": METHODOLOGY_VERSION},
    }


def _make_canonical_test_startup(
    name_suffix: str, sps: float = 50.0, submitted_by_user_id: str | None = None
) -> tuple[str, int]:
    """Creates one canonical analysis for a fresh ZZTest company and
    returns (company_name, startup_id)."""
    company_name = f"{TEST_PREFIX} {name_suffix}"
    _save_test_analysis(
        company_name, methodology=_canonical_methodology(sps), submitted_by_user_id=submitted_by_user_id
    )
    startup_id = get_or_create_startup(company_name)
    return company_name, startup_id


def _ensure_test_users() -> None:
    # save_startup_for_user()/unsave_startup_for_user() operate on
    # saved_startups, whose user_id column has a real FK to users(id) --
    # DB-layer tests call these directly (bypassing app/auth.py's own
    # get_or_create_user() lazy sync), so they need a users row to exist
    # first. API-layer tests don't need this -- RequireAuth creates it.
    with engine.begin() as connection:
        for user_id in (USER_A, USER_B):
            connection.execute(
                text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
                {"id": user_id},
            )


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM saved_startups WHERE user_id = ANY(:ids)"),
            {"ids": [USER_A, USER_B]},
        )
        connection.execute(
            text("""
                DELETE FROM analyses
                WHERE startup_id IN (
                    SELECT id FROM startups WHERE normalized_name LIKE :pattern
                )
            """),
            {"pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("DELETE FROM startups WHERE normalized_name LIKE :pattern"),
            {"pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("DELETE FROM users WHERE id = ANY(:ids)"),
            {"ids": [USER_A, USER_B]},
        )


# --- 1-6: core save/unsave/list behavior (DB layer) ------------------------


def test_authenticated_user_can_save_a_valid_startup() -> None:
    _ensure_test_users()
    try:
        _, startup_id = _make_canonical_test_startup("Save Basic")

        created = save_startup_for_user(USER_A, startup_id)

        expect(created is True, "Expected save_startup_for_user to report a new row created")
        expect(
            is_startup_saved_by_user(USER_A, startup_id),
            "Expected the startup to be saved for USER_A",
        )
    finally:
        _cleanup()


def test_saved_row_has_correct_user_and_startup_id() -> None:
    _ensure_test_users()
    try:
        _, startup_id = _make_canonical_test_startup("Row Shape")
        save_startup_for_user(USER_A, startup_id)

        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT user_id, startup_id FROM saved_startups WHERE user_id = :u"),
                {"u": USER_A},
            ).mappings().first()

        expect(row is not None, "Expected exactly one saved_startups row")
        expect(row["user_id"] == USER_A, f"Wrong user_id: {row['user_id']!r}")
        expect(row["startup_id"] == startup_id, f"Wrong startup_id: {row['startup_id']!r}")
    finally:
        _cleanup()


def test_saving_twice_creates_exactly_one_row() -> None:
    _ensure_test_users()
    try:
        _, startup_id = _make_canonical_test_startup("Idempotent Save")

        first = save_startup_for_user(USER_A, startup_id)
        second = save_startup_for_user(USER_A, startup_id)

        expect(first is True, "Expected the first save to create a row")
        expect(second is False, "Expected the second (duplicate) save to be a no-op")

        with engine.begin() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM saved_startups WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).scalar()

        expect(count == 1, f"Expected exactly one row after saving twice, got {count}")
    finally:
        _cleanup()


def test_authenticated_user_can_unsave() -> None:
    _ensure_test_users()
    try:
        _, startup_id = _make_canonical_test_startup("Unsave Basic")
        save_startup_for_user(USER_A, startup_id)

        removed = unsave_startup_for_user(USER_A, startup_id)

        expect(removed is True, "Expected unsave to report a row removed")
        expect(
            not is_startup_saved_by_user(USER_A, startup_id),
            "Expected the startup to no longer be saved",
        )
    finally:
        _cleanup()


def test_unsaving_twice_is_safe() -> None:
    _ensure_test_users()
    try:
        _, startup_id = _make_canonical_test_startup("Idempotent Unsave")
        save_startup_for_user(USER_A, startup_id)

        first = unsave_startup_for_user(USER_A, startup_id)
        second = unsave_startup_for_user(USER_A, startup_id)

        expect(first is True, "Expected the first unsave to remove a row")
        expect(second is False, "Expected the second (redundant) unsave to be a safe no-op")
    finally:
        _cleanup()


def test_user_can_list_their_saved_startups() -> None:
    """
    Portfolio Release Task 3B: the analysis is attributed to USER_A
    (submitted_by_user_id=USER_A) -- representing "I analyzed my own
    company, then saved it too" -- so USER_A is authorized to see its
    score via the visibility rule, same as before this task's fix. See
    test_saving_a_startup_does_not_grant_access_to_another_users_private_analysis
    below for the complementary case: saving alone, with no other
    relationship to the analysis, does NOT grant this.
    """
    _ensure_test_users()
    try:
        company_name, startup_id = _make_canonical_test_startup(
            "List Basic", sps=61.5, submitted_by_user_id=USER_A
        )
        save_startup_for_user(USER_A, startup_id)

        entries = get_saved_startups_for_user(USER_A)
        matching = [e for e in entries if e["startup_id"] == startup_id]

        expect(len(matching) == 1, "Expected the saved startup to appear exactly once in the list")
        expect(matching[0]["company_name"] == company_name, "Wrong company_name in list entry")
        expect(matching[0]["overall_score"] == 61.5, f"Wrong overall_score: {matching[0]['overall_score']!r}")
    finally:
        _cleanup()


def test_saving_a_startup_does_not_grant_access_to_another_users_private_analysis() -> None:
    """
    Portfolio Release Task 3B, approved decision item 5: saving/bookmarking
    a startup must NOT grant report access. USER_B saves a startup that
    only USER_A (the submitter, with no relationship to USER_B) has
    analyzed -- USER_B's list must still show the bookmark (it's their
    own, real saved_startups row) but with null intelligence fields, never
    USER_A's private score/industry/stage.
    """
    _ensure_test_users()
    try:
        _, startup_id = _make_canonical_test_startup(
            "Bookmark Not Access", sps=88.0, submitted_by_user_id=USER_A
        )
        save_startup_for_user(USER_B, startup_id)

        entries = get_saved_startups_for_user(USER_B)
        matching = [e for e in entries if e["startup_id"] == startup_id]

        expect(len(matching) == 1, "Expected USER_B's own bookmark to still appear in their list")
        expect(
            matching[0]["overall_score"] is None,
            f"Expected no visible score for an analysis USER_B is not authorized to see, "
            f"got {matching[0]['overall_score']!r}",
        )
        expect(
            matching[0]["industry"] is None and matching[0]["stage"] is None,
            f"Expected no visible industry/stage either, got {matching[0]!r}",
        )
    finally:
        _cleanup()


# --- 7-8: cross-user isolation (DB layer + API layer) -----------------------


def test_user_a_list_never_includes_user_b_saved_startup() -> None:
    _ensure_test_users()
    try:
        _, startup_id = _make_canonical_test_startup("Isolation List")
        save_startup_for_user(USER_B, startup_id)

        entries_a = get_saved_startups_for_user(USER_A)
        matching = [e for e in entries_a if e["startup_id"] == startup_id]

        expect(len(matching) == 0, "USER_A's list must never include USER_B's saved startup")
    finally:
        _cleanup()


def test_user_a_cannot_remove_user_b_saved_startup() -> None:
    _ensure_test_users()
    try:
        _, startup_id = _make_canonical_test_startup("Isolation Remove")
        save_startup_for_user(USER_B, startup_id)

        # USER_A "unsaves" a startup USER_A never saved -- scoped by
        # user_id, so this can only ever affect USER_A's own (nonexistent)
        # row, never USER_B's.
        removed = unsave_startup_for_user(USER_A, startup_id)

        expect(removed is False, "USER_A's unsave should be a no-op (nothing of USER_A's to remove)")
        expect(
            is_startup_saved_by_user(USER_B, startup_id),
            "USER_B's saved startup must still be saved after USER_A's unsave call",
        )
    finally:
        _cleanup()


def test_api_cross_user_isolation_end_to_end() -> None:
    """Same guarantee as the two tests above, proven through the real
    HTTP routes with real (locally-signed) tokens -- there is no
    /users/{user_id}/saved-startups route, so user_id is derived only
    from each request's own verified token. This is what makes reading/
    saving/removing another user's list structurally impossible, not
    just a policy this test happens to also check at the DB layer."""
    _ensure_test_users()
    try:
        with _patched_auth():
            _, startup_id = _make_canonical_test_startup("API Isolation")

            save_response = client.post(
                f"/me/saved-startups/{startup_id}", headers=_auth_headers(USER_A)
            )
            expect(save_response.status_code == 200, f"USER_A save failed: {save_response.text}")

            # USER_B's own list must not include it.
            list_response_b = client.get("/me/saved-startups", headers=_auth_headers(USER_B))
            expect(list_response_b.status_code == 200, f"USER_B list failed: {list_response_b.text}")
            ids_b = [entry["startup_id"] for entry in list_response_b.json()]
            expect(startup_id not in ids_b, "USER_B's list must not include USER_A's saved startup")

            # USER_B's status check for that startup must be False.
            status_response_b = client.get(
                f"/me/saved-startups/{startup_id}", headers=_auth_headers(USER_B)
            )
            expect(status_response_b.json()["saved"] is False, "USER_B must not see it as saved")

            # USER_B "removing" it must not affect USER_A's saved copy.
            unsave_response_b = client.delete(
                f"/me/saved-startups/{startup_id}", headers=_auth_headers(USER_B)
            )
            expect(unsave_response_b.status_code == 200, f"USER_B unsave call failed: {unsave_response_b.text}")

            status_response_a = client.get(
                f"/me/saved-startups/{startup_id}", headers=_auth_headers(USER_A)
            )
            expect(
                status_response_a.json()["saved"] is True,
                "USER_A's saved startup must survive USER_B's unrelated unsave call",
            )
    finally:
        _cleanup()


# --- 9: invalid startup id fails cleanly ------------------------------------


def test_invalid_startup_id_fails_cleanly_db_layer() -> None:
    _ensure_test_users()
    try:
        raised = False
        try:
            save_startup_for_user(USER_A, 999_999_999)
        except ValueError:
            raised = True

        expect(raised, "Expected save_startup_for_user to raise ValueError for a nonexistent startup_id")
    finally:
        _cleanup()


def test_invalid_startup_id_fails_cleanly_api_layer() -> None:
    with _patched_auth():
        response = client.post("/me/saved-startups/999999999", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404 for a nonexistent startup_id, got {response.status_code}")


# --- 10-12: unauthenticated requests fail 401 -------------------------------


def test_unauthenticated_save_fails_401() -> None:
    with _patched_auth():
        response = client.post("/me/saved-startups/1")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")


def test_unauthenticated_unsave_fails_401() -> None:
    with _patched_auth():
        response = client.delete("/me/saved-startups/1")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")


def test_unauthenticated_list_fails_401() -> None:
    with _patched_auth():
        response = client.get("/me/saved-startups")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")


# --- 13: authentication/saving never creates startup_memberships -----------


def test_saving_creates_zero_startup_memberships() -> None:
    _ensure_test_users()
    try:
        with engine.begin() as connection:
            before = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()

        with _patched_auth():
            _, startup_id = _make_canonical_test_startup("No Membership")
            response = client.post(f"/me/saved-startups/{startup_id}", headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Save failed: {response.text}")

        with engine.begin() as connection:
            after = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()

        expect(
            after == before,
            f"startup_memberships changed ({before} -> {after}): saving must never create ownership",
        )
    finally:
        _cleanup()


# --- 14: no intelligence duplicated into saved_startups ---------------------


def test_saved_startups_table_stores_no_intelligence_fields() -> None:
    """saved_startups must remain a pure relationship table -- this
    inspects the ACTUAL columns on a real row, not just the response
    shape, so a future change that adds e.g. a cached `company_name` or
    `overall_score` column directly to saved_startups would fail this
    test even if get_saved_startups_for_user() still worked correctly."""
    _ensure_test_users()
    try:
        _, startup_id = _make_canonical_test_startup("No Duplication", sps=77.0)
        save_startup_for_user(USER_A, startup_id)

        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT * FROM saved_startups WHERE user_id = :u"),
                {"u": USER_A},
            ).mappings().first()

        expect(row is not None, "Expected a saved_startups row")

        allowed_columns = {"id", "user_id", "startup_id", "created_at"}
        actual_columns = set(row.keys())

        expect(
            actual_columns == allowed_columns,
            f"saved_startups has unexpected columns: {actual_columns - allowed_columns} "
            "-- it must remain a pure relationship table with no copied intelligence",
        )
    finally:
        _cleanup()


# --- 15: latest canonical intelligence, not a snapshot (Part 9) ------------


def test_saved_startup_resolves_latest_canonical_analysis_after_newer_one() -> None:
    """Critical Part 9 behavior: a saved startup points at startups.id,
    never at a specific analysis_id -- so when a NEWER canonical analysis
    is created for the same startup after it was saved, the watchlist
    must immediately reflect the new intelligence, not the score that was
    current at save time.

    Portfolio Release Task 3B: both analyses are attributed to USER_A (the
    same user doing the listing) so this test continues to verify "latest
    wins," unaffected by the new visibility rule -- see
    test_saving_a_startup_does_not_grant_access_to_another_users_private_analysis
    for the visibility rule's own dedicated coverage.
    """
    _ensure_test_users()
    try:
        company_name, startup_id = _make_canonical_test_startup(
            "Latest Wins", sps=40.0, submitted_by_user_id=USER_A
        )
        save_startup_for_user(USER_A, startup_id)

        entries = get_saved_startups_for_user(USER_A)
        before = next(e for e in entries if e["startup_id"] == startup_id)
        expect(before["overall_score"] == 40.0, f"Expected initial SPS 40.0, got {before['overall_score']!r}")

        # A newer canonical analysis for the SAME company_name resolves to
        # the SAME startup_id (get_or_create_startup()'s own dedup rule) --
        # never a second, competing startups row.
        _save_test_analysis(company_name, methodology=_canonical_methodology(95.0), submitted_by_user_id=USER_A)
        new_startup_id = get_or_create_startup(company_name)
        expect(new_startup_id == startup_id, "A repeat analysis must resolve to the SAME startup_id")

        entries_after = get_saved_startups_for_user(USER_A)
        after = next(e for e in entries_after if e["startup_id"] == startup_id)

        expect(
            after["overall_score"] == 95.0,
            f"Expected the watchlist to reflect the NEW SPS (95.0), got {after['overall_score']!r} "
            "-- saved_startups must never pin a stale snapshot",
        )

        # Still exactly one saved_startups row -- the newer analysis must
        # not have created a second bookmark.
        with engine.begin() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM saved_startups WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            ).scalar()
        expect(count == 1, f"Expected exactly one saved_startups row, got {count}")
    finally:
        _cleanup()


# --- 16-17: public routes remain public -------------------------------------


def test_startup_profile_requires_auth_and_owner_can_access_their_own() -> None:
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility supersedes the
    old "public startup profile" behavior this test used to assert. Now:
    anonymous access is rejected (401), and the analysis's own submitter
    (a real, verified caller) can still reach their own report -- proving
    the fix doesn't just lock everyone out, it correctly recognizes an
    authorized owner end to end through the real route.
    """
    _ensure_test_users()
    company_name, _ = _make_canonical_test_startup("Public Profile", submitted_by_user_id=USER_A)
    try:
        anonymous_response = client.get(f"/startup/{company_name}")
        expect(
            anonymous_response.status_code == 401,
            f"Expected anonymous access to require auth (401), got {anonymous_response.status_code}",
        )

        with _patched_auth():
            owner_response = client.get(f"/startup/{company_name}", headers=_auth_headers(USER_A))
            expect(
                owner_response.status_code == 200,
                f"Expected the submitter to reach their own report, got {owner_response.status_code}: {owner_response.text}",
            )
    finally:
        _cleanup()


def test_rankings_search_dashboard_now_require_auth() -> None:
    """
    Portfolio Release Task 3B: these endpoints now return per-user-
    authorized analysis content (approved decision -- no public
    scores-only exception), so an anonymous caller must be rejected. See
    test_backend_authentication.py's own
    test_analysis_content_endpoints_require_auth for the fuller list.
    """
    checks = [
        ("GET", "/rankings", {}),
        ("GET", "/analytics", {}),
        ("GET", "/analyses/search", {"query": "a"}),
    ]

    for method, path, params in checks:
        response = client.request(method, path, params=params)
        expect(
            response.status_code == 401,
            f"Expected {path} to require auth (401), got {response.status_code}",
        )


TESTS = [
    test_authenticated_user_can_save_a_valid_startup,
    test_saved_row_has_correct_user_and_startup_id,
    test_saving_twice_creates_exactly_one_row,
    test_authenticated_user_can_unsave,
    test_unsaving_twice_is_safe,
    test_user_can_list_their_saved_startups,
    test_saving_a_startup_does_not_grant_access_to_another_users_private_analysis,
    test_user_a_list_never_includes_user_b_saved_startup,
    test_user_a_cannot_remove_user_b_saved_startup,
    test_api_cross_user_isolation_end_to_end,
    test_invalid_startup_id_fails_cleanly_db_layer,
    test_invalid_startup_id_fails_cleanly_api_layer,
    test_unauthenticated_save_fails_401,
    test_unauthenticated_unsave_fails_401,
    test_unauthenticated_list_fails_401,
    test_saving_creates_zero_startup_memberships,
    test_saved_startups_table_stores_no_intelligence_fields,
    test_saved_startup_resolves_latest_canonical_analysis_after_newer_one,
    test_startup_profile_requires_auth_and_owner_can_access_their_own,
    test_rankings_search_dashboard_now_require_auth,
]


def main() -> None:
    print("\nSaved Startups / Watchlist Phase 1 tests")
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
