"""
Regression tests for Idea Lab / Venture Simulator V1 --
app/ai/vps_scoring.py, app/ai/vps_guidance.py, app/database/db.py's
modeled_ventures CRUD functions, and the /ventures* endpoints in
app/api.py.

Two layers of coverage, matching test_compare.py's/test_discovery.py's
own convention:
- Pure unit tests against compute_vps()/generate_guidance() directly --
  no I/O, no auth needed, since these are deterministic functions of
  their input.
- API-layer tests through TestClient, reusing the exact same local-RSA-
  keypair JWT-mocking harness as test_backend_authentication.py (no live
  Clerk dependency), covering auth/ownership/isolation.

Every DB row created here uses a distinctive zztest_idealab_* user-id
prefix, cleaned up in a finally block even on failure. No test here makes
an LLM/Tavily call -- VPS scoring is entirely deterministic Python.

Run with:
    python -m app.tests.test_idea_lab
"""

import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.ai.vps_scoring import compute_vps
from app.ai.vps_guidance import generate_guidance
from app.database.db import engine, get_rankings, discover_startups

USER_A = "zztest_idealab_user_a"
USER_B = "zztest_idealab_user_b"

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


SAMPLE_ASSUMPTIONS = {
    "target_customer": "small construction companies",
    "market": {"estimated_market_size": "Large", "competition_intensity": "Medium"},
    "problem_solution": {
        "problem_statement": "Manual AR is slow",
        "solution_description": "AI automation",
        "differentiation": "Purpose-built for construction billing workflows",
    },
    "founder": {
        "founder_count": 2,
        "relevant_domain_experience_years": 3,
        "has_technical_cofounder": True,
        "has_business_cofounder": False,
    },
    "gtm": {"primary_acquisition_strategy": "Outbound", "expected_cac": 900},
    "economics": {"pricing_model": "Subscription", "price_point": 400, "expected_gross_margin_pct": 78},
    "validation": {"customer_interviews": 6, "waitlist_signups": 0, "paying_customers": 0, "monthly_revenue": None},
    "capital": {"starting_capital": 40000, "monthly_burn": 18000},
}


def _create_venture_body(name="ZZTest Idea Lab Venture", assumptions=None):
    return {
        "name": name,
        "description": "Test venture description.",
        "industry": "Construction Tech",
        "business_model": "Subscription",
        "target_customer": "small construction companies",
        "stage": "Researching",
        "assumptions": assumptions if assumptions is not None else SAMPLE_ASSUMPTIONS,
    }


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in (USER_A, USER_B):
            connection.execute(
                text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
                {"id": user_id},
            )


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM modeled_ventures WHERE user_id = ANY(:ids)"),
            {"ids": [USER_A, USER_B]},
        )
        connection.execute(
            text("DELETE FROM users WHERE id = ANY(:ids)"),
            {"ids": [USER_A, USER_B]},
        )


# --- Pure scoring engine tests (no auth, no I/O) ----------------------------


def test_identical_inputs_produce_identical_vps() -> None:
    result1 = compute_vps(SAMPLE_ASSUMPTIONS)
    result2 = compute_vps(SAMPLE_ASSUMPTIONS)
    expect(result1 == result2, "compute_vps must be a pure function -- identical input must give identical output")


def test_changing_relevant_assumption_changes_appropriate_category() -> None:
    baseline = compute_vps(SAMPLE_ASSUMPTIONS)
    baseline_validation = next(c for c in baseline["categories"] if c["key"] == "validation")

    stronger = dict(SAMPLE_ASSUMPTIONS)
    stronger["validation"] = {"customer_interviews": 30, "waitlist_signups": 200, "paying_customers": 10, "monthly_revenue": 5000}
    updated = compute_vps(stronger)
    updated_validation = next(c for c in updated["categories"] if c["key"] == "validation")

    expect(
        updated_validation["score"] > baseline_validation["score"],
        f"Stronger validation assumptions must raise the Validation category score ({baseline_validation['score']} -> {updated_validation['score']})",
    )
    expect(updated["vps"] > baseline["vps"], "Overall VPS must rise when validation strengthens")


