"""
Task 31 -- Evidence Engine v1 product integration: engine selection, the
feature flag's safe default, the adapter/service boundary (mocked -- no
real OpenAI/Tavily call anywhere in this file), persistence, and
authenticated ownership-scoped retrieval.

Reuses the exact same local-RSA-keypair JWT-mocking harness as every
other phase's test file (no live Clerk dependency; see
app/tests/test_analysis_usage_protection.py, the pattern this file
copies). Every row here uses a distinctive zztest_evidence_v1_* user-id
prefix, cleaned up in a finally block even on failure.

No paid external call anywhere in this file: `app.evidence_v1.service.
run_evidence_v1_analysis` (the one function that would reach real
OpenAI/Tavily) is monkeypatched to a fake, deterministic result for
every test in this file.

Run with:
    python -m app.tests.test_evidence_v1_integration
"""

from __future__ import annotations

import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
import app.evidence_v1.config as ev1_config
import app.evidence_v1.service as ev1_service
from app.database.db import engine
from app.evidence_v1.adapter import EvidenceV1AdapterError, EvidenceV1RunResult

USER_A = "zztest_evidence_v1_user_a"
USER_B = "zztest_evidence_v1_user_b"
ALL_USERS = [USER_A, USER_B]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"

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


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in ALL_USERS:
            connection.execute(text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"), {"id": user_id})


def _fake_run_result(company_ref: str = "zztest_co") -> EvidenceV1RunResult:
    return EvidenceV1RunResult(
        company_ref=company_ref, stage="Undetermined", as_of="2026-09-30", generated_at="2026-09-30",
        total_claims_in_ledger=3, rejected_count=0,
        accepted_claims=[{"claim_id": "c1", "claim_text": "a grounded claim"}],
        pillar_results=[{"pillar": "Product & Technology", "strength": 7.5, "publishable": True}],
        company_coverage_pct=12.5, company_confidence="High", company_publishable=False,
        company_withhold_reasons=["weighted coverage 12.5% < floor 40.0%"], cross_pillar_audit=[],
        telemetry={"run_id": "zztest-run", "sources_retrieved": 5}, wall_clock_seconds=1.23,
    )


class _patched_evidence_v1_flag:
    """Patches the server-side feature flag (never trusts the client's
    own `engine` field as the authorization boundary -- item 4)."""

    def __init__(self, enabled: bool):
        self._enabled = enabled

    def __enter__(self):
        self._orig = ev1_config.evidence_v1_enabled
        ev1_config.evidence_v1_enabled = lambda: self._enabled
        return self

    def __exit__(self, *exc):
        ev1_config.evidence_v1_enabled = self._orig
        return False


class _patched_adapter_success:
    """Monkeypatches the ONE function that would reach real providers --
    app.evidence_v1.service.run_evidence_v1_analysis -- to a fake,
    deterministic result. No network call anywhere in this file."""

    def __init__(self, result: EvidenceV1RunResult | None = None):
        self._result = result or _fake_run_result()
        self.calls: list[tuple[str, str]] = []

    def __enter__(self):
        self._orig = ev1_service.run_evidence_v1_analysis

        def fake(company_name: str, website_url: str, as_of=None):
            self.calls.append((company_name, website_url))
            return self._result

        ev1_service.run_evidence_v1_analysis = fake
        return self

    def __exit__(self, *exc):
        ev1_service.run_evidence_v1_analysis = self._orig
        return False


class _patched_adapter_failure:
    def __init__(self, exc: Exception):
        self._exc = exc

    def __enter__(self):
        self._orig = ev1_service.run_evidence_v1_analysis

        def fake(company_name: str, website_url: str, as_of=None):
            raise self._exc

        ev1_service.run_evidence_v1_analysis = fake
        return self

    def __exit__(self, *exc):
        ev1_service.run_evidence_v1_analysis = self._orig
        return False


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM evidence_v1_analyses WHERE owner_user_id = ANY(:ids)"),
            {"ids": ALL_USERS},
        )
        connection.execute(text("DELETE FROM analysis_runs WHERE user_id = ANY(:ids)"), {"ids": ALL_USERS})


# --- 1. Engine selection / safe default / feature flag -----------------------

