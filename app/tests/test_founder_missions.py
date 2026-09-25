"""
Regression tests for Phase 10.7 -- Founder Missions V1: the
venture_missions table (app/database/db.py), its Pydantic contracts
(app/models/venture_missions.py), and the /ventures/{id}/missions*
endpoints in app/api.py.

Same JWT-mocking harness and zztest_* user-id convention as
test_idea_lab.py -- no live Clerk dependency, every row cleaned up in a
finally block even on failure.

The single most important thing this file proves is the VPS FIREWALL:
creating, completing, dismissing, or reflecting on a mission must never
change a venture's stored assumptions, model_result, or VPS. Only an
explicit PUT /ventures/{id} (completely unchanged by this phase) can do
that.

Run with:
    python -m app.tests.test_founder_missions
"""

import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.database.db import engine, get_rankings, discover_startups

USER_A = "zztest_missions_user_a"
USER_B = "zztest_missions_user_b"

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


# --- JWT mocking harness (mirrors test_idea_lab.py) -------------------------


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
    "target_customer": "solo landlords",
    "market": {"estimated_market_size": "Medium", "competition_intensity": "Medium"},
    "problem_solution": {
        "problem_statement": "Rent collection is manual",
        "solution_description": "Automated rent collection app",
        "differentiation": "Built for landlords with under 10 units",
    },
    "founder": {
        "founder_count": 1,
        "relevant_domain_experience_years": 2,
        "has_technical_cofounder": False,
        "has_business_cofounder": False,
    },
    "gtm": {"primary_acquisition_strategy": "Content marketing", "expected_cac": 200},
    "economics": {"pricing_model": "Subscription", "price_point": 19, "expected_gross_margin_pct": 80},
    "validation": {"customer_interviews": None, "waitlist_signups": None, "paying_customers": None, "monthly_revenue": None},
    "capital": {"starting_capital": 5000, "monthly_burn": 1000},
}


def _create_venture_body(name="ZZTest Missions Venture"):
    return {
        "name": name,
        "description": "Test venture for Founder Missions.",
        "industry": "Proptech",
        "business_model": "Subscription",
        "target_customer": "solo landlords",
        "stage": "Idea",
        "assumptions": SAMPLE_ASSUMPTIONS,
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
            text("""
                DELETE FROM venture_missions
                WHERE venture_id IN (SELECT id FROM modeled_ventures WHERE user_id = ANY(:ids))
            """),
            {"ids": [USER_A, USER_B]},
        )
        connection.execute(
            text("DELETE FROM modeled_ventures WHERE user_id = ANY(:ids)"),
            {"ids": [USER_A, USER_B]},
        )
        connection.execute(
            text("DELETE FROM users WHERE id = ANY(:ids)"),
            {"ids": [USER_A, USER_B]},
        )


def _create_venture(user_id: str, name="ZZTest Missions Venture") -> dict:
    response = client.post("/ventures", json=_create_venture_body(name=name), headers=_auth_headers(user_id))
    expect(response.status_code == 200, f"Venture create failed: {response.text}")
    return response.json()


def _create_mission(venture_id: int, user_id: str, **overrides) -> dict:
    body = {
        "title": "Interview 10 potential customers",
        "description": "Learn how they solve this problem today.",
        "mission_type": "customer_discovery",
        "related_category": "validation",
        "source": "founder_created",
        **overrides,
    }
    response = client.post(f"/ventures/{venture_id}/missions", json=body, headers=_auth_headers(user_id))
    expect(response.status_code == 200, f"Mission create failed: {response.text}")
    return response.json()


# --- Authorization -----------------------------------------------------------


def test_signed_out_cannot_access_mission_endpoints() -> None:
    with _patched_auth():
        expect(client.get("/ventures/1/missions").status_code == 401, "GET missions must require auth")
        expect(
            client.post("/ventures/1/missions", json={"title": "x"}).status_code == 401,
            "POST mission must require auth",
        )
        expect(
            client.patch("/ventures/1/missions/1/status", json={"status": "completed"}).status_code == 401,
            "PATCH mission status must require auth",
        )
        expect(
            client.post("/ventures/1/missions/1/learning", json={"learning_summary": "x"}).status_code == 401,
            "POST mission learning must require auth",
        )