def test_irrelevant_assumption_does_not_alter_unrelated_category() -> None:
    baseline = compute_vps(SAMPLE_ASSUMPTIONS)
    baseline_validation = next(c for c in baseline["categories"] if c["key"] == "validation")

    changed_founder = dict(SAMPLE_ASSUMPTIONS)
    changed_founder["founder"] = {
        "founder_count": 5,
        "relevant_domain_experience_years": 15,
        "has_technical_cofounder": True,
        "has_business_cofounder": True,
    }
    updated = compute_vps(changed_founder)
    updated_validation = next(c for c in updated["categories"] if c["key"] == "validation")

    expect(
        updated_validation["score"] == baseline_validation["score"],
        "Changing founder assumptions must never alter the Validation category score",
    )


def test_pure_idea_has_no_fabricated_vps() -> None:
    result = compute_vps({})
    expect(result["vps"] is None, "A venture with zero assumptions must have VPS None, never a fabricated number")
    expect(
        all(c["score"] is None for c in result["categories"]),
        "Every category must be Unavailable (None) for a venture with zero assumptions",
    )


def test_unavailable_pillar_never_defaults_to_zero() -> None:
    # Only validation provided -- every other category must stay None,
    # not silently become 0 and drag down a fabricated overall average
    # incorrectly (it should instead be EXCLUDED via renormalization).
    result = compute_vps({"validation": {"customer_interviews": 25, "paying_customers": 5, "waitlist_signups": 100, "monthly_revenue": 2000}})
    non_validation = [c for c in result["categories"] if c["key"] != "validation"]
    expect(
        all(c["score"] is None for c in non_validation),
        "Categories with no supporting assumptions must stay Unavailable (None), never default to 0",
    )
    expect(result["vps"] is not None, "VPS should still compute from the one available category")


def test_assumptions_preserve_unknown_values() -> None:
    sparse = {"target_customer": "someone", "market": {"estimated_market_size": None, "competition_intensity": None}}
    result = compute_vps(sparse)
    market = next(c for c in result["categories"] if c["key"] == "market_potential")
    expect(market["score"] is None, "A market category with no real size/competition data must remain Unavailable")


def test_assumption_vs_observation_provenance_is_structural() -> None:
    """Provenance is structural (see vps_scoring.py's own docstring): every
    field under `validation` is a founder-reported observation; every
    other top-level group is a modeled assumption. This test locks that
    structural boundary in place."""
    from app.models.idea_lab import VentureAssumptions

    fields = set(VentureAssumptions.model_fields.keys())
    expect("validation" in fields, "VentureAssumptions must have a distinct `validation` (observation) group")

    assumption_groups = fields - {"validation", "target_customer"}
    expect(
        assumption_groups == {"market", "problem_solution", "founder", "gtm", "economics", "capital"},
        f"Unexpected assumption groups: {assumption_groups}",
    )


def test_guidance_frames_validation_gap_as_expected_not_failure() -> None:
    result = compute_vps(SAMPLE_ASSUMPTIONS)
    guidance = generate_guidance(SAMPLE_ASSUMPTIONS, result)
    expect(
        any("expected at the idea stage" in gap for gap in guidance["validation_gaps"]),
        "Validation gaps must be framed as expected-at-this-stage, not as a failure",
    )


# --- Founder Loop V2, Section 5: context-aware priority selection ----------
#
# ClaimPilot-shaped fixture (real modeled venture from this phase's own
# investigation): paying customers, revenue, and a fully-populated
# problem/solution/differentiation -- the exact shape that used to
# recommend "Secure a first paying customer" (already false) and lead
# with "Define your differentiation" ahead of the much bigger open
# question a traction-stage venture actually has: whether growth holds up
# beyond founder-led selling.

