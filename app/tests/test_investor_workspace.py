"""
Regression tests for Phase 9 -- Investor Workspace V1:
app/ai/investor_workspace.py's deterministic change-detection logic, and
the GET /investor/workspace endpoint in app/api.py (gated by RequireAuth,
NOT RequireStartupMember -- Part 10's explicit requirement).

Reuses the exact same local-RSA-keypair JWT-mocking harness as every
prior phase's test file (no live Clerk dependency). Every row here uses
a distinctive zztest_investor_* user-id prefix and a "ZZTest Investor"
company-name prefix, cleaned up in a finally block even on failure. No
test here makes a real LLM/Tavily call.

Central thesis under test: Investor Workspace is a read-only intelligence
layer over the existing saved_startups relationship -- it never creates a
new watchlist table, never requires startup_membership, never mutates
SPS/methodology/Rankings/Discovery/VPS/Fundraising Readiness, and its
deltas are honest (never fabricated to zero when history is missing).

Run with:
    python -m app.tests.test_investor_workspace
"""

import time
from contextlib import contextmanager
from datetime import datetime, timezone

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.ai.investor_workspace import (
    PILLAR_KEYS,
    PILLAR_MEANINGFUL_CHANGE_THRESHOLD,
    SPS_MEANINGFUL_CHANGE_THRESHOLD,
    assess_investor_workspace,
)
from app.database.db import (
    engine,
    get_or_create_startup,
    get_watchlist_startups_for_user,
    save_analysis,
    save_startup_for_user,
    unsave_startup_for_user,
)

USER_A = "zztest_investor_user_a"
USER_B = "zztest_investor_user_b"
ALL_USERS = [USER_A, USER_B]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_PREFIX = "ZZTest Investor"

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


# --- Test data helpers -------------------------------------------------------


def _canonical_methodology(sps: float, pillar_scores: dict | None = None) -> dict:
    from app.ai.sie_v2_methodology import METHODOLOGY_VERSION

    pillar_scores = pillar_scores or {}
    methodology = {
        "startup_intelligence_score": sps,
        "context": {"company_stage": "Seed", "industry": "SaaS"},
        "analysis_context": {"methodology_version": METHODOLOGY_VERSION, "evidence_sources": ["company_description"], "analysis_type": "public"},
    }
    for key in PILLAR_KEYS:
        score = pillar_scores.get(key, 7.0)
        methodology[key] = {
            "score": score,
            "confidence": "Medium",
            "score_breakdown": {"evidence_coverage": 60},
            "strengths": [],
            "weaknesses": [],
        }
    return methodology


def _make_analyzed_startup(name_suffix: str, analyses: list[dict], submitted_by_user_id: str | None = USER_A) -> int:
    """
    Creates a startup with one or more canonical analyses, oldest first.
    Each dict in `analyses` is {"sps": float, "pillars": {...}}.

    Portfolio Release Task 3B -- Secure Analysis Visibility: defaults to
    USER_A as submitter, since USER_A is this file's overwhelmingly common
    workspace-viewing user and watching (saving) a startup no longer
    grants visibility into its analysis content on its own (approved
    decision, item 5 -- get_watchlist_startups_for_user() had the exact
    same gap get_saved_startups_for_user() did, now closed the same way).
    This is a genuine, real product consequence worth being explicit
    about, not just a test-fixture nuisance: Investor Workspace's original
    premise -- watching OTHER founders' already-submitted analyses -- is
    now, correctly, only possible for an analysis's submitter or an
    approved startup member; an unrelated investor watching a startup they
    have no other relationship to now sees the watchlist entry with no
    visible intelligence (latest/previous both None), exactly like the
    "zero analyses yet" case already handled before this task. See
    test_watching_without_authorization_shows_no_intelligence below for
    dedicated coverage of that exact case; every other test in this file
    passes submitted_by_user_id=USER_A precisely to keep testing SPS-delta
    computation/ordering/pillar logic, not authorization.
    """
    company_name = f"{TEST_PREFIX} {name_suffix}"

    for entry in analyses:
        save_analysis(
            company_text=f"Text for {company_name}",
            summary="s", risk_analysis="r", competitor_analysis="c", memo="m",
            structured_analysis={"company_name": company_name, "industry": "SaaS", "stage": "Seed", "business_model": "SaaS"},
            investment_score={}, founder_analysis={}, market_analysis={}, sources=[], traction_analysis={},
            market_score=None, team_score=None, product_score=None, competition_score=None,
            traction_score=None, financial_score=None, overall_score=None, recommendation=None,
            readiness_score=None, readiness_summary=None,
            methodology=_canonical_methodology(entry["sps"], entry.get("pillars")),
            submitted_by_user_id=submitted_by_user_id,
        )
        # save_analysis persists created_at as now() -- tests that need a
        # deterministic ordering between two analyses rely on real
        # wall-clock separation, same technique test_founder_reanalysis.py
        # already uses for "latest analysis wins" tests.
        time.sleep(0.01)

    return get_or_create_startup(company_name)