def test_owner_can_access_missions() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            _create_mission(venture["id"], USER_A)

            response = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Owner list failed: {response.text}")
            expect(len(response.json()) == 1, "Owner should see their own mission")
    finally:
        _cleanup()


def test_another_user_cannot_read_missions() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            _create_mission(venture["id"], USER_A)

            response = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_B))
            expect(response.status_code == 404, f"Expected 404 for another user's venture, got {response.status_code}")
    finally:
        _cleanup()


def test_another_user_cannot_create_missions() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)

            response = client.post(
                f"/ventures/{venture['id']}/missions",
                json={"title": "Hijack attempt", "source": "founder_created"},
                headers=_auth_headers(USER_B),
            )
            expect(response.status_code == 404, f"Expected 404, got {response.status_code}")

            still_empty = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(len(still_empty) == 0, "USER_B's attempted mission must not exist under USER_A's venture")
    finally:
        _cleanup()


def test_another_user_cannot_mutate_missions() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)

            status_response = client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "completed"},
                headers=_auth_headers(USER_B),
            )
            expect(status_response.status_code == 404, f"Expected 404, got {status_response.status_code}")

            learning_response = client.post(
                f"/ventures/{venture['id']}/missions/{mission['id']}/learning",
                json={"learning_summary": "Hijacked reflection"},
                headers=_auth_headers(USER_B),
            )
            expect(learning_response.status_code == 404, f"Expected 404, got {learning_response.status_code}")

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(reopened[0]["status"] == "active", "USER_B must not be able to change USER_A's mission status")
            expect(reopened[0]["learning_summary"] is None, "USER_B must not be able to write USER_A's mission reflection")
    finally:
        _cleanup()


# --- Persistence ---------------------------------------------------------


def test_mission_creation_persists() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A, title="Talk to 10 customers")

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(len(reopened) == 1, "Mission must persist")
            expect(reopened[0]["title"] == "Talk to 10 customers", "Persisted mission title must match")
            expect(reopened[0]["status"] == "active", "New missions default to active")
    finally:
        _cleanup()


def test_mission_completion_persists() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)

            response = client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )
            expect(response.status_code == 200, f"Complete failed: {response.text}")
            expect(response.json()["status"] == "completed", "Status must be completed")
            expect(response.json()["completed_at"] is not None, "completed_at must be set")

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(reopened[0]["status"] == "completed", "Completion must persist across a fresh read")
    finally:
        _cleanup()


def test_mission_dismissal_persists() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)

            client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "dismissed"},
                headers=_auth_headers(USER_A),
            )

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(reopened[0]["status"] == "dismissed", "Dismissal must persist")
            expect(reopened[0]["completed_at"] is None, "Dismissing an never-completed mission must not set completed_at")
    finally:
        _cleanup()


def test_reflection_persists() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)

            response = client.post(
                f"/ventures/{venture['id']}/missions/{mission['id']}/learning",
                json={"learning_summary": "Nobody wanted this. Useful signal."},
                headers=_auth_headers(USER_A),
            )
            expect(response.status_code == 200, f"Learning record failed: {response.text}")
            expect(response.json()["learning_recorded_at"] is not None, "learning_recorded_at must be set")

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(
                reopened[0]["learning_summary"] == "Nobody wanted this. Useful signal.",
                "Reflection text must persist across a fresh read",
            )
    finally:
        _cleanup()


def test_founder_created_mission_persists() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(
                venture["id"], USER_A,
                title="Ask my professor for feedback",
                source="founder_created",
                related_category=None,
            )
            expect(mission["source"] == "founder_created", "Source must be founder_created")

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(len(reopened) == 1, "Founder-created mission must persist")
    finally:
        _cleanup()


def test_vps_guidance_mission_is_idempotent() -> None:
    """'Make this a mission' twice on the same recommendation must not
    create a duplicate row -- mirrors create_founder_action()'s own
    idempotency guarantee."""
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            first = _create_mission(
                venture["id"], USER_A, title="Interview 20+ target customers", source="vps_guidance"
            )
            second = _create_mission(
                venture["id"], USER_A, title="Interview 20+ target customers", source="vps_guidance"
            )
            expect(first["id"] == second["id"], "Same vps_guidance title must return the same mission, not a duplicate")

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(len(reopened) == 1, "Exactly one row must exist for a deduplicated vps_guidance mission")
    finally:
        _cleanup()


