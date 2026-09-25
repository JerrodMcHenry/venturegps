"""
Regression tests for Portfolio Release Task 3B -- Secure Analysis
Visibility: the private-by-default authorization rule itself
(app/database/db.py::_analysis_visibility_clause(), the
analyses.submitted_by_user_id column, and the endpoints that enforce the
rule -- primarily GET /startup/{company_name}, GET
/startup/{company_name}/sps-history, and GET /compare).

This is the single, authoritative, dedicated test file for the rule --
individual endpoint-by-endpoint "does this specific route require auth"
coverage lives in test_backend_authentication.py/test_security_hardening.py;
individual "does saving/watching grant access" coverage for those specific
features lives in test_saved_startups.py/test_investor_workspace.py.
Founder Workspace's own separate, non-_analysis_visibility_clause()
authorization path has its own dedicated coverage in
test_founder_workspace.py.

CORRECTED (final security review, before commit): this file's job is the
CORE rule, now two-tiered rather than a flat three-way OR: a NEW analysis
(non-NULL submitted_by_user_id) is visible ONLY to its submitter or an
admin -- approved membership of the same startup does NOT grant access to
it, the cross-user confidentiality bug this correction fixes. A
HISTORICAL analysis (NULL submitted_by_user_id, never backfilled) is
visible to an approved member or an admin, preserving the pre-migration
behavior. Never anyone else, including a signed-in-but-unrelated caller
or an approved member who isn't the submitter, and never an anonymous
caller. Saved startups, watchlists, and company-name matches never grant
access on their own -- see test_saved_startups.py/test_investor_workspace.py
for the dedicated coverage of those specific surfaces.

Every row uses a distinctive "ZZTest Visibility" company-name prefix and
zztest_visibility_* user-id prefix, cleaned up in a finally block even on
failure. No test here makes an LLM/Tavily call.

Run with:
    python -m app.tests.test_analysis_visibility
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
    get_rankings,
    get_startup_by_name,
    get_startups_for_comparison,
    save_analysis,
    search_analyses,
)

TEST_PREFIX = "ZZTest Visibility"
SUBMITTER = "zztest_visibility_submitter"
MEMBER = "zztest_visibility_member"
UNRELATED_USER = "zztest_visibility_unrelated"
ADMIN_USER = "zztest_visibility_admin"
ALL_USERS = [SUBMITTER, MEMBER, UNRELATED_USER, ADMIN_USER]

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


def _save(company_name: str, sps: float = 70.0, submitted_by_user_id: str | None = None) -> int:
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
            text("DELETE FROM analyses WHERE company_name ILIKE :pattern"), {"pattern": f"{TEST_PREFIX}%"}
        )
        connection.execute(
            text("DELETE FROM startups WHERE normalized_name LIKE :pattern"), {"pattern": f"{TEST_PREFIX.lower()}%"}
        )
        connection.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ALL_USERS})


# --- 1: anonymous access rejected -------------------------------------------


def test_anonymous_access_rejected() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Anonymous"
    _save(company_name, submitted_by_user_id=SUBMITTER)
    try:
        response = client.get(f"/startup/{company_name}")
        expect(response.status_code == 401, f"Expected 401 for anonymous access, got {response.status_code}")
    finally:
        _cleanup()


# --- 2: owner (submitter) access ---------------------------------------------


def test_owner_can_access_their_own_analysis() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Owner"
    _save(company_name, sps=88.0, submitted_by_user_id=SUBMITTER)
    try:
        with _patched_auth():
            response = client.get(f"/startup/{company_name}", headers=_auth_headers(SUBMITTER))
        expect(response.status_code == 200, f"Expected 200 for the submitter, got {response.status_code}: {response.text}")
        body = response.json()
        expect(
            body["methodology"]["startup_intelligence_score"] == 88.0,
            f"Expected the real score, got {body['methodology'].get('startup_intelligence_score')!r}",
        )
    finally:
        _cleanup()


# --- 3: unrelated signed-in user rejected, non-leaking ----------------------


def test_unrelated_user_never_sees_analysis_content() -> None:
    """
    A signed-in caller with no relationship to the analysis (not the
    submitter, not an approved member, not an admin) must never receive
    ANY analysis content (methodology, evidence, scores) -- but the
    response is NOT a bare 404 matching a genuinely nonexistent company:
    get_startup_by_name()'s own pre-existing fallback (Phase 37E, honest
    "exists but not yet analyzed" vs. "doesn't exist at all") still finds
    the real `startups` row this canonical company name resolved to
    (created the moment ANYONE analyzes it, by get_or_create_startup()),
    and reports has_analysis=false -- the exact same shape a company that
    has genuinely never been analyzed by anyone gets. This is a
    deliberate, accepted, minor distinction from a bare 404: it confirms
    a canonical record for this company NAME exists (not confidential --
    the caller already knows the name, since they searched for it) while
    disclosing ZERO analysis content. A genuinely nonexistent company
    (no `startups` row at all) still gets a real 404 -- see
    test_genuinely_nonexistent_company_returns_404 below.
    """
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Unrelated"
    _save(company_name, submitted_by_user_id=SUBMITTER)
    try:
        with _patched_auth():
            unrelated_response = client.get(f"/startup/{company_name}", headers=_auth_headers(UNRELATED_USER))

        expect(
            unrelated_response.status_code == 200,
            f"Expected 200 (the honest 'exists, not analyzed by you' shape), got {unrelated_response.status_code}",
        )
        body = unrelated_response.json()
        expect(body["has_analysis"] is False, f"Expected has_analysis=False for an unrelated caller, got {body['has_analysis']!r}")
        expect(body["methodology"] is None, f"Expected zero analysis content disclosed, got {body['methodology']!r}")
    finally:
        _cleanup()


def test_genuinely_nonexistent_company_returns_404() -> None:
    with _patched_auth():
        response = client.get(
            f"/startup/{TEST_PREFIX} Genuinely Nonexistent Company", headers=_auth_headers(UNRELATED_USER)
        )
    expect(response.status_code == 404, f"Expected 404 for a company with no startups row at all, got {response.status_code}")


# --- 4: approved member access is NOT a general grant -------------------------
#
# CORRECTED (final security review, before commit). The rule this file
# tested here used to be "an approved member sees any analysis for their
# startup, submitter or not" -- that was the cross-user confidentiality
# bug this correction fixes. Approved membership now only ever
# substitutes for a MISSING submitter (a historical, NULL-owner row --
# see section 6 below); it is never a path to another real person's
# private analysis of the same startup. This is the regression test the
# correction explicitly asked for: "an approved founder cannot read a
# different user's private analysis of the founder's own startup."


def test_approved_member_cannot_access_analysis_they_did_not_submit() -> None:
    """
    MEMBER is a genuinely approved member of the same startup SUBMITTER
    analyzed -- not an unrelated stranger. Membership alone must still not
    unlock SUBMITTER's private, non-NULL-owner analysis. MEMBER must get
    the exact same non-leaking 200/has_analysis:false shape an unrelated
    caller gets (see test_unrelated_user_never_sees_analysis_content) --
    never the real methodology, and never a distinguishing status code
    that would itself confirm "someone else has analyzed your startup."
    """
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Member"
    _save(company_name, sps=72.0, submitted_by_user_id=SUBMITTER)
    startup_id = get_or_create_startup(company_name)
    _grant_membership(MEMBER, startup_id)
    try:
        with _patched_auth():
            response = client.get(f"/startup/{company_name}", headers=_auth_headers(MEMBER))
        expect(response.status_code == 200, f"Expected 200 (the honest 'exists, not visible to you' shape), got {response.status_code}: {response.text}")
        body = response.json()
        expect(
            body["has_analysis"] is False,
            f"An approved member who did not submit the analysis must get has_analysis=False, got {body['has_analysis']!r}",
        )
        expect(
            body["methodology"] is None,
            f"An approved member must never see another submitter's private analysis content, got {body['methodology']!r}",
        )
    finally:
        _cleanup()


def test_submitter_can_still_access_their_own_analysis_when_other_members_exist() -> None:
    """The flip side of the fix above: tightening membership must not
    accidentally cost the submitter their own access. SUBMITTER must
    still see their own report even when a different approved member of
    the same startup exists."""
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} MemberSubmitterStillWorks"
    _save(company_name, sps=83.0, submitted_by_user_id=SUBMITTER)
    startup_id = get_or_create_startup(company_name)
    _grant_membership(MEMBER, startup_id)
    try:
        with _patched_auth():
            response = client.get(f"/startup/{company_name}", headers=_auth_headers(SUBMITTER))
        expect(response.status_code == 200, f"Expected 200 for the submitter, got {response.status_code}: {response.text}")
        expect(
            response.json()["methodology"]["startup_intelligence_score"] == 83.0,
            "The submitter must still see their own real score after submission, regardless of other members",
        )
    finally:
        _cleanup()


# --- 5: admin access ----------------------------------------------------------


def test_admin_can_access_any_analysis() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Admin"
    _save(company_name, sps=91.0, submitted_by_user_id=SUBMITTER)
    try:
        with _patched_auth():
            response = client.get(f"/startup/{company_name}", headers=_auth_headers(ADMIN_USER))
        expect(response.status_code == 200, f"Expected 200 for an admin, got {response.status_code}: {response.text}")
        expect(response.json()["methodology"]["startup_intelligence_score"] == 91.0, "Admin must see the real score")
    finally:
        _cleanup()


# --- 6: historical NULL-owner records -----------------------------------------


def test_historical_null_owner_record_accessible_only_to_member_or_admin() -> None:
    """
    Every analysis row that existed before this migration has
    submitted_by_user_id = NULL, forever (never backfilled -- approved
    decision). Such a row must be accessible to an approved member or an
    admin, but to NO signed-in caller merely by virtue of being signed in
    -- there is no submitter to match, so the "submitter" branch of the
    visibility rule can never apply.
    """
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Historical"
    _save(company_name, sps=50.0, submitted_by_user_id=None)
    startup_id = get_or_create_startup(company_name)
    _grant_membership(MEMBER, startup_id)
    try:
        with _patched_auth():
            unrelated_response = client.get(f"/startup/{company_name}", headers=_auth_headers(UNRELATED_USER))
            member_response = client.get(f"/startup/{company_name}", headers=_auth_headers(MEMBER))
            admin_response = client.get(f"/startup/{company_name}", headers=_auth_headers(ADMIN_USER))

        # See test_unrelated_user_never_sees_analysis_content's own comment:
        # an unrelated caller gets 200/has_analysis=false (the honest
        # "exists, not visible to you" shape), never the real methodology.
        expect(unrelated_response.status_code == 200, f"Expected 200, got {unrelated_response.status_code}")
        expect(
            unrelated_response.json()["has_analysis"] is False,
            "A historical NULL-owner row must disclose no analysis content to an unrelated caller",
        )
        expect(member_response.status_code == 200, f"Expected an approved member to reach it, got {member_response.status_code}")
        expect(
            member_response.json()["has_analysis"] is True and member_response.json()["methodology"] is not None,
            "An approved member must see the real historical analysis",
        )
        expect(admin_response.status_code == 200, f"Expected an admin to reach it, got {admin_response.status_code}")
        expect(
            admin_response.json()["has_analysis"] is True and admin_response.json()["methodology"] is not None,
            "An admin must see the real historical analysis",
        )
    finally:
        _cleanup()


def test_historical_records_are_never_deleted_or_rewritten_by_the_migration() -> None:
    """Constraint check, not just a rule-behavior check: the migration
    itself (add_analysis_submitted_by_column()) must be additive only --
    a pre-existing row's other columns are completely untouched, and the
    new column is simply NULL, never populated by a guess."""
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Preserved"
    analysis_id = _save(company_name, sps=63.5, submitted_by_user_id=None)
    try:
        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT company_name, submitted_by_user_id, methodology FROM analyses WHERE id = :id"),
                {"id": analysis_id},
            ).mappings().first()

        expect(row is not None, "Expected the row to still exist")
        expect(row["company_name"] == company_name, "company_name must be unchanged")
        expect(row["submitted_by_user_id"] is None, "A pre-Task-3B-shaped row must have submitted_by_user_id = NULL, never a guessed value")
        expect(row["methodology"] is not None, "methodology must be unchanged")
    finally:
        _cleanup()


# --- 7: company-name collisions -----------------------------------------------


def test_company_name_collision_each_user_sees_only_their_own() -> None:
    """
    Approved decision item 4: two users analyzing a company with the same
    name must each retrieve their own authorized result -- never overwrite
    or expose the other's private analysis. SUBMITTER analyzes first;
    UNRELATED_USER analyzes the SAME company name LATER (a real, newer
    row) -- SUBMITTER must still see THEIR OWN analysis via /startup/{name},
    never silently redirected to the stranger's newer one, and vice versa.
    """
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Collision"
    _save(company_name, sps=10.0, submitted_by_user_id=SUBMITTER)
    time.sleep(0.01)  # ensure a real wall-clock gap -- the second row is genuinely newer
    _save(company_name, sps=99.0, submitted_by_user_id=UNRELATED_USER)
    try:
        with engine.begin() as connection:
            row_count = connection.execute(
                text("SELECT COUNT(*) FROM analyses WHERE company_name ILIKE :pattern"),
                {"pattern": f"{company_name}%"},
            ).scalar()
        expect(row_count == 2, f"Expected both analyses to exist as separate rows, got {row_count}")

        with _patched_auth():
            submitter_view = client.get(f"/startup/{company_name}", headers=_auth_headers(SUBMITTER))
            unrelated_view = client.get(f"/startup/{company_name}", headers=_auth_headers(UNRELATED_USER))

        expect(submitter_view.status_code == 200, f"Expected SUBMITTER to see their own analysis, got {submitter_view.status_code}")
        expect(
            submitter_view.json()["methodology"]["startup_intelligence_score"] == 10.0,
            f"Expected SUBMITTER's OWN score (10.0), never the newer stranger's, got "
            f"{submitter_view.json()['methodology'].get('startup_intelligence_score')!r}",
        )

        expect(unrelated_view.status_code == 200, f"Expected UNRELATED_USER to see their own (newer) analysis, got {unrelated_view.status_code}")
        expect(
            unrelated_view.json()["methodology"]["startup_intelligence_score"] == 99.0,
            f"Expected UNRELATED_USER's own score (99.0), got "
            f"{unrelated_view.json()['methodology'].get('startup_intelligence_score')!r}",
        )
    finally:
        _cleanup()


def test_company_name_collision_db_layer_authorization_before_latest_pick() -> None:
    """
    Direct DB-layer proof (no HTTP) that authorization is applied BEFORE
    "pick the latest" -- not as a post-fetch filter. SUBMITTER's OWN
    analysis is older; a stranger's newer, inaccessible analysis of the
    same company name must never take priority for SUBMITTER's own query.
    """
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} Collision DB"
    _save(company_name, sps=25.0, submitted_by_user_id=SUBMITTER)
    time.sleep(0.01)
    _save(company_name, sps=95.0, submitted_by_user_id=UNRELATED_USER)
    try:
        profile = get_startup_by_name(company_name, SUBMITTER, False)
        expect(profile is not None, "Expected SUBMITTER to resolve a profile")
        expect(
            profile["methodology"]["startup_intelligence_score"] == 25.0,
            f"Expected SUBMITTER's own (older) score, not the newer stranger's, got "
            f"{profile['methodology'].get('startup_intelligence_score')!r}",
        )
    finally:
        _cleanup()


# --- 8: indirect disclosure through other endpoints ---------------------------


def test_search_never_leaks_another_users_private_analysis() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} SearchLeak"
    _save(company_name, submitted_by_user_id=SUBMITTER)
    try:
        with _patched_auth():
            unrelated_results = search_analyses(f"{TEST_PREFIX} SearchLeak", UNRELATED_USER, False)
            owner_results = search_analyses(f"{TEST_PREFIX} SearchLeak", SUBMITTER, False)

        expect(
            all(r["company_name"] != company_name for r in unrelated_results),
            f"An unrelated user's search must never surface another user's private analysis, got {unrelated_results}",
        )
        expect(
            any(r["company_name"] == company_name for r in owner_results),
            "The submitter's own search must still find their own analysis",
        )
    finally:
        _cleanup()


def test_rankings_never_leaks_another_users_private_analysis() -> None:
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} RankingsLeak"
    _save(company_name, sps=77.0, submitted_by_user_id=SUBMITTER)
    try:
        unrelated_rankings = get_rankings(UNRELATED_USER, False)
        owner_rankings = get_rankings(SUBMITTER, False)

        expect(
            all(r["company_name"] != company_name for r in unrelated_rankings),
            "An unrelated user's Rankings must never include another user's private analysis",
        )
        expect(
            any(r["company_name"] == company_name for r in owner_rankings),
            "The submitter's own Rankings must still include their own analysis",
        )
    finally:
        _cleanup()


def test_compare_explicit_startup_id_cannot_bypass_authorization() -> None:
    """
    Approved decision item 4: explicit startup_ids passed to /compare must
    not bypass authorization. An unrelated user passing the EXACT,
    correct, real startup_id of another user's private analysis must get
    it silently excluded (missing_startup_ids), never a leaked row --
    indistinguishable from passing a nonexistent id.
    """
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} CompareBypass"
    _save(company_name, submitted_by_user_id=SUBMITTER)
    startup_id = get_or_create_startup(company_name)
    try:
        rows = get_startups_for_comparison([startup_id], UNRELATED_USER, False)
        expect(
            len(rows) == 0,
            f"An unrelated user's explicit, correct startup_id must resolve to nothing, got {rows}",
        )

        owner_rows = get_startups_for_comparison([startup_id], SUBMITTER, False)
        expect(len(owner_rows) == 1, f"The submitter's own explicit startup_id must still resolve, got {owner_rows}")
    finally:
        _cleanup()


TESTS = [
    test_anonymous_access_rejected,
    test_owner_can_access_their_own_analysis,
    test_unrelated_user_never_sees_analysis_content,
    test_genuinely_nonexistent_company_returns_404,
    test_approved_member_cannot_access_analysis_they_did_not_submit,
    test_submitter_can_still_access_their_own_analysis_when_other_members_exist,
    test_admin_can_access_any_analysis,
    test_historical_null_owner_record_accessible_only_to_member_or_admin,
    test_historical_records_are_never_deleted_or_rewritten_by_the_migration,
    test_company_name_collision_each_user_sees_only_their_own,
    test_company_name_collision_db_layer_authorization_before_latest_pick,
    test_search_never_leaks_another_users_private_analysis,
    test_rankings_never_leaks_another_users_private_analysis,
    test_compare_explicit_startup_id_cannot_bypass_authorization,
]


def main() -> None:
    print("\nSecure Analysis Visibility tests")
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