TRACTION_ASSUMPTIONS = {
    "target_customer": "independent medical practices",
    "market": {"estimated_market_size": "Large", "competition_intensity": "Medium"},
    "problem_solution": {
        "problem_statement": "Healthcare providers lose revenue to denied claims.",
        "solution_description": "AI platform that recovers denied/underpaid claims.",
        "differentiation": None,  # left unset on purpose -- still a real, worth-naming gap
    },
    "founder": {
        "founder_count": 2,
        "relevant_domain_experience_years": 12,
        "has_technical_cofounder": True,
        "has_business_cofounder": True,
    },
    "gtm": {"primary_acquisition_strategy": "Founder-led outbound sales and referrals", "expected_cac": None},
    "economics": {"pricing_model": "Monthly subscription", "price_point": None, "expected_gross_margin_pct": 82},
    "validation": {"customer_interviews": 85, "waitlist_signups": None, "paying_customers": 14, "monthly_revenue": 70000},
    "capital": {"starting_capital": 2_500_000, "monthly_burn": 115_000},
}


def test_traction_venture_does_not_recommend_first_paying_customer() -> None:
    result = compute_vps(TRACTION_ASSUMPTIONS)
    guidance = generate_guidance(TRACTION_ASSUMPTIONS, result)
    expect(
        "Secure a first paying customer to validate willingness to pay." not in guidance["next_milestones"],
        "A venture with 14 already-reported paying customers must never be told to secure its first one",
    )


def test_traction_venture_with_weak_gtm_prioritizes_repeatable_growth_first() -> None:
    result = compute_vps(TRACTION_ASSUMPTIONS)
    gtm = next(c for c in result["categories"] if c["key"] == "gtm_feasibility")
    expect(gtm["score"] is not None and gtm["score"] < 7.0, f"Fixture assumption: GTM should score below strength threshold, got {gtm['score']}")

    guidance = generate_guidance(TRACTION_ASSUMPTIONS, result)
    expect(len(guidance["next_milestones"]) > 0, "Expected at least one milestone")
    expect(
        guidance["next_milestones"][0] == "Prove customer acquisition works repeatably beyond founder-led sales or referrals.",
        f"A traction-stage venture with weak GTM Feasibility should lead with repeatable-growth, got: {guidance['next_milestones'][0]!r}",
    )


def test_idea_stage_venture_still_leads_with_interviews() -> None:
    # No traction at all (paying=0, no revenue) -- the original,
    # unchanged priority order for a genuinely early idea must be
    # preserved: interviews first.
    idea_stage = dict(SAMPLE_ASSUMPTIONS)
    idea_stage["validation"] = {"customer_interviews": 2, "waitlist_signups": 0, "paying_customers": 0, "monthly_revenue": None}
    result = compute_vps(idea_stage)
    guidance = generate_guidance(idea_stage, result)
    expect(
        guidance["next_milestones"][0] == "Interview 20+ target customers to validate the problem is real.",
        f"An idea-stage venture with no traction should still lead with interviews, got: {guidance['next_milestones'][0]!r}",
    )


# --- Founder Loop V2, Section 7: "Path to 8" guidance -----------------------


def test_path_to_stronger_excludes_categories_at_or_above_threshold() -> None:
    result = compute_vps(TRACTION_ASSUMPTIONS)
    guidance = generate_guidance(TRACTION_ASSUMPTIONS, result)
    scores_by_key = {c["key"]: c["score"] for c in result["categories"]}

    for item in guidance["path_to_stronger"]:
        expect(item["score"] < 7.0, f"path_to_stronger must only include below-threshold categories, got {item}")
        expect(item["score"] == scores_by_key[item["key"]], "path_to_stronger score must exactly match the real computed category score, never a fabricated one")


def test_path_to_stronger_never_includes_unavailable_category() -> None:
    result = compute_vps(SAMPLE_ASSUMPTIONS)
    guidance = generate_guidance(SAMPLE_ASSUMPTIONS, result)
    expect(
        all(item["score"] is not None for item in guidance["path_to_stronger"]),
        "path_to_stronger must never include a category that is Unavailable (None)",
    )