def test_pitch_deck_coach_mission_persists_with_resource_ref() -> None:
    """Phase 11 -- Pitch Deck Coach V2, Part 13/14: a mission created via
    the deck review's "Make this a mission" flow uses source
    'pitch_deck_coach' (not vps_guidance or founder_created) and carries
    a resource_ref (a playbook slug) end to end."""
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(
                venture["id"], USER_A,
                title="Clarify initial GTM strategy",
                description="Investors need to understand how you'll acquire your first repeatable customers.",
                mission_type="gtm",
                related_category="gtm",
                source="pitch_deck_coach",
                resource_ref="go-to-market",
            )
            expect(mission["source"] == "pitch_deck_coach", f"Source must round-trip as pitch_deck_coach, got {mission['source']}")
            expect(mission["resource_ref"] == "go-to-market", f"resource_ref must round-trip, got {mission['resource_ref']}")

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(len(reopened) == 1, "The pitch-deck-coach mission must persist")
            expect(reopened[0]["resource_ref"] == "go-to-market", "resource_ref must survive a reload, not just the create response")
    finally:
        _cleanup()


def test_resource_ref_defaults_to_null_when_absent() -> None:
    """No caller before Phase 11 ever sent resource_ref -- confirms the
    new, optional field defaults to null rather than breaking any
    existing mission-creation shape (vps_guidance, founder_created)."""
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A, source="founder_created")
            expect(mission["resource_ref"] is None, f"resource_ref must default to null when the caller never sends it, got {mission['resource_ref']!r}")
    finally:
        _cleanup()


def test_pitch_deck_coach_mission_is_idempotent() -> None:
    """Same dedup guarantee as vps_guidance (Part 13's own "clicking twice
    must not create a duplicate" requirement) -- source <> 'founder_created'
    already covers pitch_deck_coach without any separate index."""
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            first = _create_mission(
                venture["id"], USER_A, title="Clarify initial GTM strategy", source="pitch_deck_coach"
            )
            second = _create_mission(
                venture["id"], USER_A, title="Clarify initial GTM strategy", source="pitch_deck_coach"
            )
            expect(first["id"] == second["id"], "Same pitch_deck_coach title must return the same mission, not a duplicate")

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(len(reopened) == 1, "Exactly one row must exist for a deduplicated pitch_deck_coach mission")
    finally:
        _cleanup()


def test_founder_created_missions_are_not_deduplicated() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            _create_mission(venture["id"], USER_A, title="Talk to my advisor", source="founder_created")
            _create_mission(venture["id"], USER_A, title="Talk to my advisor", source="founder_created")

            reopened = client.get(f"/ventures/{venture['id']}/missions", headers=_auth_headers(USER_A)).json()
            expect(len(reopened) == 2, "Two founder_created missions with identical text must both be kept")
    finally:
        _cleanup()


# --- VPS firewall ------------------------------------------------------------


def test_mission_creation_does_not_change_vps() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            before = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()

            _create_mission(venture["id"], USER_A)

            after = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()
            expect(before["model_result"] == after["model_result"], "Creating a mission must not change model_result/VPS")
    finally:
        _cleanup()


def test_mission_completion_does_not_change_vps() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)
            before = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()

            client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )

            after = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()
            expect(before["model_result"] == after["model_result"], "Completing a mission must not change model_result/VPS")
    finally:
        _cleanup()


def test_mission_dismissal_does_not_change_vps() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)
            before = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()

            client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "dismissed"},
                headers=_auth_headers(USER_A),
            )

            after = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()
            expect(before["model_result"] == after["model_result"], "Dismissing a mission must not change model_result/VPS")
    finally:
        _cleanup()


def test_reflection_does_not_change_vps() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)
            before = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()

            client.post(
                f"/ventures/{venture['id']}/missions/{mission['id']}/learning",
                json={"learning_summary": "I interviewed 12 people and 2 said they'd pay."},
                headers=_auth_headers(USER_A),
            )

            after = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()
            expect(before["model_result"] == after["model_result"], "Recording a reflection must not change model_result/VPS")
    finally:
        _cleanup()