def test_no_engine_field_defaults_to_legacy_and_does_not_touch_evidence_v1_adapter() -> None:
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_success() as fake:
        _ensure_test_users()
        # An empty legacy request (no website/text/pdf) is rejected by the
        # legacy path's own pre-existing validation (400) -- proving this
        # request reached the LEGACY branch, not evidence_v1 (which would
        # have required company_name/website_url and returned a different
        # error, or succeeded and called the fake adapter).
        response = client.post("/analyze", data={}, headers=_auth_headers(USER_A))
        expect(response.status_code == 400, f"expected legacy's own validation error, got {response.status_code}: {response.text}")
        expect(fake.calls == [], "the evidence_v1 adapter must never be called when no engine field is sent")


def test_unrecognized_engine_value_falls_back_to_legacy_safely() -> None:
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_success() as fake:
        _ensure_test_users()
        response = client.post("/analyze", data={"engine": "not_a_real_engine"}, headers=_auth_headers(USER_A))
        expect(response.status_code == 400, f"unrecognized engine must resolve to legacy's own validation: {response.status_code}")
        expect(fake.calls == [], "an unrecognized engine value must never reach the evidence_v1 adapter")


def test_evidence_v1_requested_but_server_flag_disabled_falls_back_to_legacy() -> None:
    """item 4: the client CANNOT authorize evidence_v1 merely by asking
    for it -- the server-side flag is the real boundary. Tests
    `resolve_engine()` directly, a pure function, rather than through a
    full HTTP round-trip -- routing this specific case through the real
    `/analyze` endpoint would fall through into the REAL, unmodified
    legacy pipeline (a genuine, paid OpenAI/Tavily run), which this test
    suite must never trigger. The adapter-not-called property for the
    HTTP-level 'server flag disabled' case is still covered end-to-end by
    every other evidence_v1 test in this file using a mocked adapter with
    the flag enabled; this test isolates the ONE additional claim those
    don't: that a disabled flag overrides the client's own request."""
    with _patched_evidence_v1_flag(False):
        resolved = ev1_config.resolve_engine("evidence_v1")
        expect(resolved == ev1_config.Engine.LEGACY, f"a disabled server flag must force legacy, got {resolved}")
    with _patched_evidence_v1_flag(True):
        resolved = ev1_config.resolve_engine("evidence_v1")
        expect(resolved == ev1_config.Engine.EVIDENCE_V1, f"an enabled server flag with an explicit request must resolve to evidence_v1, got {resolved}")


def test_evidence_v1_enabled_and_requested_invokes_the_adapter_and_persists() -> None:
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_success() as fake:
        _ensure_test_users()
        response = client.post(
            "/analyze",
            data={"engine": "evidence_v1", "company_name": "ZZTest Evidence Co", "website_url": "https://zztest-evidence.example"},
            headers=_auth_headers(USER_A),
        )
        expect(response.status_code == 200, f"expected success, got {response.status_code}: {response.text}")
        expect(fake.calls == [("ZZTest Evidence Co", "https://zztest-evidence.example")], f"adapter must receive the exact submitted company/website: {fake.calls}")

        body = response.json()
        expect(body["engine"] == "evidence_v1", body)
        expect(body["methodology_version"] == "evidence-engine-v1-candidate.1", body)
        expect(body["company_coverage_pct"] == 12.5, body)
        expect("analysis_id" in body and body["analysis_id"], "response must carry a stable analysis_id")

        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT owner_user_id, engine, methodology_version FROM evidence_v1_analyses WHERE id = :id"),
                {"id": body["analysis_id"]},
            ).mappings().first()
        expect(row is not None, "the analysis must actually be persisted")
        expect(row["owner_user_id"] == USER_A, row)
        expect(row["engine"] == "evidence_v1", row)
        expect(row["methodology_version"] == "evidence-engine-v1-candidate.1", row)
    _cleanup()


# --- 2. Unsupported Evidence-v1 input (item 7) --------------------------------

def test_evidence_v1_with_no_website_fails_clearly() -> None:
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_success() as fake:
        _ensure_test_users()
        response = client.post(
            "/analyze", data={"engine": "evidence_v1", "company_name": "ZZTest Co"}, headers=_auth_headers(USER_A),
        )
        expect(response.status_code == 400, response.text)
        expect(fake.calls == [], "adapter must never run without a website_url")
    _cleanup()