def test_path_to_stronger_is_capped_and_ranked_by_weight_and_headroom() -> None:
    from app.ai.vps_guidance import MAX_PATH_TO_STRONGER

    result = compute_vps(TRACTION_ASSUMPTIONS)
    guidance = generate_guidance(TRACTION_ASSUMPTIONS, result)
    expect(len(guidance["path_to_stronger"]) <= MAX_PATH_TO_STRONGER, "path_to_stronger must be capped")

    weights = {
        "market_potential": 0.20, "problem_solution": 0.20, "founder_readiness": 0.15,
        "gtm_feasibility": 0.15, "economic_potential": 0.10, "validation": 0.20,
    }
    impacts = [weights[item["key"]] * (7.0 - item["score"]) for item in guidance["path_to_stronger"]]
    expect(impacts == sorted(impacts, reverse=True), "path_to_stronger must be ranked by weight x headroom, most impactful first")


# --- 1: creation requires auth ----------------------------------------------


def test_venture_creation_requires_auth() -> None:
    with _patched_auth():
        response = client.post("/ventures", json=_create_venture_body())
        expect(response.status_code == 401, f"Expected 401, got {response.status_code}")


# --- Phase 37B, Cases B/C: blank/whitespace-only venture names rejected ----
# The one truly new backend behavior this phase adds: defense in depth for
# any caller (a direct API call, a future client) that isn't the one
# frontend form whose own matching bug is fixed separately (see
# VentureDraftReview.tsx's own Phase 37B comment). min_length=1 alone
# already rejected a bare "" before this phase; these tests specifically
# exercise the new field_validator's whitespace-only case, plus confirm a
# real name with incidental whitespace is trimmed, not rejected.


def test_case_b_blank_venture_name_rejected() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.post(
                "/ventures", json=_create_venture_body(name=""), headers=_auth_headers(USER_A)
            )
            expect(response.status_code == 422, f"Expected 422 for blank name, got {response.status_code} {response.text}")
    finally:
        _cleanup()


def test_case_c_whitespace_only_venture_name_rejected() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.post(
                "/ventures", json=_create_venture_body(name="   "), headers=_auth_headers(USER_A)
            )
            expect(response.status_code == 422, f"Expected 422 for whitespace-only name, got {response.status_code} {response.text}")

            # A real name with incidental surrounding whitespace is
            # trimmed and accepted, never rejected -- the validator
            # blocks EMPTY-after-trim, not whitespace itself.
            response = client.post(
                "/ventures", json=_create_venture_body(name="  RelayOps  "), headers=_auth_headers(USER_A)
            )
            expect(response.status_code == 200, f"Expected a real name to be accepted, got {response.status_code} {response.text}")
            expect(response.json()["name"] == "RelayOps", f"Expected the name to be trimmed, got: {response.json()['name']!r}")
    finally:
        _cleanup()


def test_case_c2_blank_venture_name_rejected_on_update() -> None:
    """Same validator, same discipline, on UpdateVentureRequest -- a
    founder (or any caller) must never be able to blank out an existing
    venture's name via PUT either."""
    _ensure_test_users()
    try:
        with _patched_auth():
            created = client.post("/ventures", json=_create_venture_body(), headers=_auth_headers(USER_A)).json()
            venture_id = created["id"]

            response = client.put(
                f"/ventures/{venture_id}", json=_create_venture_body(name="   "), headers=_auth_headers(USER_A)
            )
            expect(response.status_code == 422, f"Expected 422 for whitespace-only name on update, got {response.status_code} {response.text}")
    finally:
        _cleanup()


# --- 23: all Idea Lab endpoints remain private ------------------------------


def test_all_idea_lab_endpoints_require_auth() -> None:
    with _patched_auth():
        expect(client.get("/ventures").status_code == 401, "GET /ventures must require auth")
        expect(client.get("/ventures/1").status_code == 401, "GET /ventures/{id} must require auth")
        expect(client.put("/ventures/1", json=_create_venture_body()).status_code == 401, "PUT must require auth")
        expect(client.delete("/ventures/1").status_code == 401, "DELETE must require auth")
        expect(
            client.post("/ventures/scenario-compare", json={"current_assumptions": {}, "modified_assumptions": {}}).status_code == 401,
            "scenario-compare must require auth",
        )