def test_mission_creation_does_not_change_assumptions() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            before = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()

            _create_mission(venture["id"], USER_A)

            after = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()
            expect(before["assumptions"] == after["assumptions"], "Creating a mission must not change assumptions")
    finally:
        _cleanup()


def test_mission_completion_does_not_change_validation() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(
                venture["id"], USER_A, title="Interview 10 potential customers", related_category="validation"
            )

            client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )

            after = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()
            expect(
                after["assumptions"]["validation"]["customer_interviews"] is None,
                "Marking an 'interview customers' mission complete must NOT populate customer_interviews",
            )
    finally:
        _cleanup()


def test_reflection_does_not_change_validation() -> None:
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)

            client.post(
                f"/ventures/{venture['id']}/missions/{mission['id']}/learning",
                json={"learning_summary": "customer_interviews: 12, paying_customers: 2"},
                headers=_auth_headers(USER_A),
            )

            after = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()
            expect(
                after["assumptions"]["validation"]["customer_interviews"] is None
                and after["assumptions"]["validation"]["paying_customers"] is None,
                "Free-text reflection -- even text that LOOKS like structured numbers -- must never be auto-extracted into validation",
            )
    finally:
        _cleanup()


# --- Explicit model update (existing venture-update path only) --------------


def test_explicit_validation_update_uses_existing_venture_path() -> None:
    """Completing/reflecting on a mission has zero scoring effect (proven
    above); this proves the ONLY way forward -- an explicit PUT
    /ventures/{id}, exactly like a manual edit -- still works normally and
    is not routed through any mission endpoint."""
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A, related_category="validation")
            client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )
            before = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()
            before_vps = before["model_result"]["vps"]

            updated_assumptions = dict(SAMPLE_ASSUMPTIONS)
            updated_assumptions["validation"] = {
                "customer_interviews": 12, "waitlist_signups": 0, "paying_customers": 2, "monthly_revenue": None
            }
            update_body = _create_venture_body()
            update_body["assumptions"] = updated_assumptions

            response = client.put(f"/ventures/{venture['id']}", json=update_body, headers=_auth_headers(USER_A))
            expect(response.status_code == 200, f"Explicit update failed: {response.text}")

            after = response.json()
            expect(
                after["assumptions"]["validation"]["customer_interviews"] == 12,
                "Explicit PUT must persist the founder-confirmed validation value",
            )
            expect(
                after["model_result"]["vps"] != before_vps,
                "VPS must recalculate because assumptions genuinely changed via the existing update path",
            )

            validation_category = next(c for c in after["model_result"]["categories"] if c["key"] == "validation")
            expect(validation_category["score"] is not None, "Validation category must now be scored")
    finally:
        _cleanup()


def test_category_independence_still_intact_after_mission_flow() -> None:
    """Mirrors test_idea_lab.py's own irrelevant-assumption test, run
    after a full mission create/complete/reflect cycle -- proves the
    mission flow introduced no new coupling between categories."""
    _ensure_test_users()
    try:
        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)
            client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )
            before = client.get(f"/ventures/{venture['id']}", headers=_auth_headers(USER_A)).json()
            before_founder = next(c for c in before["model_result"]["categories"] if c["key"] == "founder_readiness")

            updated_assumptions = dict(SAMPLE_ASSUMPTIONS)
            updated_assumptions["founder"] = {
                "founder_count": 3, "relevant_domain_experience_years": 10,
                "has_technical_cofounder": True, "has_business_cofounder": True,
            }
            update_body = _create_venture_body()
            update_body["assumptions"] = updated_assumptions
            response = client.put(f"/ventures/{venture['id']}", json=update_body, headers=_auth_headers(USER_A))

            after_validation = next(c for c in response.json()["model_result"]["categories"] if c["key"] == "validation")
            before_validation = next(c for c in before["model_result"]["categories"] if c["key"] == "validation")
            expect(
                after_validation["score"] == before_validation["score"],
                "Changing founder assumptions must never alter the Validation category score",
            )
    finally:
        _cleanup()


# --- Canonical-startup isolation ---------------------------------------------