def test_evidence_v1_with_free_form_text_fails_clearly_rather_than_silently_ignoring_it() -> None:
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_success() as fake:
        _ensure_test_users()
        response = client.post(
            "/analyze",
            data={
                "engine": "evidence_v1", "company_name": "ZZTest Co", "website_url": "https://example.com",
                "company_text": "some free-form text",
            },
            headers=_auth_headers(USER_A),
        )
        expect(response.status_code == 400, response.text)
        expect("Evidence Engine v1" in response.json().get("detail", ""), response.text)
        expect(fake.calls == [], "adapter must never run with unsupported input silently dropped")
    _cleanup()


# --- 3. Provider-failure mapping (item 15) ------------------------------------

def test_evidence_v1_missing_credentials_maps_to_a_clear_non_leaking_error() -> None:
    """Uses the adapter's OWN real message format (`_require_provider_
    credentials()`'s "Evidence Engine v1 is not configured: missing
    X.") -- an env var NAME (never its value) is actionable operator
    information, not a secret; this test confirms the message is that
    clear, well-formed sentence, never a raw Python exception repr or a
    traceback fragment."""
    real_error = EvidenceV1AdapterError("Evidence Engine v1 is not configured: missing OPENAI_API_KEY.")
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_failure(real_error):
        _ensure_test_users()
        response = client.post(
            "/analyze",
            data={"engine": "evidence_v1", "company_name": "ZZTest Co", "website_url": "https://zztest-fail1.example"},
            headers=_auth_headers(USER_A),
        )
        expect(response.status_code == 502, response.text)
        detail = response.json().get("detail", "")
        expect(detail == "Evidence Engine v1 is not configured: missing OPENAI_API_KEY.", detail)
        expect("Traceback" not in detail and "File \"" not in detail, f"must never leak a raw traceback: {detail}")
    _cleanup()


def test_evidence_v1_pipeline_exception_maps_to_a_clear_error_never_a_raw_traceback() -> None:
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_failure(RuntimeError("simulated Tavily outage")):
        _ensure_test_users()
        response = client.post(
            "/analyze",
            data={"engine": "evidence_v1", "company_name": "ZZTest Co", "website_url": "https://zztest-fail2.example"},
            headers=_auth_headers(USER_A),
        )
        expect(response.status_code == 502, response.text)
        detail = response.json().get("detail", "")
        expect("simulated Tavily outage" not in detail, f"raw exception text must never reach the client: {detail}")
        expect("traceback" not in detail.lower(), detail)
    _cleanup()


# --- 4. Authenticated, ownership-scoped retrieval (items 9/10/20) ------------

def test_unauthenticated_retrieval_is_rejected() -> None:
    response = client.get("/evidence-v1/analyses/some-id")
    expect(response.status_code == 401, response.text)


def test_owner_can_retrieve_their_own_analysis() -> None:
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_success():
        _ensure_test_users()
        submit = client.post(
            "/analyze",
            data={"engine": "evidence_v1", "company_name": "ZZTest Owner Co", "website_url": "https://zztest-owner.example"},
            headers=_auth_headers(USER_A),
        )
        analysis_id = submit.json()["analysis_id"]

        response = client.get(f"/evidence-v1/analyses/{analysis_id}", headers=_auth_headers(USER_A))
        expect(response.status_code == 200, response.text)
        expect(response.json()["company_name"] == "ZZTest Owner Co", response.text)
    _cleanup()


