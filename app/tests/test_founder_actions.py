"""
Regression tests for Phase 7.3 -- Founder Progress & Improvement V1:
app/database/db.py's founder_actions functions, and the
GET/POST /founder/startups/{startup_id}/actions and
PATCH /founder/startups/{startup_id}/actions/{action_id} endpoints in
app/api.py (all gated by app/auth.py's RequireStartupMember, exactly like
Phase 7.2's GET /founder/startups/{startup_id}).

Reuses the exact same local-RSA-keypair JWT-mocking harness as
test_founder_workspace.py/test_founder_reanalysis.py (no live Clerk
dependency). Every row here uses a distinctive zztest_actions_* user-id
prefix and a "ZZTest Actions" company-name prefix, cleaned up in a
finally block even on failure. No test here makes a real LLM/Tavily call
(the two re-analysis tests reuse test_founder_reanalysis.py's
patched-pipeline technique).

Central thesis under test: founder_actions is pure workflow state.
Nothing in this file ever asserts a *_score, methodology, or
startup_memberships change as a RESULT of an action -- several tests
below assert the opposite (no change), which is the actual point.

Run with:
    python -m app.tests.test_founder_actions
"""

import time
from contextlib import contextmanager

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
from app.models.analysis import (
    ExecutionAnalysisResult,
    FinancialAnalysisResult,
    FounderAnalysisResult,
    MarketAnalysisResult,
    ProductAnalysisResult,
    TractionAnalysisResult,
)
from app.workflows.due_diligence_workflow import build_sie_methodology_analysis

USER_A = "zztest_actions_user_a"
USER_B = "zztest_actions_user_b"
ADMIN_USER = "zztest_actions_admin"
ALL_USERS = [USER_A, USER_B, ADMIN_USER]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_PREFIX = "ZZTest Actions"

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


# --- Fast, LLM-free fake pipeline (reused for the two re-analysis tests) ----


@contextmanager
def patched_pipeline(extracted_company_name: str = "ZZTest Actions Extracted Variant"):
    def fake_run_due_diligence(company_text, analysis_type="public", evidence_sources=None):
        sie_analysis = build_sie_methodology_analysis(
            structured_analysis={
                "company_name": extracted_company_name,
                "industry": "SaaS",
                "business_model": "SaaS",
            },
            readiness=None,
            founder_analysis=FounderAnalysisResult(),
            market_analysis=MarketAnalysisResult(),
            product_analysis=ProductAnalysisResult(),
            execution_analysis=ExecutionAnalysisResult(),
            traction_analysis=TractionAnalysisResult(),
            financial_analysis=FinancialAnalysisResult(),
            analysis_type=analysis_type,
            evidence_sources=evidence_sources,
        )
        return {
            "summary": "s", "risk_analysis": "r", "competitor_analysis": "c", "memo": "m",
            "structured_analysis": {"company_name": extracted_company_name},
            "investment_score": {}, "founder_analysis": FounderAnalysisResult(),
            "market_analysis": MarketAnalysisResult(), "sources": [],
            "traction_analysis": TractionAnalysisResult(),
            "market_score": None, "team_score": None, "product_score": None,
            "competition_score": None, "traction_score": None, "financial_score": None,
            "overall_score": sie_analysis.startup_intelligence_score,
            "recommendation": None, "readiness_score": None, "readiness_summary": None,
            "sie_analysis": sie_analysis,
        }

    original = api.run_due_diligence
    api.run_due_diligence = fake_run_due_diligence
    try:
        yield
    finally:
        api.run_due_diligence = original


# --- Test data helpers -------------------------------------------------------


def _canonical_methodology(sps: float = 50.0) -> dict:
    from app.ai.sie_v2_methodology import METHODOLOGY_VERSION

    return {
        "startup_intelligence_score": sps,
        "market": {"score": 7.0}, "team": {"score": 7.0}, "product": {"score": 7.0},
        "execution": {"score": 7.0}, "traction": {"score": 7.0}, "financial_health": {"score": 7.0},
        "analysis_context": {"methodology_version": METHODOLOGY_VERSION},
    }


def _make_analyzed_startup(name_suffix: str) -> int:
    company_name = f"{TEST_PREFIX} {name_suffix}"
    save_analysis(
        company_text=f"Original text for {company_name}",
        summary="s", risk_analysis="r", competitor_analysis="c", memo="m",
        structured_analysis={"company_name": company_name, "industry": "SaaS", "stage": "Seed", "business_model": "SaaS"},
        investment_score={}, founder_analysis={}, market_analysis={}, sources=[], traction_analysis={},
        market_score=None, team_score=None, product_score=None, competition_score=None,
        traction_score=None, financial_score=None, overall_score=None, recommendation=None,
        readiness_score=None, readiness_summary=None,
        methodology=_canonical_methodology(),
    )
    return get_or_create_startup(company_name)