def _make_unanalyzed_startup(name_suffix: str) -> int:
    return get_or_create_startup(f"{TEST_PREFIX} {name_suffix}")


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in ALL_USERS:
            connection.execute(text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"), {"id": user_id})


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            DELETE FROM saved_startups
            WHERE user_id = ANY(:ids) OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
        """), {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("""
            DELETE FROM startup_memberships
            WHERE user_id = ANY(:ids) OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
        """), {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("""
            DELETE FROM analyses
            WHERE startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern) OR company_name ILIKE :pattern2
        """), {"pattern": f"{TEST_PREFIX.lower()}%", "pattern2": f"{TEST_PREFIX}%"})
        connection.execute(text("DELETE FROM startups WHERE normalized_name LIKE :pattern"), {"pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ALL_USERS})


# --- 1: authentication --------------------------------------------------


def test_unauthenticated_request_rejected() -> None:
    with _patched_auth():
        response = client.get("/investor/workspace")
    expect(response.status_code == 401, f"Expected 401, got {response.status_code}")


# --- 2: empty watchlist ---------------------------------------------------


def test_zero_saved_startups_returns_honest_empty_result() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        body = response.json()
        expect(body["watched_startups"] == [], "Must be an empty list, not an error")
        expect(body["overview"]["watched_count"] == 0, "Overview must honestly report zero")
        expect(body["overview"]["average_current_sps"] is None, "Must not fabricate an average from nothing")
    finally:
        _cleanup()


# --- 3-4: isolation --------------------------------------------------------


def test_only_current_users_saved_startups_returned() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("OnlyMine", [{"sps": 60.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        names = [w["company_name"] for w in response.json()["watched_startups"]]
        expect(f"{TEST_PREFIX} OnlyMine" in names, "The saving user must see their own saved startup")
    finally:
        _cleanup()


def test_another_users_saved_startup_never_leaks() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NeverLeaks", [{"sps": 60.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_B))
        names = [w["company_name"] for w in response.json()["watched_startups"]]
        expect(f"{TEST_PREFIX} NeverLeaks" not in names, "User B must never see User A's saved startup")
        expect(response.json()["overview"]["watched_count"] == 0, "User B's watchlist must be empty")
    finally:
        _cleanup()


def test_watching_without_authorization_shows_no_intelligence() -> None:
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility, approved
    decision item 5: watching (saving) a startup does not, on its own,
    grant visibility into its analysis content. USER_B watches a startup
    only USER_A (the submitter, with no relationship to USER_B) has
    analyzed -- the watchlist entry must still appear (USER_B's own real
    saved_startups row), but with no visible SPS/intelligence, never
    USER_A's private methodology. This is the dedicated regression test
    for the get_watchlist_startups_for_user() gap this task closed
    (previously: NO visibility filter at all on the underlying analysis
    content, only on the watchlist row itself).
    """
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NotAuthorized", [{"sps": 77.0}], submitted_by_user_id=USER_A)
    try:
        save_startup_for_user(USER_B, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_B))

        body = response.json()
        watched = next(w for w in body["watched_startups"] if w["startup_id"] == startup_id)

        expect(watched is not None, "USER_B's own watchlist entry must still appear")
        expect(
            watched["has_canonical_analysis"] is False,
            f"Expected has_canonical_analysis=False for an analysis USER_B is not authorized to see, "
            f"got {watched['has_canonical_analysis']!r}",
        )
        expect(
            watched["current_sps"] is None,
            f"Expected no visible current_sps, got {watched['current_sps']!r}",
        )
        expect(
            watched["previous_sps"] is None,
            f"Expected no visible previous_sps either, got {watched['previous_sps']!r}",
        )
    finally:
        _cleanup()


