"""
Regression tests for Phase 8 -- Fundraising Readiness V1:
app/ai/fundraising_readiness.py's deterministic assessment logic, and the
GET /founder/startups/{startup_id}/fundraising endpoint in app/api.py
(gated by app/auth.py's RequireStartupMember, exactly like every other
Founder Workspace endpoint), plus the founder_actions source='fundraising_gap'
Action Plan integration.

Reuses the exact same local-RSA-keypair JWT-mocking harness as
test_founder_evidence.py/test_founder_actions.py (no live Clerk
dependency). Every row here uses a distinctive zztest_readiness_* user-id
prefix and a "ZZTest Readiness" company-name prefix, cleaned up in a
finally block even on failure. No test here makes a real LLM/Tavily call.

Central thesis under test: Fundraising Readiness is a separate,
deterministic assessment -- never SPS, never written anywhere SPS is
read from (Rankings/Discovery/Compare/SPS history), and never influenced
by founder_actions/startup_milestones/founder_updates completion state.

Run with:
    python -m app.tests.test_fundraising_readiness
"""

import time
from contextlib import contextmanager

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.ai.fundraising_readiness import (
    PILLAR_KEYS,
    PillarReadinessInput,
    assess_fundraising_readiness,
    compute_pillar_readiness,
    normalize_stage,
    resolve_stage_weights,
)
from app.database.db import (
    engine,
    get_or_create_startup,
    save_analysis,
    save_startup_for_user,
    create_modeled_venture,
)

USER_A = "zztest_readiness_user_a"
USER_B = "zztest_readiness_user_b"
ADMIN_USER = "zztest_readiness_admin"
ALL_USERS = [USER_A, USER_B, ADMIN_USER]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
TEST_PREFIX = "ZZTest Readiness"

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