def _make_unanalyzed_startup(name_suffix: str) -> int:
    return get_or_create_startup(f"{TEST_PREFIX} {name_suffix}")


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in ALL_USERS:
            connection.execute(
                text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
                {"id": user_id},
            )


def _grant_membership(user_id: str, startup_id: int, role: str = "member") -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO startup_memberships (user_id, startup_id, role)
            VALUES (:user_id, :startup_id, :role)
            ON CONFLICT (user_id, startup_id) DO NOTHING
        """), {"user_id": user_id, "startup_id": startup_id, "role": role})


def _cleanup() -> None:
    with engine.begin() as connection:
        # Phase 10.1B: this file's re-analysis tests call POST /analyze
        # against a small fixed set of zztest user ids -- without this,
        # repeated runs would accumulate real analysis_runs rows and
        # eventually trip either the daily usage cap or the
        # duplicate-cooldown check (see app/database/db.py's
        # analysis_runs section).
        connection.execute(
            text("DELETE FROM analysis_runs WHERE user_id = ANY(:ids)"),
            {"ids": ALL_USERS},
        )
        connection.execute(
            text("""
                DELETE FROM founder_actions
                WHERE created_by_user_id = ANY(:ids)
                   OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
            """),
            {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"},
        )
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
        connection.execute(text("DELETE FROM saved_startups WHERE user_id = ANY(:ids)"), {"ids": ALL_USERS})
        connection.execute(text("DELETE FROM modeled_ventures WHERE user_id = ANY(:ids)"), {"ids": ALL_USERS})
        connection.execute(
            text("""
                DELETE FROM analyses
                WHERE startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
                   OR company_name ILIKE :pattern2
            """),
            {"pattern": f"{TEST_PREFIX.lower()}%", "pattern2": f"{TEST_PREFIX}%"},
        )
        connection.execute(text("DELETE FROM startups WHERE normalized_name LIKE :pattern"), {"pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ALL_USERS})


# --- 1-3: baseline list authorization ------------------------------------------


def test_member_can_list_actions() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MemberList")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json() == [], "Expected an honest empty list for a fresh startup")
    finally:
        _cleanup()


def test_non_member_cannot_list_actions() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NonMemberList")
    try:
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_signed_out_cannot_list_actions() -> None:
    startup_id = _make_analyzed_startup("SignedOutList")
    try:
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/actions")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")
    finally:
        _cleanup()


# --- 4-5: founder-created action, identity cannot be spoofed -------------------


def test_member_can_create_founder_action() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("CreateAction")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(
                f"/founder/startups/{startup_id}/actions",
                json={"title": "Talk to 10 more customers"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        body = response.json()
        expect(body["title"] == "Talk to 10 more customers", "Title must match")
        expect(body["source"] == "founder_created", "Default source must be founder_created")
        expect(body["status"] == "todo", "New actions must start as todo")
        expect(body["related_pillar"] is None, "related_pillar must be optional and unset here")
    finally:
        _cleanup()


def test_client_cannot_spoof_created_by_user_id() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SpoofCreator")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(
                f"/founder/startups/{startup_id}/actions",
                json={"title": "x", "created_by_user_id": USER_B},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(
            response.json()["created_by_user_id"] == USER_A,
            f"created_by_user_id must be the real caller, got {response.json()['created_by_user_id']!r}",
        )
    finally:
        _cleanup()


# --- 6-8: SIE-recommendation provenance and deduplication ----------------------


def test_member_can_add_sie_recommendation() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("AddRecommendation")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(
                f"/founder/startups/{startup_id}/actions",
                json={
                    "title": "Obtain quantitative customer growth data",
                    "related_pillar": "traction",
                    "source": "sie_recommendation",
                },
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        body = response.json()
        expect(body["source"] == "sie_recommendation", "Source must be preserved")
        expect(body["related_pillar"] == "traction", "related_pillar must be preserved")
    finally:
        _cleanup()


def test_recommendation_provenance_preserved() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("Provenance")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            client.post(
                f"/founder/startups/{startup_id}/actions",
                json={"title": "Improve retention metrics", "related_pillar": "traction", "source": "sie_recommendation"},
                headers=_auth_headers(USER_A),
            )
            listing = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        rows = listing.json()
        expect(len(rows) == 1, f"Expected 1 action, got {len(rows)}")
        expect(rows[0]["source"] == "sie_recommendation" and rows[0]["related_pillar"] == "traction", "Provenance must survive a round trip through the list endpoint")
    finally:
        _cleanup()


def test_duplicate_sie_recommendation_does_not_spam() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoDuplicateSpam")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            for _ in range(5):
                response = client.post(
                    f"/founder/startups/{startup_id}/actions",
                    json={"title": "Improve customer validation", "related_pillar": "traction", "source": "sie_recommendation"},
                    headers=_auth_headers(USER_A),
                )
                expect(response.status_code == 200, f"Expected 200: {response.text}")
            listing = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        rows = listing.json()
        expect(len(rows) == 1, f"Expected exactly 1 row after 5 identical 'Add to Plan' clicks, got {len(rows)}")
    finally:
        _cleanup()


def test_founder_created_duplicates_are_not_deduplicated() -> None:
    """Founder-authored text is never text-deduplicated (Part 13) -- two
    founder_created actions with identical titles are both kept."""
    _ensure_test_users()
    startup_id = _make_analyzed_startup("FounderDupesAllowed")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            client.post(f"/founder/startups/{startup_id}/actions", json={"title": "Ship the new pricing page"}, headers=_auth_headers(USER_A))
            client.post(f"/founder/startups/{startup_id}/actions", json={"title": "Ship the new pricing page"}, headers=_auth_headers(USER_A))
            listing = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        expect(len(listing.json()) == 2, f"Expected 2 independent founder-created rows, got {len(listing.json())}")
    finally:
        _cleanup()


# --- 9-13: status lifecycle -----------------------------------------------------


def test_todo_to_in_progress() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("TodoToInProgress")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            response = client.patch(
                f"/founder/startups/{startup_id}/actions/{created['id']}",
                json={"status": "in_progress"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["status"] == "in_progress", "Status must update to in_progress")
    finally:
        _cleanup()


def test_in_progress_to_completed() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("InProgressToCompleted")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/actions/{created['id']}", json={"status": "in_progress"}, headers=_auth_headers(USER_A))
            response = client.patch(
                f"/founder/startups/{startup_id}/actions/{created['id']}",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["status"] == "completed", "Status must update to completed")
    finally:
        _cleanup()


def test_completed_at_set_correctly() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("CompletedAtSet")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            expect(created["completed_at"] is None, "completed_at must start unset")
            response = client.patch(
                f"/founder/startups/{startup_id}/actions/{created['id']}",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )
        expect(response.json()["completed_at"] is not None, "completed_at must be set on completion")
    finally:
        _cleanup()


def test_completed_item_can_be_reopened() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("Reopen")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/actions/{created['id']}", json={"status": "completed"}, headers=_auth_headers(USER_A))
            reopened = client.patch(
                f"/founder/startups/{startup_id}/actions/{created['id']}",
                json={"status": "todo"},
                headers=_auth_headers(USER_A),
            )
        expect(reopened.status_code == 200, f"Expected 200: {reopened.text}")
        expect(reopened.json()["status"] == "todo", "Status must revert to todo")
        expect(reopened.json()["completed_at"] is None, "completed_at must clear on reopen")
    finally:
        _cleanup()


def test_dismiss_behavior() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("Dismiss")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            response = client.patch(
                f"/founder/startups/{startup_id}/actions/{created['id']}",
                json={"status": "dismissed"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["status"] == "dismissed", "Status must update to dismissed")
    finally:
        _cleanup()


# --- 14-18: authorization boundary ----------------------------------------------


def test_user_cannot_mutate_another_startups_action() -> None:
    _ensure_test_users()
    startup_a = _make_analyzed_startup("CrossMutateA")
    startup_b = _make_analyzed_startup("CrossMutateB")
    try:
        _grant_membership(USER_A, startup_a)
        _grant_membership(USER_B, startup_b)
        with _patched_auth():
            created_on_b = client.post(f"/founder/startups/{startup_b}/actions", json={"title": "x"}, headers=_auth_headers(USER_B)).json()
            # USER_A tries to mutate an action that exists, but under
            # startup_a's own path -- action_id belongs to startup_b.
            response = client.patch(
                f"/founder/startups/{startup_a}/actions/{created_on_b['id']}",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_membership_removal_immediately_removes_access() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("RemovalTiming")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            still_member = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        expect(still_member.status_code == 200, "Sanity: must start out authorized")

        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            )

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404 immediately after removal, got {response.status_code}")
    finally:
        _cleanup()


def test_saved_startup_does_not_authorize_actions() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SavedNotAuthorized")
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_pending_claim_does_not_authorize_actions() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("PendingNotAuthorized")
    try:
        with _patched_auth(admin_ids=[ADMIN_USER]):
            client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            response = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_approved_claim_without_membership_does_not_authorize_actions() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ApprovedNoMembershipActions")
    try:
        with _patched_auth(admin_ids=[ADMIN_USER]):
            submitted = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            claim_id = submitted.json()["id"]
            client.post(f"/admin/startup-claims/{claim_id}/approve", headers=_auth_headers(ADMIN_USER))
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                    {"u": USER_A, "s": startup_id},
                )
            response = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_modeled_venture_does_not_authorize_actions() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("VentureNotAuthorized")
    try:
        create_modeled_venture(
            user_id=USER_A, name="Idea", description=None, industry=None,
            business_model=None, target_customer=None, stage=None,
            assumptions={}, model_result=None,
        )
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


# --- 19, 27: shared plan / cross-user isolation ---------------------------------


def test_two_members_of_same_startup_see_same_plan() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SharedPlan")
    try:
        _grant_membership(USER_A, startup_id)
        _grant_membership(USER_B, startup_id)
        with _patched_auth():
            client.post(f"/founder/startups/{startup_id}/actions", json={"title": "Added by A"}, headers=_auth_headers(USER_A))
            client.post(f"/founder/startups/{startup_id}/actions", json={"title": "Added by B"}, headers=_auth_headers(USER_B))

            listing_a = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A)).json()
            listing_b = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_B)).json()

        titles_a = sorted(row["title"] for row in listing_a)
        titles_b = sorted(row["title"] for row in listing_b)
        expect(titles_a == ["Added by A", "Added by B"], f"USER_A must see the full shared plan, got {titles_a}")
        expect(titles_a == titles_b, "Both members must see the exact same plan")
    finally:
        _cleanup()


def test_cross_startup_isolation_for_listing() -> None:
    _ensure_test_users()
    startup_a = _make_analyzed_startup("IsolationA")
    startup_b = _make_analyzed_startup("IsolationB")
    try:
        _grant_membership(USER_A, startup_a)
        _grant_membership(USER_A, startup_b)
        with _patched_auth():
            client.post(f"/founder/startups/{startup_a}/actions", json={"title": "Only in A"}, headers=_auth_headers(USER_A))
            listing_b = client.get(f"/founder/startups/{startup_b}/actions", headers=_auth_headers(USER_A)).json()
        expect(listing_b == [], "Startup B's plan must not include Startup A's action")
    finally:
        _cleanup()


# --- 20-23: no SPS contamination ------------------------------------------------


def test_founder_created_action_does_not_affect_sps() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoSpsFromFounderAction")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            sps_before = connection.execute(
                text("SELECT methodology->>'startup_intelligence_score' FROM analyses WHERE startup_id=:s"), {"s": startup_id}
            ).scalar()
        with _patched_auth():
            client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            sps_after = connection.execute(
                text("SELECT methodology->>'startup_intelligence_score' FROM analyses WHERE startup_id=:s"), {"s": startup_id}
            ).scalar()
        expect(sps_before == sps_after, f"SPS must be unchanged, before={sps_before} after={sps_after}")
    finally:
        _cleanup()


def test_completing_action_does_not_affect_sps() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoSpsFromCompletion")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            sps_before = connection.execute(
                text("SELECT methodology->>'startup_intelligence_score' FROM analyses WHERE startup_id=:s"), {"s": startup_id}
            ).scalar()
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/actions/{created['id']}", json={"status": "completed"}, headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            sps_after = connection.execute(
                text("SELECT methodology->>'startup_intelligence_score' FROM analyses WHERE startup_id=:s"), {"s": startup_id}
            ).scalar()
        expect(sps_before == sps_after, f"SPS must be unchanged, before={sps_before} after={sps_after}")
    finally:
        _cleanup()


def test_completing_action_does_not_affect_methodology_jsonb() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoMethodologyChange")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            methodology_before = connection.execute(
                text("SELECT methodology::text FROM analyses WHERE startup_id=:s"), {"s": startup_id}
            ).scalar()
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/actions/{created['id']}", json={"status": "completed"}, headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            methodology_after = connection.execute(
                text("SELECT methodology::text FROM analyses WHERE startup_id=:s"), {"s": startup_id}
            ).scalar()
        expect(methodology_before == methodology_after, "methodology JSONB must be byte-for-byte unchanged")
    finally:
        _cleanup()


def test_completing_action_does_not_affect_rankings() -> None:
    # Task 33 item 15: GET /rankings has required RequireAuth since a
    # prior security-hardening phase (see app/tests/test_security_
    # hardening.py::test_rankings_now_requires_auth, currently passing)
    # -- this test's own `_score_in_rankings()` helper predates that
    # change and called it with no Authorization header, which now
    # returns 401's JSON body ({"detail": ...}) instead of a list of
    # rows, crashing with AttributeError on `.get()` deep inside a list
    # comprehension. Fixed by authenticating the read, same as every
    # mutation call in this test already does -- the underlying "does
    # completing an action change the ranking?" behavior this test
    # checks is completely unchanged; only the read's own auth
    # requirement is new.
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoRankingsChange")
    try:
        _grant_membership(USER_A, startup_id)
        company_name = f"{TEST_PREFIX} NoRankingsChange"

        def _score_in_rankings():
            rows = client.get("/rankings", headers=_auth_headers(USER_A)).json()
            matches = [r for r in rows if r.get("company_name") == company_name]
            return matches[0]["overall_score"] if matches else None

        with _patched_auth():
            score_before = _score_in_rankings()
            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/actions/{created['id']}", json={"status": "completed"}, headers=_auth_headers(USER_A))
            score_after = _score_in_rankings()
        expect(score_before == score_after, f"Rankings score must be unchanged, before={score_before} after={score_after}")
    finally:
        _cleanup()


# --- 24-25: re-analysis preserves history ---------------------------------------


def test_reanalysis_does_not_delete_existing_actions() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ReanalysisPreserves")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "Keep me"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/actions/{created['id']}", json={"status": "in_progress"}, headers=_auth_headers(USER_A))

            with patched_pipeline():
                reanalyze = client.post(
                    "/analyze",
                    data={"company_text": "updated info", "startup_id": str(startup_id)},
                    headers=_auth_headers(USER_A),
                )
            expect(reanalyze.status_code == 200, f"Re-analysis failed: {reanalyze.text}")

            listing = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A)).json()
        matches = [row for row in listing if row["id"] == created["id"]]
        expect(len(matches) == 1, "The pre-existing action must still exist after re-analysis")
        expect(matches[0]["status"] == "in_progress", "Its status must be untouched by re-analysis")
    finally:
        _cleanup()


def test_new_recommendations_after_reanalysis_do_not_destroy_history() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NewRecsPreserveHistory")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            old = client.post(
                f"/founder/startups/{startup_id}/actions",
                json={"title": "Old recommendation no longer surfaced", "related_pillar": "team", "source": "sie_recommendation"},
                headers=_auth_headers(USER_A),
            ).json()

            with patched_pipeline():
                client.post(
                    "/analyze",
                    data={"company_text": "updated info", "startup_id": str(startup_id)},
                    headers=_auth_headers(USER_A),
                )

            new = client.post(
                f"/founder/startups/{startup_id}/actions",
                json={"title": "Brand new recommendation from latest analysis", "related_pillar": "traction", "source": "sie_recommendation"},
                headers=_auth_headers(USER_A),
            ).json()

            listing = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A)).json()
        ids = {row["id"] for row in listing}
        expect(old["id"] in ids, "The old recommendation-turned-action must survive re-analysis")
        expect(new["id"] in ids, "A new post-re-analysis recommendation must be addable")
        expect(len(listing) == 2, f"Expected exactly 2 actions total, got {len(listing)}")
    finally:
        _cleanup()


# --- 26: unanalyzed startup ------------------------------------------------------


def test_unanalyzed_startup_supports_founder_created_actions() -> None:
    _ensure_test_users()
    startup_id = _make_unanalyzed_startup("NeverAnalyzedActions")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(
                f"/founder/startups/{startup_id}/actions",
                json={"title": "Talk to potential customers before the first analysis"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Founder-created actions must work with zero canonical analyses: {response.text}")
        expect(response.json()["status"] == "todo", "New action must start as todo")
    finally:
        _cleanup()


# --- 28: existing Founder Workspace behavior remains functional ----------------


def test_existing_founder_workspace_endpoint_still_works() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("WorkspaceStillWorks")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["methodology"] is not None, "Existing workspace response shape must be unaffected")
    finally:
        _cleanup()


# --- 29-30: static audits --------------------------------------------------------


def test_no_new_membership_write_path() -> None:
    import pathlib
    import re

    app_dir = pathlib.Path(__file__).resolve().parent.parent
    insert_pattern = re.compile(r"INSERT\s+INTO\s+startup_memberships", re.IGNORECASE)
    def_pattern = re.compile(r"^\s*def\s+(\w+)\s*\(")

    matches: list[tuple[pathlib.Path, int, str]] = []
    for path in app_dir.rglob("*.py"):
        if "tests" in path.parts:
            continue
        lines = path.read_text().splitlines()
        for line_number, line in enumerate(lines, start=1):
            match = insert_pattern.search(line)
            if match and "#" in line[: match.start()]:
                continue
            if match:
                enclosing_function = "<module level>"
                for prior_line in reversed(lines[:line_number - 1]):
                    def_match = def_pattern.match(prior_line)
                    if def_match:
                        enclosing_function = def_match.group(1)
                        break
                matches.append((path, line_number, enclosing_function))

    locations = [f"{path.name}:{line_number} (in {fn})" for path, line_number, fn in matches]
    expect(len(matches) == 1, f"Expected exactly one INSERT INTO startup_memberships, found {len(matches)}: {locations}")
    expect(
        matches[0][0].name == "db.py" and matches[0][2] == "approve_startup_claim",
        f"The one INSERT must still live inside db.py's approve_startup_claim(); found {locations}",
    )


def test_no_scoring_or_vps_files_reference_founder_actions() -> None:
    """Static audit: nothing in the scoring/methodology/VPS surface may
    even mention founder_actions -- if it did, that alone would suggest
    an accidental coupling between workflow state and evidence-based
    scoring."""
    import pathlib

    app_dir = pathlib.Path(__file__).resolve().parent.parent
    scoring_files = [
        app_dir / "ai" / "scoring.py",
        app_dir / "ai" / "scorecard.py",
        app_dir / "ai" / "investment_score.py",
        app_dir / "ai" / "vps_scoring.py",
        app_dir / "ai" / "readiness_score.py",
        app_dir / "ai" / "sie_v2_methodology.py",
        app_dir / "ai" / "scoring_methodology.py",
        app_dir / "ai" / "analyze_pillar.py",
        app_dir / "workflows" / "sie_assembler.py",
        app_dir / "workflows" / "due_diligence_workflow.py",
    ]

    offenders = []
    for path in scoring_files:
        if not path.exists():
            continue
        if "founder_action" in path.read_text().lower():
            offenders.append(str(path))

    expect(len(offenders) == 0, f"No scoring/methodology/VPS file may reference founder_actions, found: {offenders}")


TESTS = [
    test_member_can_list_actions,
    test_non_member_cannot_list_actions,
    test_signed_out_cannot_list_actions,
    test_member_can_create_founder_action,
    test_client_cannot_spoof_created_by_user_id,
    test_member_can_add_sie_recommendation,
    test_recommendation_provenance_preserved,
    test_duplicate_sie_recommendation_does_not_spam,
    test_founder_created_duplicates_are_not_deduplicated,
    test_todo_to_in_progress,
    test_in_progress_to_completed,
    test_completed_at_set_correctly,
    test_completed_item_can_be_reopened,
    test_dismiss_behavior,
    test_user_cannot_mutate_another_startups_action,
    test_membership_removal_immediately_removes_access,
    test_saved_startup_does_not_authorize_actions,
    test_pending_claim_does_not_authorize_actions,
    test_approved_claim_without_membership_does_not_authorize_actions,
    test_modeled_venture_does_not_authorize_actions,
    test_two_members_of_same_startup_see_same_plan,
    test_cross_startup_isolation_for_listing,
    test_founder_created_action_does_not_affect_sps,
    test_completing_action_does_not_affect_sps,
    test_completing_action_does_not_affect_methodology_jsonb,
    test_completing_action_does_not_affect_rankings,
    test_reanalysis_does_not_delete_existing_actions,
    test_new_recommendations_after_reanalysis_do_not_destroy_history,
    test_unanalyzed_startup_supports_founder_created_actions,
    test_existing_founder_workspace_endpoint_still_works,
    test_no_new_membership_write_path,
    test_no_scoring_or_vps_files_reference_founder_actions,
]


def main() -> None:
    print("\nPhase 7.3 -- Founder Progress & Improvement V1 tests")
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
