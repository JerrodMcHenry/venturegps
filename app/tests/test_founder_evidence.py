"""
Regression tests for Phase 7.4 -- Founder Evidence + Milestones V1:
app/database/db.py's founder_updates/startup_milestones functions, and
the GET/POST/PATCH .../updates and .../milestones endpoints in
app/api.py (all gated by app/auth.py's RequireStartupMember, exactly
like Phase 7.2/7.3's other founder-scoped endpoints).

Reuses the exact same local-RSA-keypair JWT-mocking harness as
test_founder_actions.py/test_founder_workspace.py (no live Clerk
dependency). Every row here uses a distinctive zztest_evidence_* user-id
prefix and a "ZZTest Evidence" company-name prefix, cleaned up in a
finally block even on failure. No test here makes a real LLM/Tavily call
(the two re-analysis tests reuse test_founder_reanalysis.py's
patched-pipeline technique).

Central thesis under test: founder_updates and startup_milestones are
pure founder-REPORTED record. Nothing in this file ever asserts a
*_score, methodology, or startup_memberships change as a RESULT of
recording an update or achieving a milestone -- several tests below
assert the opposite (no change), which is the actual point.

Run with:
    python -m app.tests.test_founder_evidence
"""

import time
from contextlib import contextmanager
from datetime import datetime

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

USER_A = "zztest_evidence_user_a"
USER_B = "zztest_evidence_user_b"
ADMIN_USER = "zztest_evidence_admin"
ALL_USERS = [USER_A, USER_B, ADMIN_USER]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_PREFIX = "ZZTest Evidence"

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


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# --- Fast, LLM-free fake pipeline (reused for the two re-analysis tests) ----