@contextmanager
def patched_pipeline(extracted_company_name: str = "ZZTest Readiness Extracted Variant"):
    from app.ai.sie_v2_methodology import METHODOLOGY_VERSION
    from app.workflows.due_diligence_workflow import build_sie_methodology_analysis
    from app.models.analysis import (
        ExecutionAnalysisResult, FinancialAnalysisResult, FounderAnalysisResult,
        MarketAnalysisResult, ProductAnalysisResult, TractionAnalysisResult,
    )

    def fake_run_due_diligence(company_text, analysis_type="public", evidence_sources=None):
        sie_analysis = build_sie_methodology_analysis(
            structured_analysis={"company_name": extracted_company_name, "industry": "SaaS", "business_model": "SaaS"},
            readiness=None,
            founder_analysis=FounderAnalysisResult(), market_analysis=MarketAnalysisResult(),
            product_analysis=ProductAnalysisResult(), execution_analysis=ExecutionAnalysisResult(),
            traction_analysis=TractionAnalysisResult(), financial_analysis=FinancialAnalysisResult(),
            analysis_type=analysis_type, evidence_sources=evidence_sources,
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


def _canonical_methodology(sps: float = 50.0, stage: str = "Seed") -> dict:
    from app.ai.sie_v2_methodology import METHODOLOGY_VERSION

    return {
        "startup_intelligence_score": sps,
        "context": {"company_stage": stage, "funding_stage": stage},
        "analysis_context": {"methodology_version": METHODOLOGY_VERSION, "evidence_sources": ["company_description"], "analysis_type": "public"},
        "market": {"score": 7.0, "confidence": "Medium", "score_breakdown": {"evidence_coverage": 60}, "strengths": ["Clear TAM"], "weaknesses": []},
        "team": {"score": 7.0, "confidence": "Medium", "score_breakdown": {"evidence_coverage": 60}, "strengths": [], "weaknesses": []},
        "product": {"score": 7.0, "confidence": "Medium", "score_breakdown": {"evidence_coverage": 60}, "strengths": [], "weaknesses": []},
        "execution": {"score": 7.0, "confidence": "Medium", "score_breakdown": {"evidence_coverage": 60}, "strengths": [], "weaknesses": []},
        "traction": {"score": 7.0, "confidence": "Medium", "score_breakdown": {"evidence_coverage": 60}, "strengths": [], "weaknesses": []},
        "financial_health": {"score": 7.0, "confidence": "Medium", "score_breakdown": {"evidence_coverage": 60}, "strengths": [], "weaknesses": []},
    }


def _make_analyzed_startup(name_suffix: str, stage: str = "Seed") -> int:
    company_name = f"{TEST_PREFIX} {name_suffix}"
    save_analysis(
        company_text=f"Original text for {company_name}",
        summary="s", risk_analysis="r", competitor_analysis="c", memo="m",
        structured_analysis={"company_name": company_name, "industry": "SaaS", "stage": stage, "business_model": "SaaS"},
        investment_score={}, founder_analysis={}, market_analysis={}, sources=[], traction_analysis={},
        market_score=None, team_score=None, product_score=None, competition_score=None,
        traction_score=None, financial_score=None, overall_score=None, recommendation=None,
        readiness_score=None, readiness_summary=None,
        methodology=_canonical_methodology(stage=stage),
    )
    return get_or_create_startup(company_name)


def _make_unanalyzed_startup(name_suffix: str) -> int:
    return get_or_create_startup(f"{TEST_PREFIX} {name_suffix}")


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in ALL_USERS:
            connection.execute(text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"), {"id": user_id})


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
        connection.execute(text("DELETE FROM analysis_runs WHERE user_id = ANY(:ids)"), {"ids": ALL_USERS})
        connection.execute(text("""
            DELETE FROM founder_actions
            WHERE created_by_user_id = ANY(:ids) OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
        """), {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("""
            DELETE FROM startup_milestones
            WHERE created_by_user_id = ANY(:ids) OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
        """), {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("""
            DELETE FROM founder_updates
            WHERE created_by_user_id = ANY(:ids) OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
        """), {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("""
            DELETE FROM startup_memberships
            WHERE user_id = ANY(:ids) OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
        """), {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("""
            DELETE FROM startup_claims
            WHERE user_id = ANY(:ids) OR startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern)
        """), {"ids": ALL_USERS, "pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("DELETE FROM saved_startups WHERE user_id = ANY(:ids)"), {"ids": ALL_USERS})
        connection.execute(text("DELETE FROM modeled_ventures WHERE user_id = ANY(:ids)"), {"ids": ALL_USERS})
        connection.execute(text("""
            DELETE FROM analyses
            WHERE startup_id IN (SELECT id FROM startups WHERE normalized_name LIKE :pattern) OR company_name ILIKE :pattern2
        """), {"pattern": f"{TEST_PREFIX.lower()}%", "pattern2": f"{TEST_PREFIX}%"})
        connection.execute(text("DELETE FROM startups WHERE normalized_name LIKE :pattern"), {"pattern": f"{TEST_PREFIX.lower()}%"})
        connection.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ALL_USERS})


# --- 1-8: authorization -----------------------------------------------------


def test_member_can_access_readiness() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("MemberAccess")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["has_canonical_analysis"] is True, "Must reflect real canonical analysis")
    finally:
        _cleanup()


def test_signed_out_denied() -> None:
    startup_id = _make_analyzed_startup("SignedOutDenied")
    try:
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising")
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")
    finally:
        _cleanup()


def test_non_member_denied() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NonMemberDenied")
    try:
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_membership_removal_immediately_denies() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("RemovalDenies")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            still_ok = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        expect(still_ok.status_code == 200, "Sanity: must start authorized")

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM startup_memberships WHERE user_id = :u AND startup_id = :s"), {"u": USER_A, "s": startup_id})

        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404 immediately after removal, got {response.status_code}")
    finally:
        _cleanup()


def test_saved_startup_does_not_authorize() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("SavedNotAuthorized")
    try:
        save_startup_for_user(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_pending_claim_does_not_authorize() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("PendingNotAuthorized")
    try:
        with _patched_auth(admin_ids=[ADMIN_USER]):
            client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_approved_claim_without_membership_does_not_authorize() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ApprovedNotAuthorized")
    try:
        with _patched_auth(admin_ids=[ADMIN_USER]):
            submitted = client.post("/startup-claims", json={"startup_id": startup_id, "justification": "x"}, headers=_auth_headers(USER_A))
            claim_id = submitted.json()["id"]
            client.post(f"/admin/startup-claims/{claim_id}/approve", headers=_auth_headers(ADMIN_USER))
            with engine.begin() as connection:
                connection.execute(text("DELETE FROM startup_memberships WHERE user_id = :u AND startup_id = :s"), {"u": USER_A, "s": startup_id})
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


def test_modeled_venture_does_not_authorize() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("VentureNotAuthorized")
    try:
        create_modeled_venture(
            user_id=USER_A, name="Idea", description=None, industry=None,
            business_model=None, target_customer=None, stage=None,
            assumptions={}, model_result=None,
        )
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, f"Expected 404, got {response.status_code}")
    finally:
        _cleanup()


# --- 9-10: unanalyzed / uses latest analysis ---------------------------------


def test_unanalyzed_startup_gets_no_fabricated_score() -> None:
    _ensure_test_users()
    startup_id = _make_unanalyzed_startup("Unanalyzed")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        body = response.json()
        expect(body["has_canonical_analysis"] is False, "Must honestly report no analysis")
        expect(body["readiness_score"] is None, "Must never fabricate a score")
        expect(body["readiness_band"] is None, "Must never fabricate a band")
    finally:
        _cleanup()


def test_readiness_uses_latest_canonical_analysis() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("LatestAnalysis", stage="Seed")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            first = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()

            with patched_pipeline():
                client.post("/analyze", data={"company_text": "updated", "startup_id": str(startup_id)}, headers=_auth_headers(USER_A))

            second = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()
        expect(second["analyzed_at"] != first["analyzed_at"], "Must reflect the newest analysis, not a stale one")
    finally:
        _cleanup()


# --- 11-20: no side effects, no SPS contamination ----------------------------


def test_readiness_does_not_mutate_canonical_analysis() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoMutation")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            before = connection.execute(text("SELECT methodology::text FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()
        with _patched_auth():
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT methodology::text FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()
        expect(before == after, "Viewing readiness must never mutate the stored methodology")
    finally:
        _cleanup()


def test_readiness_does_not_change_sps() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoSpsChange")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            before = connection.execute(text("SELECT methodology->>'startup_intelligence_score' FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()
        with _patched_auth():
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT methodology->>'startup_intelligence_score' FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()
        expect(before == after, "SPS must be unchanged by viewing readiness")
    finally:
        _cleanup()


def test_readiness_does_not_change_sps_history() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoHistoryChange")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            before = connection.execute(text("SELECT count(*) FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()
        with _patched_auth():
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT count(*) FROM analyses WHERE startup_id=:s"), {"s": startup_id}).scalar()
        expect(before == after, "SPS History (analyses rows) must be unchanged by viewing readiness")
    finally:
        _cleanup()


def test_readiness_does_not_change_rankings() -> None:
    # Task 33 item 15: GET /rankings requires auth since a prior
    # security-hardening phase -- see test_founder_actions.py's own
    # identical fix/rationale.
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoRankingsChange")
    try:
        _grant_membership(USER_A, startup_id)
        company_name = f"{TEST_PREFIX} NoRankingsChange"

        def _score():
            rows = client.get("/rankings", headers=_auth_headers(USER_A)).json()
            matches = [r for r in rows if r.get("company_name") == company_name]
            return matches[0]["overall_score"] if matches else None

        with _patched_auth():
            before = _score()
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
            after = _score()
        expect(before == after, f"Rankings must be unchanged, before={before} after={after}")
    finally:
        _cleanup()


def test_readiness_does_not_change_discovery() -> None:
    # Task 33 item 15: GET /discover also requires auth -- same fix.
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoDiscoveryChange")
    try:
        _grant_membership(USER_A, startup_id)
        company_name = f"{TEST_PREFIX} NoDiscoveryChange"

        def _score():
            rows = client.get("/discover", params={"query": company_name}, headers=_auth_headers(USER_A)).json()["results"]
            matches = [r for r in rows if r.get("company_name") == company_name]
            return matches[0]["overall_score"] if matches else None

        with _patched_auth():
            before = _score()
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
            after = _score()
        expect(before == after, f"Discovery must be unchanged, before={before} after={after}")
    finally:
        _cleanup()


def test_readiness_does_not_change_compare() -> None:
    # Task 33 item 15: GET /compare also requires auth -- same fix.
    _ensure_test_users()
    startup_a = _make_analyzed_startup("CompareA")
    startup_b = _make_analyzed_startup("CompareB")
    try:
        _grant_membership(USER_A, startup_a)
        with _patched_auth():
            before = client.get("/compare", params={"startups": f"{startup_a},{startup_b}"}, headers=_auth_headers(USER_A)).json()
            client.get(f"/founder/startups/{startup_a}/fundraising", headers=_auth_headers(USER_A))
            after = client.get("/compare", params={"startups": f"{startup_a},{startup_b}"}, headers=_auth_headers(USER_A)).json()
        expect(before == after, "Compare output must be unchanged by viewing readiness")
    finally:
        _cleanup()


def test_readiness_does_not_change_vps() -> None:
    """Static-flavored check: Idea Lab/VPS endpoints are entirely
    separate from Fundraising Readiness (Part 19) -- a modeled venture's
    VPS is untouched by any startup's readiness assessment. Verified by
    confirming a venture's VPS is identical before/after viewing
    readiness for an unrelated real startup."""
    _ensure_test_users()
    startup_id = _make_analyzed_startup("VpsUnrelated")
    try:
        _grant_membership(USER_A, startup_id)
        venture_id = create_modeled_venture(
            user_id=USER_A, name="Idea", description=None, industry=None,
            business_model=None, target_customer=None, stage=None,
            assumptions={}, model_result={"vps": 42.0},
        )
        with engine.begin() as connection:
            before = connection.execute(text("SELECT model_result::text FROM modeled_ventures WHERE id=:id"), {"id": venture_id}).scalar()
        with _patched_auth():
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT model_result::text FROM modeled_ventures WHERE id=:id"), {"id": venture_id}).scalar()
        expect(before == after, "VPS/modeled venture data must be unaffected by Fundraising Readiness")
    finally:
        _cleanup()


def test_readiness_does_not_modify_actions_merely_by_viewing() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoActionMutation")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            client.post(f"/founder/startups/{startup_id}/actions", json={"title": "Existing action"}, headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            before = connection.execute(text("SELECT count(*) FROM founder_actions WHERE startup_id=:s"), {"s": startup_id}).scalar()
        with _patched_auth():
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT count(*) FROM founder_actions WHERE startup_id=:s"), {"s": startup_id}).scalar()
        expect(before == after, "Viewing readiness must never create/modify founder_actions rows")
    finally:
        _cleanup()


def test_readiness_does_not_modify_milestones() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoMilestoneMutation")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            before = connection.execute(text("SELECT count(*) FROM startup_milestones WHERE startup_id=:s"), {"s": startup_id}).scalar()
        with _patched_auth():
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT count(*) FROM startup_milestones WHERE startup_id=:s"), {"s": startup_id}).scalar()
        expect(before == after, "Viewing readiness must never create/modify startup_milestones rows")
    finally:
        _cleanup()


def test_readiness_does_not_modify_founder_updates() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoUpdateMutation")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            before = connection.execute(text("SELECT count(*) FROM founder_updates WHERE startup_id=:s"), {"s": startup_id}).scalar()
        with _patched_auth():
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT count(*) FROM founder_updates WHERE startup_id=:s"), {"s": startup_id}).scalar()
        expect(before == after, "Viewing readiness must never create/modify founder_updates rows")
    finally:
        _cleanup()


# --- 21-23: stage awareness --------------------------------------------------


def test_stage_affects_expectations() -> None:
    weights_idea = resolve_stage_weights("Idea")
    weights_growth = resolve_stage_weights("Growth")
    expect(weights_idea["traction"] < weights_growth["traction"], "Traction must matter less at Idea stage than Growth")
    expect(weights_idea["financial_health"] < weights_growth["financial_health"], "Financial preparedness must matter less at Idea stage than Growth")
    expect(weights_idea["market"] > weights_growth["market"], "Market/team narrative must matter more at Idea stage than Growth")


def test_pre_seed_not_penalized_for_later_stage_expectations() -> None:
    """A pre-seed company with zero traction evidence must not generate
    a 'stage-inappropriate' gap for it -- Traction's weight at Idea/
    Pre-Seed is small enough that an Unavailable pillar there is excluded
    from the gap list entirely (see _gap_for_pillar()'s own weight
    threshold)."""
    thin_traction = PillarReadinessInput(score=None, confidence="Low", evidence_coverage=0.0)
    idea_weights = resolve_stage_weights("Idea")
    pillar = compute_pillar_readiness("traction", thin_traction, idea_weights["traction"])
    expect(pillar.readiness_contribution is None, "Unavailable pillar must never get a fabricated contribution")

    from app.ai.fundraising_readiness import _gap_for_pillar
    result = _gap_for_pillar(pillar, "Idea")
    expect(result is None, "A stage-appropriate absence (Traction at Idea stage) must not become a gap")


def test_later_stage_held_to_stronger_evidence_expectations() -> None:
    from app.ai.fundraising_readiness import _gap_for_pillar

    thin_traction = PillarReadinessInput(score=None, confidence="Low", evidence_coverage=0.0)
    growth_weights = resolve_stage_weights("Growth")
    pillar = compute_pillar_readiness("traction", thin_traction, growth_weights["traction"])
    result = _gap_for_pillar(pillar, "Growth")
    expect(result is not None, "Missing Traction evidence at Growth stage must surface as a real gap")


# --- 24-26: epistemic discipline ---------------------------------------------


def test_missing_data_remains_unavailable_not_zero() -> None:
    unavailable = PillarReadinessInput(score=None, confidence="Low", evidence_coverage=0.0)
    pillar = compute_pillar_readiness("market", unavailable, 0.2)
    expect(pillar.readiness_contribution is None, "Missing data must stay None, never a fabricated 0")
    expect(pillar.score is None, "Score must stay None, never a fabricated 0")


def test_missing_pitch_deck_analysis_does_not_become_no_deck_exists() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoDeckLanguage")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        note = response.json()["pitch_deck_note"]
        expect("analyzed" in note.lower(), f"Must be phrased as 'not yet analyzed', got: {note!r}")
        expect("no pitch deck exists" not in note.lower(), "Must never claim a deck doesn't exist")
    finally:
        _cleanup()


def test_founder_updates_not_treated_as_verified_evidence() -> None:
    """Static check: assess_fundraising_readiness() takes only a
    methodology dict -- founder_updates rows are never read by, or
    passed into, this module at all. Confirmed here by recording a
    founder update claiming a large metric and proving the readiness
    assessment (and its pillar evidence_coverage/confidence) is
    unaffected."""
    _ensure_test_users()
    startup_id = _make_analyzed_startup("FounderUpdateNotEvidence")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            before = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()

            client.post(
                f"/founder/startups/{startup_id}/updates",
                json={"update_type": "revenue", "title": "MRR reached $500,000", "occurred_at": "2026-08-26T00:00:00"},
                headers=_auth_headers(USER_A),
            )

            after = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()
        expect(before["readiness_score"] == after["readiness_score"], "A founder-reported update must never silently change the readiness score")
        expect(before["pillar_readiness"] == after["pillar_readiness"], "Pillar-level readiness data must be unaffected by a founder update")
    finally:
        _cleanup()


# --- 27-28: milestone/action completion doesn't improve readiness -----------


def test_completed_actions_do_not_improve_readiness() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("CompletedActionNoEffect")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            before = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()

            created = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/actions/{created['id']}", json={"status": "completed"}, headers=_auth_headers(USER_A))

            after = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()
        expect(before["readiness_score"] == after["readiness_score"], "Completing an action must never change the readiness score")
    finally:
        _cleanup()


def test_achieved_milestones_do_not_improve_readiness() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("AchievedMilestoneNoEffect")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            before = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()

            created = client.post(f"/founder/startups/{startup_id}/milestones", json={"title": "Reach $50K MRR"}, headers=_auth_headers(USER_A)).json()
            client.patch(f"/founder/startups/{startup_id}/milestones/{created['id']}", json={"status": "achieved"}, headers=_auth_headers(USER_A))

            after = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()
        expect(before["readiness_score"] == after["readiness_score"], "Achieving a milestone must never change the readiness score")
    finally:
        _cleanup()


# --- 29-30: investor questions / checklist derivation ------------------------


def test_investor_questions_derive_from_actual_gaps() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("QuestionsFromGaps")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        body = response.json()
        gap_categories = {g["category"] for g in body["gaps"]}
        expect(len(body["gaps"]) > 0, "Sanity: this synthetic startup should have at least one real gap")
        expect(len(body["investor_questions"]) > 0, "Questions must exist when gaps exist")
        expect(len(body["investor_questions"]) <= len(gap_categories) + 1, "Questions must not exceed what the gap categories can support (no invented extras)")
    finally:
        _cleanup()


def test_checklist_derives_from_structured_assessment() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ChecklistFromAssessment")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        checklist = response.json()["checklist"]
        categories = {item["category"] for item in checklist}
        expect("Use of Funds" not in categories, "Must not include a checklist category SIE has no data to assess")
        expect("Pitch Deck Analyzed" in categories, "Must include pitch-deck presence, which SIE can honestly assess")
    finally:
        _cleanup()


# --- 31-32: numeric score determinism / no LLM -------------------------------


def test_deterministic_identical_input_identical_result() -> None:
    methodology = _canonical_methodology(stage="Series A")
    a1 = assess_fundraising_readiness(methodology)
    a2 = assess_fundraising_readiness(methodology)
    expect(a1.readiness_score == a2.readiness_score, "Identical input must produce identical readiness_score")
    expect(a1.readiness_band == a2.readiness_band, "Identical input must produce identical readiness_band")
    expect([g.issue for g in a1.gaps] == [g.issue for g in a2.gaps], "Identical input must produce identical gaps")


def test_no_llm_import_in_fundraising_readiness_module() -> None:
    """Static check: the module must not import an LLM client at all --
    the whole point is that nothing here can be altered by a model call."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent / "ai" / "fundraising_readiness.py").read_text()
    expect("openai" not in source.lower(), "fundraising_readiness.py must never import an LLM client")
    expect("chat.completions" not in source, "fundraising_readiness.py must never call an LLM")


# --- 33-35: static audits -----------------------------------------------------


def test_readiness_never_writes_startup_intelligence_score() -> None:
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent / "ai" / "fundraising_readiness.py").read_text()
    expect("startup_intelligence_score =" not in source, "Module must never assign startup_intelligence_score")
    expect("UPDATE analyses" not in source, "Module must never write to analyses")


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


def test_methodology_v2_scoring_files_unchanged() -> None:
    """Static audit: no Methodology v2/scoring/VPS file may import or
    call the new fundraising_readiness module -- if it did, that alone
    would suggest an accidental coupling back into canonical scoring.

    Checks for the actual module coupling (an import statement or a
    call to assess_fundraising_readiness), not the bare English phrase
    "fundraising readiness" -- scoring_methodology.py already contains
    an unrelated, pre-existing FUNDRAISING_READINESS_NARRATIVE_RUBRIC
    (Methodology v2's own demoted, unscored narrative flag, predating
    Phase 8) that legitimately uses that phrase and must not trip this
    audit."""
    import pathlib

    app_dir = pathlib.Path(__file__).resolve().parent.parent
    scoring_files = [
        app_dir / "ai" / "scoring.py", app_dir / "ai" / "scorecard.py",
        app_dir / "ai" / "investment_score.py", app_dir / "ai" / "vps_scoring.py",
        app_dir / "ai" / "readiness_score.py", app_dir / "ai" / "sie_v2_methodology.py",
        app_dir / "ai" / "scoring_methodology.py", app_dir / "ai" / "analyze_pillar.py",
        app_dir / "workflows" / "sie_assembler.py", app_dir / "workflows" / "due_diligence_workflow.py",
    ]
    coupling_markers = ("import fundraising_readiness", "from app.ai.fundraising_readiness", "assess_fundraising_readiness(")
    offenders = [
        str(p) for p in scoring_files
        if p.exists() and any(marker in p.read_text() for marker in coupling_markers)
    ]
    expect(len(offenders) == 0, f"No scoring/methodology/VPS file may import or call fundraising_readiness, found: {offenders}")


# --- 36-40: existing surfaces remain functional -------------------------------


def test_existing_founder_workspace_remains_functional() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("WorkspaceStillWorks")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.get(f"/founder/startups/{startup_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["methodology"] is not None, "Existing workspace response must be unaffected")
    finally:
        _cleanup()


def test_existing_deterministic_reanalysis_remains_functional() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ReanalysisStillWorks")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth(), patched_pipeline():
            response = client.post("/analyze", data={"company_text": "x", "startup_id": str(startup_id)}, headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
    finally:
        _cleanup()


def test_existing_action_plan_remains_functional() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ActionPlanStillWorks")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            response = client.post(f"/founder/startups/{startup_id}/actions", json={"title": "x"}, headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Expected 200: {response.text}")
    finally:
        _cleanup()


def test_existing_idea_lab_remains_isolated() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.get("/ventures", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, f"Idea Lab must remain fully functional and isolated: {response.text}")
        expect(response.json() == [], "A user with no ventures must see an honest empty list, unaffected by readiness")
    finally:
        _cleanup()


def test_public_startup_profile_remains_unchanged() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("ProfileUnchanged")
    try:
        _grant_membership(USER_A, startup_id)
        name = f"{TEST_PREFIX} ProfileUnchanged"
        before = client.get(f"/startup/{name}").json()
        with _patched_auth():
            client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        after = client.get(f"/startup/{name}").json()
        expect(before == after, "Public Startup Profile must be byte-identical before/after viewing readiness")
    finally:
        _cleanup()


# --- 41-44: Action Plan integration -------------------------------------------


def test_founder_explicitly_adds_readiness_gap() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("AddGap")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            readiness = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()
            expect(len(readiness["gaps"]) > 0, "Sanity: must have at least one real gap")
            gap = readiness["gaps"][0]

            response = client.post(
                f"/founder/startups/{startup_id}/actions",
                json={"title": gap["issue"], "related_pillar": gap["pillar"], "source": "fundraising_gap"},
                headers=_auth_headers(USER_A),
            )
        expect(response.status_code == 200, f"Expected 200: {response.text}")
        expect(response.json()["source"] == "fundraising_gap", "Source must be preserved")
    finally:
        _cleanup()


def test_gap_provenance_preserved() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("GapProvenance")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            readiness = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()
            gap = readiness["gaps"][0]
            created = client.post(
                f"/founder/startups/{startup_id}/actions",
                json={"title": gap["issue"], "related_pillar": gap["pillar"], "source": "fundraising_gap"},
                headers=_auth_headers(USER_A),
            ).json()
            listing = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A)).json()
        matches = [row for row in listing if row["id"] == created["id"]]
        expect(len(matches) == 1 and matches[0]["source"] == "fundraising_gap", "Provenance must survive a round trip through the list endpoint")
    finally:
        _cleanup()


def test_duplicate_gap_add_does_not_spam_duplicates() -> None:
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoGapDuplicates")
    try:
        _grant_membership(USER_A, startup_id)
        with _patched_auth():
            readiness = client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A)).json()
            gap = readiness["gaps"][0]

            for _ in range(4):
                response = client.post(
                    f"/founder/startups/{startup_id}/actions",
                    json={"title": gap["issue"], "related_pillar": gap["pillar"], "source": "fundraising_gap"},
                    headers=_auth_headers(USER_A),
                )
                expect(response.status_code == 200, f"Expected 200: {response.text}")

            listing = client.get(f"/founder/startups/{startup_id}/actions", headers=_auth_headers(USER_A)).json()
        matching = [row for row in listing if row["title"] == gap["issue"] and row["source"] == "fundraising_gap"]
        expect(len(matching) == 1, f"Expected exactly 1 row after 4 identical 'Add to Plan' clicks, got {len(matching)}")
    finally:
        _cleanup()


def test_no_automatic_task_creation_from_gaps() -> None:
    """Merely viewing readiness must never create founder_actions rows on
    its own -- the founder must explicitly choose to add a gap."""
    _ensure_test_users()
    startup_id = _make_analyzed_startup("NoAutoTasks")
    try:
        _grant_membership(USER_A, startup_id)
        with engine.begin() as connection:
            before = connection.execute(text("SELECT count(*) FROM founder_actions WHERE startup_id=:s"), {"s": startup_id}).scalar()
        with _patched_auth():
            for _ in range(3):
                client.get(f"/founder/startups/{startup_id}/fundraising", headers=_auth_headers(USER_A))
        with engine.begin() as connection:
            after = connection.execute(text("SELECT count(*) FROM founder_actions WHERE startup_id=:s"), {"s": startup_id}).scalar()
        expect(before == after == 0, "Viewing readiness (even repeatedly) must never auto-create Action Plan items")
    finally:
        _cleanup()


TESTS = [
    test_member_can_access_readiness,
    test_signed_out_denied,
    test_non_member_denied,
    test_membership_removal_immediately_denies,
    test_saved_startup_does_not_authorize,
    test_pending_claim_does_not_authorize,
    test_approved_claim_without_membership_does_not_authorize,
    test_modeled_venture_does_not_authorize,
    test_unanalyzed_startup_gets_no_fabricated_score,
    test_readiness_uses_latest_canonical_analysis,
    test_readiness_does_not_mutate_canonical_analysis,
    test_readiness_does_not_change_sps,
    test_readiness_does_not_change_sps_history,
    test_readiness_does_not_change_rankings,
    test_readiness_does_not_change_discovery,
    test_readiness_does_not_change_compare,
    test_readiness_does_not_change_vps,
    test_readiness_does_not_modify_actions_merely_by_viewing,
    test_readiness_does_not_modify_milestones,
    test_readiness_does_not_modify_founder_updates,
    test_stage_affects_expectations,
    test_pre_seed_not_penalized_for_later_stage_expectations,
    test_later_stage_held_to_stronger_evidence_expectations,
    test_missing_data_remains_unavailable_not_zero,
    test_missing_pitch_deck_analysis_does_not_become_no_deck_exists,
    test_founder_updates_not_treated_as_verified_evidence,
    test_completed_actions_do_not_improve_readiness,
    test_achieved_milestones_do_not_improve_readiness,
    test_investor_questions_derive_from_actual_gaps,
    test_checklist_derives_from_structured_assessment,
    test_deterministic_identical_input_identical_result,
    test_no_llm_import_in_fundraising_readiness_module,
    test_readiness_never_writes_startup_intelligence_score,
    test_no_new_membership_write_path,
    test_methodology_v2_scoring_files_unchanged,
    test_existing_founder_workspace_remains_functional,
    test_existing_deterministic_reanalysis_remains_functional,
    test_existing_action_plan_remains_functional,
    test_existing_idea_lab_remains_isolated,
    test_public_startup_profile_remains_unchanged,
    test_founder_explicitly_adds_readiness_gap,
    test_gap_provenance_preserved,
    test_duplicate_gap_add_does_not_spam_duplicates,
    test_no_automatic_task_creation_from_gaps,
]


def main() -> None:
    print("\nPhase 8 -- Fundraising Readiness V1 tests")
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