def test_missions_never_create_startup_or_analysis_rows() -> None:
    _ensure_test_users()
    try:
        with engine.begin() as connection:
            before_startups = connection.execute(text("SELECT COUNT(*) FROM startups")).scalar()
            before_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()

        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)
            client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )
            client.post(
                f"/ventures/{venture['id']}/missions/{mission['id']}/learning",
                json={"learning_summary": "Learned something."},
                headers=_auth_headers(USER_A),
            )

        with engine.begin() as connection:
            after_startups = connection.execute(text("SELECT COUNT(*) FROM startups")).scalar()
            after_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()

        expect(after_startups == before_startups, "Mission activity must never create a startups row")
        expect(after_analyses == before_analyses, "Mission activity must never create an analyses row")
    finally:
        _cleanup()


def test_missions_never_create_founder_actions_or_memberships() -> None:
    _ensure_test_users()
    try:
        with engine.begin() as connection:
            before_actions = connection.execute(text("SELECT COUNT(*) FROM founder_actions")).scalar()
            before_memberships = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()

        with _patched_auth():
            venture = _create_venture(USER_A)
            mission = _create_mission(venture["id"], USER_A)
            client.patch(
                f"/ventures/{venture['id']}/missions/{mission['id']}/status",
                json={"status": "completed"},
                headers=_auth_headers(USER_A),
            )

        with engine.begin() as connection:
            after_actions = connection.execute(text("SELECT COUNT(*) FROM founder_actions")).scalar()
            after_memberships = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()

        expect(after_actions == before_actions, "Mission activity must never create a founder_actions row")
        expect(after_memberships == before_memberships, "Mission activity must never create a startup_memberships row")
    finally:
        _cleanup()


def test_missions_never_appear_in_rankings_or_discovery() -> None:
    _ensure_test_users()
    try:
        venture_name = "ZZTest Missions Rankings Check"
        with _patched_auth():
            venture = _create_venture(USER_A, name=venture_name)
            _create_mission(venture["id"], USER_A, title="Ranked mission check")

        # Portfolio Release Task 3B: get_rankings()/discover_startups() now
        # require a viewer to scope by -- passed here as an admin bypass
        # ("__task3b_sanity_admin__", True) purely so this population-
        # isolation check keeps seeing the full population, unaffected by
        # the new, orthogonal authorization feature this test isn't about.
        rankings = get_rankings("__task3b_sanity_admin__", True)
        expect(
            all(row["company_name"] != venture_name for row in rankings),
            "A venture with missions must still never appear in Rankings",
        )

        discovery = discover_startups("__task3b_sanity_admin__", True)
        expect(
            all(row["company_name"] != venture_name for row in discovery),
            "A venture with missions must still never appear in Discovery",
        )
    finally:
        _cleanup()


TESTS = [
    test_signed_out_cannot_access_mission_endpoints,
    test_owner_can_access_missions,
    test_another_user_cannot_read_missions,
    test_another_user_cannot_create_missions,
    test_another_user_cannot_mutate_missions,
    test_mission_creation_persists,
    test_mission_completion_persists,
    test_mission_dismissal_persists,
    test_reflection_persists,
    test_founder_created_mission_persists,
    test_vps_guidance_mission_is_idempotent,
    test_pitch_deck_coach_mission_persists_with_resource_ref,
    test_resource_ref_defaults_to_null_when_absent,
    test_pitch_deck_coach_mission_is_idempotent,
    test_founder_created_missions_are_not_deduplicated,
    test_mission_creation_does_not_change_vps,
    test_mission_completion_does_not_change_vps,
    test_mission_dismissal_does_not_change_vps,
    test_reflection_does_not_change_vps,
    test_mission_creation_does_not_change_assumptions,
    test_mission_completion_does_not_change_validation,
    test_reflection_does_not_change_validation,
    test_explicit_validation_update_uses_existing_venture_path,
    test_category_independence_still_intact_after_mission_flow,
    test_missions_never_create_startup_or_analysis_rows,
    test_missions_never_create_founder_actions_or_memberships,
    test_missions_never_appear_in_rankings_or_discovery,
]


def main() -> None:
    print("\nFounder Missions V1 tests")
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