@contextmanager
def patched_pipeline(extracted_company_name: str = "ZZTest Evidence Extracted Variant"):
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
                DELETE FROM founder_updates
                WHERE created_by_user_id = ANY(:ids)
                   OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
            """),
            {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("""
                DELETE FROM startup_milestones
                WHERE created_by_user_id = ANY(:ids)
                   OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
            """),
            {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"},
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


def _update_body(**overrides) -> dict:
    body = {
        "update_type": "revenue",
        "title": "MRR reached $25,000",
        "occurred_at": _iso(datetime(2026, 8, 20, 12, 0, 0)),
    }
    body.update(overrides)
    return body


# =============================================================================
# FOUNDER UPDATES
# =============================================================================


def test_member_can_list_updates() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MemberListUpdates")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json() == [], "Expected an honest empty list for a fresh startup")
    finally:
        _cleanup()


def test_signed_out_cannot_list_updates() -> None:
    startup_id = _make_analyzed_startup("SignedOutUpdates")
    try:
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/updates")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")
    finally:
        _cleanup()


def test_non_member_cannot_list_updates() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NonMemberUpdates")
    try:
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_member_can_create_update() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("CreateUpdate")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(
                f"/founder/startups/{startup_id}/updates",
                json=_update_body(),
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        body = response.json()
        expect(body["title"] == "MRR reached $25,000", "Title must match")
        expect(body["update_type"] == "revenue", "update_type must match")
    finally:
        _cleanup()


def test_client_cannot_spoof_created_by_user_id_on_update() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SpoofUpdateCreator")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(
                f"/founder/startups/{startup_id}/updates",
                json=_update_body(created_by_user_id=USER_B),
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(
            response.json()["created_by_user_id"] == USER_A,
            f"created_by_user_id must be the real caller, got {response.json()['created_by_user_id']!r}",
        )
    finally:
        _cleanup()


def test_founder_reported_provenance_preserved() -> None:
    """No dedicated 'verified' field exists on FounderUpdate at all --
    that IS the provenance signal (see app/models/founder_update.py's
    own docstring): the absence of a verification concept is what keeps
    this from ever being confused with canonical Evidence."""
    _ensure_test_users()
    startup_id = _make_analyzed_startup("Provenance")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(
                f"/founder/startups/{startup_id}/updates",
                json=_update_body(title="Signed 5 paying customers", update_type="customer"),
                headers=_auth_headers(USER_A),
            )
        body = response.json()
        expect("verified" not in body, "FounderUpdate must carry no verification field")
        expect("confidence" not in body, "FounderUpdate must carry no confidence field")
        expect(body["created_by_user_id"] == USER_A, "Attribution must be the real reporting user")
    finally:
        _cleanup()


def test_member_can_edit_update() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("EditUpdate")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(), headers=_auth_headers(USER_A)).json()
            response = client.patch(
                f"/founder/startups/{startup_id}/updates/{created['id']}",
                json=_update_body(title="MRR reached $26,000 (corrected)"),
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["title"] == "MRR reached $26,000 (corrected)", "Edit must apply")
    finally:
        _cleanup()


def test_cross_startup_update_mutation_denied() -> None:
    _ensure_test_users()
    startup_a = _make_analyzed_startup("CrossUpdateA")
    startup_b = _make_analyzed_startup("CrossUpdateB")
    try:
        _grant_membership(USER_A, startup_a)
        _grant_membership(USER_B, startup_b)
        with _patched_auth():
            created_on_b = client.post(f"/founder/startups/{startup_b}/updates", json=_update_body(), headers=_auth_headers(USER_B)).json()
            response = client.patch(
                f"/founder/startups/{startup_a}/updates/{created_on_b['id']}",
                json=_update_body(title="hijacked"),
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_two_members_see_same_updates() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SharedUpdates")
    try:
        _grant_membership(USER_A, startup_id)
        _grant_membership(USER_B, startup_id)
        with _patched_auth():
            client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(title="From A"), headers=_auth_headers(USER_A))
            client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(title="From B"), headers=_auth_headers(USER_B))
            listing_a = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_A)).json()
            listing_b = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_B)).json()
        titles_a = sorted(row["title"] for row in listing_a)
        titles_b = sorted(row["title"] for row in listing_b)
        expect(titles_a == ["From A", "From B"], f"Both must see the shared updates, got {titles_a}")
        expect(titles_a == titles_b, "Both members must see the exact same updates")
    finally:
        _cleanup()


def test_membership_removal_immediately_removes_update_access() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("RemovalUpdates")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            still_member = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_A))
        expect(still_member.status_code == 200, "Sanity: must start out authorized")

        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM startup_memberships WHERE user_id = :u AND startup_id = :s"),
                {"u": USER_A, "s": startup_id},
            )

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404 immediately after removal, got {response.status_code}")
    finally:
        _cleanup()


def test_saved_startup_does_not_authorize_updates() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SavedNotUpdates")
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_pending_claim_does_not_authorize_updates() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("PendingNotUpdates")
    try:
        with _patched_auth(admin_ids=[ADMIN_USER]):
            client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            response = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_approved_claim_without_membership_does_not_authorize_updates() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ApprovedNotUpdates")
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
            response = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


# =============================================================================
# STARTUP MILESTONES
# =============================================================================


def test_member_can_list_milestones() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MemberListMilestones")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/milestones", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json() == [], "Expected an honest empty list")
    finally:
        _cleanup()


def test_member_can_create_milestone() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("CreateMilestone")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(
                f"/founder/startups/{startup_id}/milestones",
                json={"title": "Reach $50K MRR", "related_pillar": "financial_health"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        body = response.json()
        expect(body["title"] == "Reach $50K MRR", "Title must match")
        expect(body["status"] == "planned", "New milestones must start planned")
    finally:
        _cleanup()


def test_milestone_planned_to_in_progress() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MilestoneInProgress")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            response = client.patch(
                f"/founder/startups/{startup_id}/milestones/{created['id']}",
                json={"status": "in_progress"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["status"] == "in_progress", "Status must update")
    finally:
        _cleanup()


def test_milestone_in_progress_to_achieved() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MilestoneAchieved")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{created['id']}", json={"status": "in_progress"}, headers=_auth_headers(USER_A))
            response = client.patch(
                f"/founder/startups/{startup_id}/milestones/{created['id']}",
                json={"status": "achieved"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["status"] == "achieved", "Status must update")
    finally:
        _cleanup()


def test_milestone_completed_at_set_correctly() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MilestoneCompletedAt")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            expect(created["completed_at"] is None, "completed_at must start unset")
            response = client.patch(
                f"/founder/startups/{startup_id}/milestones/{created['id']}",
                json={"status": "achieved"},
                headers=_auth_headers(USER_A),
            )
        expect(response.json()["completed_at"] is not None, "completed_at must be set on achievement")
    finally:
        _cleanup()


def test_achieved_milestone_can_be_reopened() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MilestoneReopen")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{created['id']}", json={"status": "achieved"}, headers=_auth_headers(USER_A))
            reopened = client.patch(
                f"/founder/startups/{startup_id}/milestones/{created['id']}",
                json={"status": "planned"},
                headers=_auth_headers(USER_A),
            )
        expect(reopened.status_code == 200, f"Expected 200: {reopened.text}")
        expect(reopened.json()["status"] == "planned", "Status must revert")
        expect(reopened.json()["completed_at"] is None, "completed_at must clear on reopen")
    finally:
        _cleanup()


def test_milestone_cancelled_behavior() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MilestoneCancel")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            response = client.patch(
                f"/founder/startups/{startup_id}/milestones/{created['id']}",
                json={"status": "cancelled"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["status"] == "cancelled", "Status must update to cancelled")
        expect(response.json()["completed_at"] is None, "cancelled must not set completed_at")
    finally:
        _cleanup()


def test_cross_startup_milestone_mutation_denied() -> None:
    _ensure_test_users()
    startup_a = _make_analyzed_startup("CrossMilestoneA")
    startup_b = _make_analyzed_startup("CrossMilestoneB")
    try:
        _grant_membership(USER_A, startup_a)
        _grant_membership(USER_B, startup_b)
        with _patched_auth():
            created_on_b = client.post(f"/founder/startups/{startup_b}/milestones", json={"title": "x"}, headers=_auth_headers(USER_B)).json()
            response = client.patch(
                f"/founder/startups/{startup_a}/milestones/{created_on_b['id']}",
                json={"status": "achieved"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_two_members_see_same_milestones() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SharedMilestones")
    try:
        _grant_membership(USER_A, startup_id)
        _grant_membership(USER_B, startup_id)
        with _patched_auth():
            client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "From A"}, headers=_auth_headers(USER_A))
            client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "From B"}, headers=_auth_headers(USER_B))
            listing_a = client.get(f"/founder/startups/{startup_id}/milestones", headers=_auth_headers(USER_A)).json()
            listing_b = client.get(f"/founder/startups/{startup_id}/milestones", headers=_auth_headers(USER_B)).json()
        titles_a = sorted(row["title"] for row in listing_a)
        titles_b = sorted(row["title"] for row in listing_b)
        expect(titles_a == ["From A", "From B"], f"Both must see shared milestones, got {titles_a}")
        expect(titles_a == titles_b, "Both members must see the exact same milestones")
    finally:
        _cleanup()


# =============================================================================
# 23-24: unanalyzed startup
# =============================================================================


def test_unanalyzed_startup_supports_milestones() -> None:
    _ensure_test_users()
    startup_id = _make_unanalyzed_startup("UnanalyzedMilestone")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Milestones must work with zero canonical analyses: {response.text}")
    finally:
        _cleanup()


def test_unanalyzed_startup_supports_updates() -> None:
    _ensure_test_users()
    startup_id = _make_unanalyzed_startup("UnanalyzedUpdate")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(), headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Updates must work with zero canonical analyses: {response.text}")
    finally:
        _cleanup()


# =============================================================================
# 25-32: SPS / methodology / rankings / discovery / memberships firewall
# =============================================================================


def _sps_and_methodology(startup_id: int):
    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT methodology->>'startup_intelligence_score' AS sps, methodology::text AS m FROM analyses WHERE startup_id=:s"),
            {"s": startup_id},
        ).mappings().first()
        return row["sps"], row["m"]


def test_creating_update_does_not_change_sps() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoSpsFromUpdateCreate")
    try:
        _grant_membership(USER_A, startup_id)
        sps_before, _ = _sps_and_methodology(startup_id)
        with _patched_auth():
            client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(), headers=_auth_headers(USER_A))
        sps_after, _ = _sps_and_methodology(startup_id)
        expect(sps_before == sps_after, f"SPS must be unchanged, before={sps_before} after={sps_after}")
    finally:
        _cleanup()


def test_editing_update_does_not_change_sps() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoSpsFromUpdateEdit")
    try:
        _grant_membership(USER_A, startup_id)
        sps_before, _ = _sps_and_methodology(startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(), headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/updates/{created['id']}", json=_update_body(title="edited"), headers=_auth_headers(USER_A))
        sps_after, _ = _sps_and_methodology(startup_id)
        expect(sps_before == sps_after, f"SPS must be unchanged, before={sps_before} after={sps_after}")
    finally:
        _cleanup()


def test_achieving_milestone_does_not_change_sps() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoSpsFromMilestone")
    try:
        _grant_membership(USER_A, startup_id)
        sps_before, _ = _sps_and_methodology(startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "Reach $50K MRR"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{created['id']}", json={"status": "achieved"}, headers=_auth_headers(USER_A))
        sps_after, _ = _sps_and_methodology(startup_id)
        expect(sps_before == sps_after, f"SPS must be unchanged, before={sps_before} after={sps_after}")
    finally:
        _cleanup()


def test_creating_update_does_not_modify_methodology_jsonb() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoMethodologyFromUpdate")
    try:
        _grant_membership(USER_A, startup_id)
        _, methodology_before = _sps_and_methodology(startup_id)
        with _patched_auth():
            client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(), headers=_auth_headers(USER_A))
        _, methodology_after = _sps_and_methodology(startup_id)
        expect(methodology_before == methodology_after, "methodology JSONB must be byte-for-byte unchanged")
    finally:
        _cleanup()


def test_achieving_milestone_does_not_modify_methodology_jsonb() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoMethodologyFromMilestone")
    try:
        _grant_membership(USER_A, startup_id)
        _, methodology_before = _sps_and_methodology(startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{created['id']}", json={"status": "achieved"}, headers=_auth_headers(USER_A))
        _, methodology_after = _sps_and_methodology(startup_id)
        expect(methodology_before == methodology_after, "methodology JSONB must be byte-for-byte unchanged")
    finally:
        _cleanup()


def test_rankings_unchanged() -> None:
    # Task 33 item 15: GET /rankings requires auth since a prior
    # security-hardening phase -- `_score()` below now authenticates its
    # own read, same as every other call in this test already does. See
    # test_founder_actions.py::test_completing_action_does_not_affect_
    # rankings for the identical fix and full rationale.
    _ensure_test_users()
    startup_id = _make_analyzed_startup("RankingsUnchanged")
    try:
        _grant_membership(USER_A, startup_id)
        company_name = f"{TEST_PREFIX} RankingsUnchanged"

        def _score():
            rows = client.get("/rankings", headers=_auth_headers(USER_A)).json()
            matches = [r for r in rows if r.get("company_name") == company_name]
            return matches[0]["overall_score"] if matches else None

        with _patched_auth():
            before = _score()
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{created['id']}", json={"status": "achieved"}, headers=_auth_headers(USER_A))
            client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(), headers=_auth_headers(USER_A))
            after = _score()
        expect(before == after, f"Rankings score must be unchanged, before={before} after={after}")
    finally:
        _cleanup()


def test_discovery_unchanged() -> None:
    # Task 33 item 15: GET /discover also requires RequireAuth (same
    # security-hardening phase as /rankings) -- same fix as
    # test_rankings_unchanged above.
    _ensure_test_users()
    startup_id = _make_analyzed_startup("DiscoveryUnchanged")
    try:
        _grant_membership(USER_A, startup_id)
        company_name = f"{TEST_PREFIX} DiscoveryUnchanged"

        def _score():
            rows = client.get("/discover", params={"query": company_name}, headers=_auth_headers(USER_A)).json()["results"]
            matches = [r for r in rows if r.get("company_name") == company_name]
            return matches[0]["overall_score"] if matches else None

        with _patched_auth():
            before = _score()
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{created['id']}", json={"status": "achieved"}, headers=_auth_headers(USER_A))
            after = _score()
        expect(before == after, f"Discovery score must be unchanged, before={before} after={after}")
    finally:
        _cleanup()


def test_startup_memberships_unchanged_by_evidence_activity() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MembershipsUnchanged")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            before = connection.execute(text("SELECT count(*) FROM startup_memberships")).scalar()
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{created['id']}", json={"status": "achieved"}, headers=_auth_headers(USER_A))
            client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(), headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT count(*) FROM startup_memberships")).scalar()
        expect(before == after, f"startup_memberships must be unchanged, before={before} after={after}")
    finally:
        _cleanup()


# =============================================================================
# 33-36: re-analysis preserves history; existing actions unaffected
# =============================================================================


def test_reanalysis_does_not_delete_updates() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ReanalysisKeepsUpdates")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(title="Keep me"), headers=_auth_headers(USER_A)).json()
            with patched_pipeline():
                reanalyze = client.post(
                    "/analyze",
                    data={"company_text": "updated info", "startup_id": str(startup_id)},
                    headers=_auth_headers(USER_A),
                )
            expect(reanalyze.status_code == 200, f"Re-analysis failed: {reanalyze.text}")
            listing = client.get(f"/founder/startups/{startup_id}/updates", headers=_auth_headers(USER_A)).json()
        expect(any(row["id"] == created["id"] for row in listing), "The pre-existing update must survive re-analysis")
    finally:
        _cleanup()


def test_reanalysis_does_not_delete_milestones() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ReanalysisKeepsMilestones")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "Keep me"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{created['id']}", json={"status": "in_progress"}, headers=_auth_headers(USER_A))
            with patched_pipeline():
                reanalyze = client.post(
                    "/analyze",
                    data={"company_text": "updated info", "startup_id": str(startup_id)},
                    headers=_auth_headers(USER_A),
                )
            expect(reanalyze.status_code == 200, f"Re-analysis failed: {reanalyze.text}")
            listing = client.get(f"/founder/startups/{startup_id}/milestones", headers=_auth_headers(USER_A)).json()
        matches = [row for row in listing if row["id"] == created["id"]]
        expect(len(matches) == 1, "The pre-existing milestone must survive re-analysis")
        expect(matches[0]["status"] == "in_progress", "Its status must be untouched by re-analysis")
    finally:
        _cleanup()


def test_existing_founder_actions_remain_unchanged() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ActionsUnaffected")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            action = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "Existing action"}, headers=_auth_headers(USER_A)).json()

            client.post(f"/founder/startups/{startup_id}/updates", json=_update_body(), headers=_auth_headers(USER_A))
            milestone = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{milestone['id']}", json={"status": "achieved"}, headers=_auth_headers(USER_A))

            listing = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A)).json()
        matches = [row for row in listing if row["id"] == action["id"]]
        expect(len(matches) == 1, "The pre-existing founder action must be unaffected by evidence/milestone activity")
        expect(matches[0]["status"] == "todo", "Its status must be untouched")
    finally:
        _cleanup()


# =============================================================================
# 36-37: static audits
# =============================================================================


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


def test_no_scoring_or_vps_files_reference_founder_evidence() -> None:
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
        content = path.read_text().lower()
        if "founder_update" in content or "startup_milestone" in content:
            offenders.append(str(path))

    expect(len(offenders) == 0, f"No scoring/methodology/VPS file may reference founder_updates/startup_milestones, found: {offenders}")


TESTS = [
    test_member_can_list_updates,
    test_signed_out_cannot_list_updates,
    test_non_member_cannot_list_updates,
    test_member_can_create_update,
    test_client_cannot_spoof_created_by_user_id_on_update,
    test_founder_reported_provenance_preserved,
    test_member_can_edit_update,
    test_cross_startup_update_mutation_denied,
    test_two_members_see_same_updates,
    test_membership_removal_immediately_removes_update_access,
    test_saved_startup_does_not_authorize_updates,
    test_pending_claim_does_not_authorize_updates,
    test_approved_claim_without_membership_does_not_authorize_updates,
    test_member_can_list_milestones,
    test_member_can_create_milestone,
    test_milestone_planned_to_in_progress,
    test_milestone_in_progress_to_achieved,
    test_milestone_completed_at_set_correctly,
    test_achieved_milestone_can_be_reopened,
    test_milestone_cancelled_behavior,
    test_cross_startup_milestone_mutation_denied,
    test_two_members_see_same_milestones,
    test_unanalyzed_startup_supports_milestones,
    test_unanalyzed_startup_supports_updates,
    test_creating_update_does_not_change_sps,
    test_editing_update_does_not_change_sps,
    test_achieving_milestone_does_not_change_sps,
    test_creating_update_does_not_modify_methodology_jsonb,
    test_achieving_milestone_does_not_modify_methodology_jsonb,
    test_rankings_unchanged,
    test_discovery_unchanged,
    test_startup_memberships_unchanged_by_evidence_activity,
    test_reanalysis_does_not_delete_updates,
    test_reanalysis_does_not_delete_milestones,
    test_existing_founder_actions_remain_unchanged,
    test_no_new_membership_write_path,
    test_no_scoring_or_vps_files_reference_founder_evidence,
]


def main() -> None:
    print("\nPhase 7.4 -- Founder Evidence + Milestones V1 tests")
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