# --- 5: current SPS resolution ---------------------------------------------


def test_current_sps_resolves_from_latest_canonical_analysis() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("LatestSps", [{"sps": 50.0}, {"sps": 65.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        watched = response.json()["watched_startups"][0]
        expect(watched["current_sps"] == 65.0, f"Expected latest SPS 65.0, got {watched['current_sps']}")
        expect(watched["previous_sps"] == 50.0, f"Expected previous SPS 50.0, got {watched['previous_sps']}")
    finally:
        _cleanup()


# --- 6: no fake delta with one analysis -------------------------------------


def test_single_analysis_has_no_fake_delta() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SingleAnalysis", [{"sps": 55.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        watched = response.json()["watched_startups"][0]
        expect(watched["has_multiple_analyses"] is False, "Must report exactly one analysis")
        expect(watched["sps_delta"] is None, "Must never fabricate a delta from a single analysis")
        expect(watched["previous_sps"] is None, "previous_sps must be None, not 0")
        for pillar in watched["pillars"]:
            expect(pillar["delta"] is None, f"{pillar['pillar']} delta must be None, not 0, with only one analysis")
    finally:
        _cleanup()


# --- 7-10: SPS delta correctness --------------------------------------------


def test_multiple_analyses_gets_correct_sps_delta() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MultiDelta", [{"sps": 60.0}, {"sps": 63.5}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        watched = response.json()["watched_startups"][0]
        expect(watched["has_multiple_analyses"] is True, "Must report two analyses")
        expect(abs(watched["sps_delta"] - 3.5) < 1e-6, f"Expected delta 3.5, got {watched['sps_delta']}")
    finally:
        _cleanup()


def test_positive_sps_change_calculated_correctly() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("PositiveSps", [{"sps": 40.0}, {"sps": 48.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        watched = response.json()["watched_startups"][0]
        expect(watched["sps_delta"] > 0, "Delta must be positive")
        expect(abs(watched["sps_delta"] - 8.0) < 1e-6, f"Expected +8.0, got {watched['sps_delta']}")
    finally:
        _cleanup()


def test_negative_sps_change_calculated_correctly() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NegativeSps", [{"sps": 70.0}, {"sps": 61.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        watched = response.json()["watched_startups"][0]
        expect(watched["sps_delta"] < 0, "Delta must be negative")
        expect(abs(watched["sps_delta"] - (-9.0)) < 1e-6, f"Expected -9.0, got {watched['sps_delta']}")
    finally:
        _cleanup()


def test_unchanged_sps_calculated_correctly() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("UnchangedSps", [{"sps": 55.5}, {"sps": 55.5}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        watched = response.json()["watched_startups"][0]
        expect(watched["sps_delta"] == 0.0, f"Expected 0.0, got {watched['sps_delta']}")
    finally:
        _cleanup()


# --- 11-13: pillar deltas ----------------------------------------------------


def test_pillar_positive_delta_correct() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup(
        "PillarUp",
        [{"sps": 60.0, "pillars": {"traction": 5.0}}, {"sps": 62.0, "pillars": {"traction": 7.0}}],
    )
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        pillars = {p["pillar"]: p for p in response.json()["watched_startups"][0]["pillars"]}
        expect(abs(pillars["traction"]["delta"] - 2.0) < 1e-6, f"Expected +2.0, got {pillars['traction']['delta']}")
    finally:
        _cleanup()


def test_pillar_negative_delta_correct() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup(
        "PillarDown",
        [{"sps": 60.0, "pillars": {"financial_health": 8.0}}, {"sps": 58.0, "pillars": {"financial_health": 6.5}}],
    )
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        pillars = {p["pillar"]: p for p in response.json()["watched_startups"][0]["pillars"]}
        expect(abs(pillars["financial_health"]["delta"] - (-1.5)) < 1e-6, f"Expected -1.5, got {pillars['financial_health']['delta']}")
    finally:
        _cleanup()


def test_unavailable_pillar_remains_unavailable() -> None:
    """A pillar with no score (Unavailable) must stay null in both the
    score and the delta -- never coerced to 0, and never silently given a
    fake delta against a null baseline."""
    _ensure_test_users()
    company_name = f"{TEST_PREFIX} UnavailablePillar"
    from app.ai.sie_v2_methodology import METHODOLOGY_VERSION

    methodology = _canonical_methodology(60.0)
    methodology["traction"] = {
        "score": None,
        "confidence": "Low",
        "score_breakdown": {"evidence_coverage": 0},
        "strengths": [],
        "weaknesses": [],
    }
    save_analysis(
        company_text="text", summary="s", risk_analysis="r", competitor_analysis="c", memo="m",
        structured_analysis={"company_name": company_name, "industry": "SaaS", "stage": "Seed", "business_model": "SaaS"},
        investment_score={}, founder_analysis={}, market_analysis={}, sources=[], traction_analysis={},
        market_score=None, team_score=None, product_score=None, competition_score=None,
        traction_score=None, financial_score=None, overall_score=None, recommendation=None,
        readiness_score=None, readiness_summary=None,
        methodology=methodology,
    )
    startup_id = get_or_create_startup(company_name)
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        pillars = {p["pillar"]: p for p in response.json()["watched_startups"][0]["pillars"]}
        expect(pillars["traction"]["current_score"] is None, "Unavailable pillar score must stay None")
        expect(pillars["traction"]["delta"] is None, "Unavailable pillar delta must stay None, never fabricated")
    finally:
        _cleanup()


# --- 14-15: history ordering / latest date ----------------------------------


def test_historical_analysis_ordering_correct() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("Ordering", [{"sps": 10.0}, {"sps": 20.0}, {"sps": 30.0}])
    try:
        rows = get_watchlist_startups_for_user(USER_A)
        expect(rows == [], "Sanity: nothing saved yet for this direct-DB check")
        save_startup_for_user(USER_A, startup_id)
        rows = get_watchlist_startups_for_user(USER_A)
        row = rows[0]
        expect(row["latest"]["methodology"]["startup_intelligence_score"] == 30.0, "Latest must be the most recent analysis (30.0), not first-inserted")
        expect(row["previous"]["methodology"]["startup_intelligence_score"] == 20.0, "Previous must be the second-most-recent (20.0), not the oldest")
    finally:
        _cleanup()


def test_latest_analysis_date_correct() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("LatestDate", [{"sps": 40.0}, {"sps": 45.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with engine.begin() as connection:
            expected = connection.execute(text("""
                SELECT created_at FROM analyses WHERE startup_id=:s ORDER BY created_at DESC, id DESC LIMIT 1
            """), {"s": startup_id}).scalar()
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        watched = response.json()["watched_startups"][0]
        returned = datetime.fromisoformat(watched["latest_analysis_at"])
        if returned.tzinfo is None:
            returned = returned.replace(tzinfo=timezone.utc)
        expected_aware = expected.replace(tzinfo=timezone.utc) if expected.tzinfo is None else expected
        expect(abs((returned - expected_aware).total_seconds()) < 1, "latest_analysis_at must match the real latest analysis row's created_at")
    finally:
        _cleanup()


# --- 16-18: save/unsave lifecycle -------------------------------------------


def test_unsaved_startups_excluded() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NeverSaved", [{"sps": 50.0}])
    try:
        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        names = [w["company_name"] for w in response.json()["watched_startups"]]
        expect(f"{TEST_PREFIX} NeverSaved" not in names, "A startup never saved by this user must not appear")
    finally:
        _cleanup()


def test_saving_startup_makes_it_appear() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("AppearsAfterSave", [{"sps": 50.0}])
    try:
        with _patched_auth():
            before = client.get("/investor/workspace", headers=_auth_headers(USER_A)).json()
        names_before = [w["company_name"] for w in before["watched_startups"]]
        expect(f"{TEST_PREFIX} AppearsAfterSave" not in names_before, "Must not appear before saving")

        save_startup_for_user(USER_A, startup_id)

        with _patched_auth():
            after = client.get("/investor/workspace", headers=_auth_headers(USER_A)).json()
        names_after = [w["company_name"] for w in after["watched_startups"]]
        expect(f"{TEST_PREFIX} AppearsAfterSave" in names_after, "Must appear immediately after saving")
    finally:
        _cleanup()


def test_unsaving_startup_removes_it() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("RemovedAfterUnsave", [{"sps": 50.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            before = client.get("/investor/workspace", headers=_auth_headers(USER_A)).json()
        expect(f"{TEST_PREFIX} RemovedAfterUnsave" in [w["company_name"] for w in before["watched_startups"]], "Sanity: must appear before unsaving")

        unsave_startup_for_user(USER_A, startup_id)

        with _patched_auth():
            after = client.get("/investor/workspace", headers=_auth_headers(USER_A)).json()
        expect(f"{TEST_PREFIX} RemovedAfterUnsave" not in [w["company_name"] for w in after["watched_startups"]], "Must disappear immediately after unsaving")
    finally:
        _cleanup()


# --- 19: compare continues to use canonical startup_id -----------------------


def test_comparison_continues_to_use_canonical_startup_id() -> None:
    _ensure_test_users()
    startup_a = _make_analyzed_startup("CompareA", [{"sps": 55.0}])
    startup_b = _make_analyzed_startup("CompareB", [{"sps": 65.0}])
    try:
        save_startup_for_user(USER_A, startup_a)
        save_startup_for_user(USER_A, startup_b)

        with _patched_auth():
            workspace = client.get("/investor/workspace", headers=_auth_headers(USER_A)).json()

            ids_in_workspace = {w["startup_id"] for w in workspace["watched_startups"]}
            expect({startup_a, startup_b} <= ids_in_workspace, "Both watched startup_ids must be present")

            # Portfolio Release Task 3B: /compare now requires auth
            # (approved decision) -- USER_A is the submitter of both
            # analyses (see _make_analyzed_startup's own default), so is
            # authorized to compare them.
            response = client.get(
                "/compare", params={"startups": f"{startup_a},{startup_b}"}, headers=_auth_headers(USER_A)
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        resolved_ids = {row["startup_id"] for row in response.json()["startups"]}
        expect({startup_a, startup_b} <= resolved_ids, "Compare must resolve the exact same canonical startup_ids Investor Workspace uses")
    finally:
        _cleanup()


# --- 20-21: membership independence -----------------------------------------


def test_investor_workspace_does_not_require_startup_membership() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoMembershipNeeded", [{"sps": 50.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with engine.begin() as connection:
            membership_count = connection.execute(text(
                "SELECT count(*) FROM startup_memberships WHERE user_id=:u AND startup_id=:s"
            ), {"u": USER_A, "s": startup_id}).scalar()
        expect(membership_count == 0, "Sanity: no membership exists")

        with _patched_auth():
            response = client.get("/investor/workspace", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200 with no membership: {response.text}")
        names = [w["company_name"] for w in response.json()["watched_startups"]]
        expect(f"{TEST_PREFIX} NoMembershipNeeded" in names, "Watching a startup must work with zero startup_memberships rows")
    finally:
        _cleanup()


def test_saving_startup_does_not_create_startup_membership() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoMembershipCreated", [{"sps": 50.0}])
    try:
        with engine.begin() as connection:
            before = connection.execute(text("SELECT count(*) FROM startup_memberships WHERE startup_id=:s"), {"s": startup_id}).scalar()

        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            client.get("/investor/workspace", headers=_auth_headers(USER_A))

        with engine.begin() as connection:
            after = connection.execute(text("SELECT count(*) FROM startup_memberships WHERE startup_id=:s"), {"s": startup_id}).scalar()
        expect(before == after == 0, "Saving a startup and viewing Investor Workspace must never create a startup_memberships row")
    finally:
        _cleanup()


# --- 22-28: read-only / no contamination ------------------------------------


def test_investor_reads_do_not_modify_analyses() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoAnalysesMutation", [{"sps": 55.0}, {"sps": 60.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with engine.begin() as connection:
            before = connection.execute(text("SELECT count(*) FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()
        with _patched_auth():
            for _ in range(3):
                client.get("/investor/workspace", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT count(*) FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()
        expect(before == after, "Viewing Investor Workspace repeatedly must never create/delete analyses rows")
    finally:
        _cleanup()


def test_investor_reads_do_not_modify_methodology_jsonb() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoMethodologyMutation", [{"sps": 55.0}, {"sps": 60.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with engine.begin() as connection:
            before = connection.execute(text("""
                SELECT methodology::text FROM analyses WHERE startup_id=:s ORDER BY created_at DESC, id DESC LIMIT 1
            """), {"s": startup_id}).scalar()
        with _patched_auth():
            client.get("/investor/workspace", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("""
                SELECT methodology::text FROM analyses WHERE startup_id=:s ORDER BY created_at DESC, id DESC LIMIT 1
            """), {"s": startup_id}).scalar()
        expect(before == after, "Viewing Investor Workspace must never mutate the stored methodology JSONB")
    finally:
        _cleanup()


def test_sps_history_remains_unchanged() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoSpsHistoryChange", [{"sps": 55.0}, {"sps": 60.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        # SPS History is served by get_sps_history() (app/api.py's
        # /startup-sps-history/{company_name}); comparing the raw analyses
        # row count is the direct, unambiguous way to prove nothing was
        # added/removed by Investor Workspace reads.
        with engine.begin() as connection:
            before_count = connection.execute(text("SELECT count(*) FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()

        with _patched_auth():
            client.get("/investor/workspace", headers=_auth_headers(USER_A))

        with engine.begin() as connection:
            after_count = connection.execute(text("SELECT count(*) FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()

        expect(before_count == after_count, "SPS History's underlying analyses rows must be unchanged")
    finally:
        _cleanup()


def test_rankings_remain_unchanged() -> None:
    # Portfolio Release Task 3B: /rankings now requires auth (approved
    # decision) -- USER_A is the submitter (see _make_analyzed_startup's
    # own default), so is authorized to see it in Rankings.
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoRankingsChange", [{"sps": 55.0}])
    company_name = f"{TEST_PREFIX} NoRankingsChange"
    try:
        save_startup_for_user(USER_A, startup_id)

        def _score():
            with _patched_auth():
                rows = client.get("/rankings", headers=_auth_headers(USER_A)).json()
            matches = [r for r in rows if r.get("company_name") == company_name]
            return matches[0]["overall_score"] if matches else None

        before = _score()
        with _patched_auth():
            client.get("/investor/workspace", headers=_auth_headers(USER_A))
        after = _score()
        expect(before == after, f"Rankings must be unchanged, before={before} after={after}")
    finally:
        _cleanup()


def test_discovery_remains_unchanged() -> None:
    # Portfolio Release Task 3B: /discover now requires auth (approved
    # decision) -- USER_A is the submitter, so is authorized to see it.
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoDiscoveryChange", [{"sps": 55.0}])
    company_name = f"{TEST_PREFIX} NoDiscoveryChange"
    try:
        save_startup_for_user(USER_A, startup_id)

        def _score():
            with _patched_auth():
                rows = client.get(
                    "/discover", params={"query": company_name}, headers=_auth_headers(USER_A)
                ).json()["results"]
            matches = [r for r in rows if r.get("company_name") == company_name]
            return matches[0]["overall_score"] if matches else None

        before = _score()
        with _patched_auth():
            client.get("/investor/workspace", headers=_auth_headers(USER_A))
        after = _score()
        expect(before == after, f"Discovery must be unchanged, before={before} after={after}")
    finally:
        _cleanup()


def test_vps_remains_unchanged() -> None:
    """Static-flavored check, same pattern Phase 8 used for the same
    claim: a modeled venture's VPS is untouched by any Investor Workspace
    read for an unrelated real startup."""
    from app.database.db import create_modeled_venture

    _ensure_test_users()
    startup_id = _make_analyzed_startup("VpsUnrelated", [{"sps": 55.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        venture_id = create_modeled_venture(
            user_id=USER_A, name="Idea", description=None, industry=None,
            business_model=None, target_customer=None, stage=None,
            assumptions={}, model_result={"vps": 42.0},
        )
        with engine.begin() as connection:
            before = connection.execute(text("SELECT model_result::text FROM modeled_ventures WHERE id=:id"), {"id": venture_id}).scalar()
        with _patched_auth():
            client.get("/investor/workspace", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT model_result::text FROM modeled_ventures WHERE id=:id"), {"id": venture_id}).scalar()
        expect(before == after, "VPS/modeled venture data must be unaffected by Investor Workspace reads")
    finally:
        _cleanup()


def test_fundraising_readiness_remains_unchanged() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("FundraisingUnchanged", [{"sps": 55.0}, {"sps": 60.0}])
    try:
        save_startup_for_user(USER_A, startup_id)
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO startup_memberships (user_id, startup_id, role) VALUES (:u, :s, 'member') ON CONFLICT DO NOTHING"
            ), {"u": USER_A, "s": startup_id})

        with _patched_auth():
            before = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()
            client.get("/investor/workspace", headers=_auth_headers(USER_A))
            after = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()

        expect(before == after, "Fundraising Readiness output must be byte-identical before/after an Investor Workspace read")
    finally:
        _cleanup()


# --- deterministic threshold + no-LLM static checks -------------------------


def test_meaningful_change_thresholds_are_deterministic_constants() -> None:
    expect(isinstance(SPS_MEANINGFUL_CHANGE_THRESHOLD, float), "Threshold must be a plain constant, not computed at runtime")
    expect(isinstance(PILLAR_MEANINGFUL_CHANGE_THRESHOLD, float), "Threshold must be a plain constant, not computed at runtime")


def test_no_llm_import_in_investor_workspace_module() -> None:
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent / "ai" / "investor_workspace.py").read_text()
    expect("openai" not in source.lower(), "investor_workspace.py must never import an LLM client")
    expect("chat.completions" not in source, "investor_workspace.py must never call an LLM")


def test_no_new_watchlist_table_created() -> None:
    import pathlib

    db_source = (pathlib.Path(__file__).resolve().parent.parent / "database" / "db.py").read_text()
    for forbidden in ("CREATE TABLE IF NOT EXISTS investor_startups", "CREATE TABLE IF NOT EXISTS portfolio_startups", "CREATE TABLE IF NOT EXISTS watchlist_startups"):
        expect(forbidden not in db_source, f"Must not introduce a duplicate watchlist table: {forbidden}")


def test_deterministic_assessment_repeatable() -> None:
    methodology_pair = [
        {"startup_id": 1, "company_name": "X", "saved_at": datetime.now(timezone.utc), "latest": {"analysis_id": 2, "created_at": datetime.now(timezone.utc), "methodology": _canonical_methodology(60.0)}, "previous": {"analysis_id": 1, "created_at": datetime.now(timezone.utc), "methodology": _canonical_methodology(55.0)}},
    ]
    now = datetime.now(timezone.utc)
    a1 = assess_investor_workspace(methodology_pair, now=now)
    a2 = assess_investor_workspace(methodology_pair, now=now)
    expect(a1.watched_startups[0].sps_delta == a2.watched_startups[0].sps_delta, "Identical input must produce identical delta")
    expect([c.statement for c in a1.recent_changes] == [c.statement for c in a2.recent_changes], "Identical input must produce identical recent changes")


TESTS = [
    test_unauthenticated_request_rejected,
    test_zero_saved_startups_returns_honest_empty_result,
    test_only_current_users_saved_startups_returned,
    test_another_users_saved_startup_never_leaks,
    test_watching_without_authorization_shows_no_intelligence,
    test_current_sps_resolves_from_latest_canonical_analysis,
    test_single_analysis_has_no_fake_delta,
    test_multiple_analyses_gets_correct_sps_delta,
    test_positive_sps_change_calculated_correctly,
    test_negative_sps_change_calculated_correctly,
    test_unchanged_sps_calculated_correctly,
    test_pillar_positive_delta_correct,
    test_pillar_negative_delta_correct,
    test_unavailable_pillar_remains_unavailable,
    test_historical_analysis_ordering_correct,
    test_latest_analysis_date_correct,
    test_unsaved_startups_excluded,
    test_saving_startup_makes_it_appear,
    test_unsaving_startup_removes_it,
    test_comparison_continues_to_use_canonical_startup_id,
    test_investor_workspace_does_not_require_startup_membership,
    test_saving_startup_does_not_create_startup_membership,
    test_investor_reads_do_not_modify_analyses,
    test_investor_reads_do_not_modify_methodology_jsonb,
    test_sps_history_remains_unchanged,
    test_rankings_remain_unchanged,
    test_discovery_remains_unchanged,
    test_vps_remains_unchanged,
    test_fundraising_readiness_remains_unchanged,
    test_meaningful_change_thresholds_are_deterministic_constants,
    test_no_llm_import_in_investor_workspace_module,
    test_no_new_watchlist_table_created,
    test_deterministic_assessment_repeatable,
]


def main() -> None:
    print("\nPhase 9 -- Investor Workspace V1 tests")
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