# --- 2: venture belongs to authenticated user -------------------------------


def test_venture_belongs_to_authenticated_user() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.post("/ventures", json=_create_venture_body(), headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Create failed: {response.text}")
            venture_id = response.json()["id"]

            with engine.begin() as connection:
                row = connection.execute(
                    text("SELECT user_id FROM modeled_ventures WHERE id = :id"), {"id": venture_id}
                ).mappings().first()

            expect(row["user_id"] == USER_A, f"Expected owner {USER_A}, got {row['user_id']!r}")
    finally:
        _cleanup()


# --- 3-5: cross-user isolation -----------------------------------------------


def test_user_cannot_access_another_users_venture() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            created = client.post("/ventures", json=_create_venture_body(), headers=_auth_headers(USER_A)).json()
            venture_id = created["id"]

            response = client.get(f"/ventures/{venture_id}", headers=_auth_headers(USER_B))
            expect(response.status_code == 404, f"Expected 404 for another user's venture, got {response.status_code}")
    finally:
        _cleanup()


def test_user_cannot_modify_another_users_venture() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            created = client.post("/ventures", json=_create_venture_body(), headers=_auth_headers(USER_A)).json()
            venture_id = created["id"]

            response = client.put(
                f"/ventures/{venture_id}",
                json=_create_venture_body(name="Hijacked name"),
                headers=_auth_headers(USER_B),
            )
            expect(response.status_code == 404, f"Expected 404, got {response.status_code}")

            with engine.begin() as connection:
                row = connection.execute(
                    text("SELECT name FROM modeled_ventures WHERE id = :id"), {"id": venture_id}
                ).mappings().first()
            expect(row["name"] != "Hijacked name", "USER_B must not be able to rename USER_A's venture")
    finally:
        _cleanup()


def test_user_cannot_delete_another_users_venture() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            created = client.post("/ventures", json=_create_venture_body(), headers=_auth_headers(USER_A)).json()
            venture_id = created["id"]

            response = client.delete(f"/ventures/{venture_id}", headers=_auth_headers(USER_B))
            expect(response.status_code == 404, f"Expected 404, got {response.status_code}")

            still_there = client.get(f"/ventures/{venture_id}", headers=_auth_headers(USER_A))
            expect(still_there.status_code == 200, "USER_A's venture must survive USER_B's delete attempt")
    finally:
        _cleanup()


# --- 6-10: no canonical/ownership side effects ------------------------------


def test_venture_creation_has_no_canonical_side_effects() -> None:
    _ensure_test_users()
    try:
        with engine.begin() as connection:
            before_startups = connection.execute(text("SELECT COUNT(*) FROM startups")).scalar()
            before_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()
            before_memberships = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()
            before_saved = connection.execute(text("SELECT COUNT(*) FROM saved_startups")).scalar()

        with _patched_auth():
            response = client.post("/ventures", json=_create_venture_body(), headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Create failed: {response.text}")

        with engine.begin() as connection:
            after_startups = connection.execute(text("SELECT COUNT(*) FROM startups")).scalar()
            after_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()
            after_memberships = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()
            after_saved = connection.execute(text("SELECT COUNT(*) FROM saved_startups")).scalar()

        expect(after_startups == before_startups, "Venture creation must never create a startups row")
        expect(after_analyses == before_analyses, "Venture creation must never create an analyses row")
        expect(after_memberships == before_memberships, "Venture creation must never create a startup_membership")
        expect(after_saved == before_saved, "Venture creation must never create a saved_startup")
    finally:
        _cleanup()


def test_vps_never_stored_as_sps() -> None:
    """The computed model_result JSONB must never be written into
    analyses.methodology, and must use the key "vps", never
    "startup_intelligence_score" (SPS's own field name)."""
    _ensure_test_users()
    try:
        with _patched_auth():
            response = client.post("/ventures", json=_create_venture_body(), headers=_auth_headers(USER_A))
            body = response.json()

        expect("vps" in body["model_result"], "model_result must use the key 'vps'")
        expect(
            "startup_intelligence_score" not in body["model_result"],
            "model_result must never use SPS's own field name",
        )

        with engine.begin() as connection:
            analyses_with_venture_name = connection.execute(
                text("SELECT COUNT(*) FROM analyses WHERE company_name = :name"),
                {"name": _create_venture_body()["name"]},
            ).scalar()
        expect(analyses_with_venture_name == 0, "A modeled venture must never appear as an analyses row")
    finally:
        _cleanup()


# --- 11-12: never appears in Rankings/Discovery -----------------------------


def test_modeled_venture_never_appears_in_rankings_or_discovery() -> None:
    _ensure_test_users()
    try:
        venture_name = "ZZTest Idea Lab Rankings Check"
        with _patched_auth():
            response = client.post("/ventures", json=_create_venture_body(name=venture_name), headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Create failed: {response.text}")

        # Portfolio Release Task 3B: admin bypass, unrelated to this test.
        rankings = get_rankings("__task3b_sanity_admin__", True)
        expect(
            all(row["company_name"] != venture_name for row in rankings),
            "A modeled venture must never appear in Rankings",
        )

        discovery = discover_startups("__task3b_sanity_admin__", True)
        expect(
            all(row["company_name"] != venture_name for row in discovery),
            "A modeled venture must never appear in Discovery",
        )
    finally:
        _cleanup()


# --- 18: scenario comparison preserves the original ------------------------


def test_scenario_comparison_preserves_original_venture() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            created = client.post("/ventures", json=_create_venture_body(), headers=_auth_headers(USER_A)).json()
            venture_id = created["id"]

            hypothetical = dict(SAMPLE_ASSUMPTIONS)
            hypothetical["validation"] = {"customer_interviews": 100, "waitlist_signups": 500, "paying_customers": 50, "monthly_revenue": 20000}

            scenario_response = client.post(
                "/ventures/scenario-compare",
                json={"current_assumptions": SAMPLE_ASSUMPTIONS, "modified_assumptions": hypothetical},
                headers=_auth_headers(USER_A),
            )
            expect(scenario_response.status_code == 200, f"Scenario compare failed: {scenario_response.text}")
            expect(
                scenario_response.json()["modified"]["vps"] > scenario_response.json()["current"]["vps"],
                "The hypothetical scenario should score higher given much stronger validation",
            )

            reopened = client.get(f"/ventures/{venture_id}", headers=_auth_headers(USER_A)).json()
            expect(
                reopened["assumptions"]["validation"]["paying_customers"] == 0,
                "scenario-compare must never overwrite the venture's persisted assumptions",
            )
    finally:
        _cleanup()


# --- 19: invalid numeric inputs fail cleanly --------------------------------


def test_invalid_numeric_inputs_fail_cleanly() -> None:
    with _patched_auth():
        bad_assumptions = dict(SAMPLE_ASSUMPTIONS)
        bad_assumptions["validation"] = {"customer_interviews": -5, "waitlist_signups": 0, "paying_customers": 0, "monthly_revenue": None}
        response = client.post(
            "/ventures", json=_create_venture_body(assumptions=bad_assumptions), headers=_auth_headers(USER_A)
        )
        expect(response.status_code == 422, f"Negative customer_interviews should be rejected, got {response.status_code}")


# --- 20: API never accepts a client-controlled user_id ----------------------


def test_api_never_accepts_client_controlled_user_id() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            body = _create_venture_body()
            body["user_id"] = USER_B  # not a real field -- must be ignored, not honored
            response = client.post("/ventures", json=body, headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Create failed: {response.text}")

            with engine.begin() as connection:
                row = connection.execute(
                    text("SELECT user_id FROM modeled_ventures WHERE id = :id"), {"id": response.json()["id"]}
                ).mappings().first()

            expect(
                row["user_id"] == USER_A,
                f"A client-supplied user_id field must be ignored; expected {USER_A}, got {row['user_id']!r}",
            )
    finally:
        _cleanup()


# --- 21-22: old canonical behavior + public endpoints unaffected ------------


def test_canonical_behavior_and_public_endpoints_unaffected() -> None:
    # Portfolio Release Task 3B: get_rankings()/discover_startups() now
    # require a viewer to scope by -- admin bypass here, unrelated to this
    # test's own job (Idea Lab isolation from canonical intelligence).
    before_rankings = len(get_rankings("__task3b_sanity_admin__", True))
    before_discovery = len(discover_startups("__task3b_sanity_admin__", True))

    _ensure_test_users()
    try:
        with _patched_auth():
            client.post("/ventures", json=_create_venture_body(), headers=_auth_headers(USER_A))

        expect(
            len(get_rankings("__task3b_sanity_admin__", True)) == before_rankings,
            "Rankings population must be unaffected by Idea Lab activity",
        )
        expect(
            len(discover_startups("__task3b_sanity_admin__", True)) == before_discovery,
            "Discovery population must be unaffected by Idea Lab activity",
        )

        # Portfolio Release Task 3B supersedes the original "remain public"
        # assertion (approved decision: no public scores-only exception) --
        # /rankings and /discover now require auth; any authenticated
        # caller (USER_A here) can still reach them.
        with _patched_auth():
            expect(client.get("/rankings").status_code == 401, "/rankings must require auth")
            expect(client.get("/discover").status_code == 401, "/discover must require auth")
            expect(
                client.get("/rankings", headers=_auth_headers(USER_A)).status_code == 200,
                "An authenticated caller must still reach /rankings",
            )
            expect(
                client.get("/discover", headers=_auth_headers(USER_A)).status_code == 200,
                "An authenticated caller must still reach /discover",
            )
            expect(client.get("/compare", params={"startups": "1,2"}).status_code == 401, "/compare must require auth")
            expect(
                client.get("/compare", params={"startups": "1,2"}, headers=_auth_headers(USER_A)).status_code in (200, 400),
                "An authenticated caller must still reach /compare",
            )
    finally:
        _cleanup()


TESTS = [
    test_identical_inputs_produce_identical_vps,
    test_changing_relevant_assumption_changes_appropriate_category,
    test_irrelevant_assumption_does_not_alter_unrelated_category,
    test_pure_idea_has_no_fabricated_vps,
    test_unavailable_pillar_never_defaults_to_zero,
    test_assumptions_preserve_unknown_values,
    test_assumption_vs_observation_provenance_is_structural,
    test_guidance_frames_validation_gap_as_expected_not_failure,
    test_traction_venture_does_not_recommend_first_paying_customer,
    test_traction_venture_with_weak_gtm_prioritizes_repeatable_growth_first,
    test_idea_stage_venture_still_leads_with_interviews,
    test_path_to_stronger_excludes_categories_at_or_above_threshold,
    test_path_to_stronger_never_includes_unavailable_category,
    test_path_to_stronger_is_capped_and_ranked_by_weight_and_headroom,
    test_venture_creation_requires_auth,
    test_case_b_blank_venture_name_rejected,
    test_case_c_whitespace_only_venture_name_rejected,
    test_case_c2_blank_venture_name_rejected_on_update,
    test_all_idea_lab_endpoints_require_auth,
    test_venture_belongs_to_authenticated_user,
    test_user_cannot_access_another_users_venture,
    test_user_cannot_modify_another_users_venture,
    test_user_cannot_delete_another_users_venture,
    test_venture_creation_has_no_canonical_side_effects,
    test_vps_never_stored_as_sps,
    test_modeled_venture_never_appears_in_rankings_or_discovery,
    test_scenario_comparison_preserves_original_venture,
    test_invalid_numeric_inputs_fail_cleanly,
    test_api_never_accepts_client_controlled_user_id,
    test_canonical_behavior_and_public_endpoints_unaffected,
]


def main() -> None:
    print("\nIdea Lab / Venture Simulator V1 tests")
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

    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