def test_cross_user_retrieval_is_a_non_leaking_404_not_403() -> None:
    """item 9/20: ownership is by analysis ID + authenticated identity,
    never company name -- a different user gets the SAME 404 a
    nonexistent id would give, never a distinguishing 403."""
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_success():
        _ensure_test_users()
        submit = client.post(
            "/analyze",
            data={"engine": "evidence_v1", "company_name": "ZZTest CrossUser Co", "website_url": "https://zztest-crossuser.example"},
            headers=_auth_headers(USER_A),
        )
        analysis_id = submit.json()["analysis_id"]

        as_other_user = client.get(f"/evidence-v1/analyses/{analysis_id}", headers=_auth_headers(USER_B))
        as_nonexistent = client.get("/evidence-v1/analyses/definitely-not-a-real-id", headers=_auth_headers(USER_B))
        expect(as_other_user.status_code == 404, f"a non-owner must get 404, got {as_other_user.status_code}")
        expect(as_nonexistent.status_code == 404, "a nonexistent id must also be 404")
        expect(
            as_other_user.json() == as_nonexistent.json(),
            "the response body must be indistinguishable between 'not yours' and 'does not exist'",
        )
    _cleanup()


def test_analysis_not_found_is_404() -> None:
    with _patched_auth():
        _ensure_test_users()
        response = client.get("/evidence-v1/analyses/nonexistent-analysis-id", headers=_auth_headers(USER_A))
        expect(response.status_code == 404, response.text)


def test_my_evidence_v1_analyses_lists_only_the_caller_s_own_rows() -> None:
    with _patched_auth(), _patched_evidence_v1_flag(True), _patched_adapter_success():
        _ensure_test_users()
        client.post(
            "/analyze",
            data={"engine": "evidence_v1", "company_name": "ZZTest List A", "website_url": "https://zztest-lista.example"},
            headers=_auth_headers(USER_A),
        )
        client.post(
            "/analyze",
            data={"engine": "evidence_v1", "company_name": "ZZTest List B", "website_url": "https://zztest-listb.example"},
            headers=_auth_headers(USER_B),
        )

        response_a = client.get("/me/analyses/evidence-v1", headers=_auth_headers(USER_A))
        names_a = [row["company_name"] for row in response_a.json()]
        expect("ZZTest List A" in names_a, names_a)
        expect("ZZTest List B" not in names_a, f"user A must never see user B's analyses: {names_a}")
    _cleanup()


# --- 5. Legacy compatibility (item 17) ----------------------------------------

def test_legacy_request_with_no_engine_field_is_completely_unaffected() -> None:
    """A minimal, targeted confirmation alongside the full existing
    app/tests/test_analyze_unified.py suite (already re-run and passing
    unchanged, see the Task 31 completion report) -- proves the new
    `engine`/`company_name` Form fields are purely additive."""
    with _patched_auth():
        _ensure_test_users()
        response = client.post("/analyze", data={}, headers=_auth_headers(USER_A))
        expect(response.status_code == 400, response.text)
        expect("Provide at least one of" in response.json().get("detail", ""), response.json())


TESTS = [
    test_no_engine_field_defaults_to_legacy_and_does_not_touch_evidence_v1_adapter,
    test_unrecognized_engine_value_falls_back_to_legacy_safely,
    test_evidence_v1_requested_but_server_flag_disabled_falls_back_to_legacy,
    test_evidence_v1_enabled_and_requested_invokes_the_adapter_and_persists,
    test_evidence_v1_with_no_website_fails_clearly,
    test_evidence_v1_with_free_form_text_fails_clearly_rather_than_silently_ignoring_it,
    test_evidence_v1_missing_credentials_maps_to_a_clear_non_leaking_error,
    test_evidence_v1_pipeline_exception_maps_to_a_clear_error_never_a_raw_traceback,
    test_unauthenticated_retrieval_is_rejected,
    test_owner_can_retrieve_their_own_analysis,
    test_cross_user_retrieval_is_a_non_leaking_404_not_403,
    test_analysis_not_found_is_404,
    test_my_evidence_v1_analyses_lists_only_the_caller_s_own_rows,
    test_legacy_request_with_no_engine_field_is_completely_unaffected,
]


def main() -> None:
    print("\nTask 31: Evidence Engine v1 product integration tests")
    print("-" * 72)
    passed = 0
    failed = 0
    try:
        for test in TESTS:
            try:
                test()
                print(f"PASS  {test.__name__}")
                passed += 1
            except AssertionError as error:
                print(f"FAIL  {test.__name__}\n      {error}")
                failed += 1
            except Exception as error:  # noqa: BLE001
                print(f"ERROR {test.__name__}\n      {error!r}")
                failed += 1
    finally:
        _cleanup()

    print("-" * 72)
    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
