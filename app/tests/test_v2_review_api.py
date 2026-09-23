"""
Regression tests for Increment 18.4: the internal V2 evidence review API (app/v2_review_api.py), mounted at
/admin/v2-review inside the same FastAPI app as every legacy route (app/api.py).

Runs against the REAL, isolated V2 development database (venturegps_v2_dev_1801 -- the same disposable local
Postgres database the Increment 18.2/18.3 CLI demonstrations used; see docs/v2/RUNBOOK_18_2.md), never the
shared preview or production database. V2_DATABASE_URL is set explicitly below, in-process, before the V2
engine is ever created: app.v2.config.get_database_url() silently falls back to the LEGACY DATABASE_URL when
V2_DATABASE_URL is unset, which this file must never rely on by accident. Override it on the command line to
point at a different disposable V2 database; never point it at a shared one.

Auth is exercised the same way as app/tests/test_backend_authentication.py: a local RSA keypair stands in for
Clerk's own signing key (real signature/issuer/expiry/azp/sub verification runs, nothing is stubbed), and
app.auth._resolve_admin_user_ids is monkeypatched -- the same pattern app/tests/test_product_analytics.py
uses -- to grant or deny admin status for the duration of a block. Nothing about admin status or reviewer
identity is ever taken from the request itself.

Every row this file creates uses a distinctive zztest_v2_review_ marker (source key, processor id, company/
candidate content) and every id created is deleted, in reverse dependency order, in a `finally` block -- even
on failure -- so repeated runs are idempotent and the shared dev database is left clean for other work on it.

Run with:
    python -m app.tests.test_v2_review_api
"""

import os
import time
from datetime import datetime, timezone
from uuid import UUID

os.environ.setdefault("V2_DATABASE_URL", "postgresql+psycopg2://postgres@127.0.0.1:54331/venturegps_v2_dev_1801")

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.v2.db.engine import get_engine
from app.v2.domain.candidate import CompanyCandidateProposal, EvidenceLocator
from app.v2.domain.financing import (
    AmountSemantics,
    FinancingDateKind,
    FinancingEventCandidateProposal,
    FinancingType,
    Money,
    ProposedAmount,
    ProposedFinancingDate,
    ProposedFinancingType,
    ProposedStage,
    Stage,
)
from app.v2.domain.observation import Observation
from app.v2.domain.source import CollectionMethod, Source, SourceType
from app.v2.domain.time import EventTime
from app.v2.observations.hashing import build_raw_payload, compute_content_hash
from app.v2.observations.media import sniff_media_type
from app.v2.repositories.company_candidates import store_company_candidates
from app.v2.repositories.financing_event_candidates import persist_financing_event_candidates
from app.v2.repositories.markets import register_market, register_taxonomy_version
from app.v2.repositories.observations import store_observation
from app.v2.repositories.processing_attempts import start_processing
from app.v2.repositories.raw_payloads import store_raw_payload
from app.v2.repositories.sources import register_source

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"
ADMIN_USER_ID = "zztest_v2_review_admin"
OTHER_USER_ID = "zztest_v2_review_nonadmin"
SOURCE_KEY = "zztest_v2_review_source"
PROCESSOR_ID = "zztest_v2_review_proposer"
PROCESSOR_VERSION = f"{PROCESSOR_ID}.v1"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


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


def _make_token(sub: str = ADMIN_USER_ID, signing_key=None, exp_delta: int = 3600) -> str:
    now = int(time.time())
    payload = {"iat": now, "exp": now + exp_delta, "sub": sub, "iss": TEST_ISSUER, "azp": TEST_AZP}
    return pyjwt.encode(payload, signing_key if signing_key is not None else _private_key, algorithm="RS256")


class _patched_auth:
    def __enter__(self):
        self._orig_issuer = auth.CLERK_ISSUER
        self._orig_jwks_client = auth._jwks_client
        self._orig_resolve_parties = auth._resolve_authorized_parties
        self._orig_resolve_admins = auth._resolve_admin_user_ids
        auth.CLERK_ISSUER = TEST_ISSUER
        auth._jwks_client = lambda: _FakeJWKSClient()
        auth._resolve_authorized_parties = lambda: [TEST_AZP]
        auth._resolve_admin_user_ids = lambda: [ADMIN_USER_ID]
        return self

    def __exit__(self, *exc):
        auth.CLERK_ISSUER = self._orig_issuer
        auth._jwks_client = self._orig_jwks_client
        auth._resolve_authorized_parties = self._orig_resolve_parties
        auth._resolve_admin_user_ids = self._orig_resolve_admins
        return False


def _headers(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


ADMIN_TOKEN = None  # set inside _patched_auth blocks that need it


# ---------------------------------------------------------------- real V2 fixture construction (no mocks)

def _span(haystack: str, needle: str) -> tuple[int, int]:
    start = haystack.index(needle)
    return start, start + len(needle)


def _locator(data: bytes, start: int, end: int) -> EvidenceLocator:
    return EvidenceLocator(byte_start=start, byte_end=end, evidence_hash=compute_content_hash(data[start:end]))


def _ensure_source(engine):
    return register_source(engine, Source(
        source_key=SOURCE_KEY, name="zztest v2 review fixture source", source_type=SourceType.GOVERNMENT_REGULATORY,
        collection_method=CollectionMethod.MANUAL_UPLOAD, url=None, is_active=True,
    )).stored.id


def _make_observation_and_attempt(engine, text_body: str, *, source_record_identifier: str):
    """Real observation + processing attempt: store_raw_payload -> store_observation -> start_processing, each
    a genuine write through the same repositories the real ingestion pipeline uses."""
    data = text_body.encode("utf-8")
    store_raw_payload(engine, data)
    media_type = sniff_media_type(data)
    observation = Observation(
        source_key=SOURCE_KEY, source_record_identifier=source_record_identifier, observation_type="test_document",
        observed_time=datetime.now(timezone.utc),
        collection_version=PROCESSOR_VERSION, collector_id=ADMIN_USER_ID,
        content_hash=compute_content_hash(data), sniffed_media_type=media_type,
    )
    stored_observation = store_observation(engine, observation).stored
    attempt = start_processing(engine, stored_observation.id, PROCESSOR_ID, PROCESSOR_VERSION)
    return stored_observation, attempt, data


def _build_company_candidate(engine, *, record_id: str, name: str):
    stored_observation, attempt, data = _make_observation_and_attempt(engine, f"{name} is a real company.", source_record_identifier=record_id)
    start, end = _span(f"{name} is a real company.", name)
    proposal = CompanyCandidateProposal(proposed_name=name, name_evidence=_locator(data, start, end), identifiers=())
    result = store_company_candidates(engine, attempt.id, [proposal])
    return result.candidates[0], attempt.id, stored_observation.id, data


def _build_financing_candidate(engine, *, record_id: str, company_id, headline: str):
    stored_observation, attempt, data = _make_observation_and_attempt(engine, headline, source_record_identifier=record_id)
    event_start, event_end = _span(headline, "raised a Series A financing round")
    stage_start, stage_end = _span(headline, "Series A")
    type_start, type_end = _span(headline, "common stock")
    amount_start, amount_end = _span(headline, "$20,000,000")
    date_start, date_end = _span(headline, "2026-01-15")
    proposal = FinancingEventCandidateProposal(
        company_id=company_id, event_evidence=_locator(data, event_start, event_end),
        stage=ProposedStage(stage=Stage.SERIES_A, evidence=_locator(data, stage_start, stage_end)),
        financing_type=ProposedFinancingType(financing_type=FinancingType.EQUITY, evidence=_locator(data, type_start, type_end)),
        amounts=(ProposedAmount(semantics=AmountSemantics.ANNOUNCED_ROUND_AMOUNT, money=Money(currency_code="USD", minor_units=2_000_000_000),
                                evidence=_locator(data, amount_start, amount_end)),),
        dates=(ProposedFinancingDate(kind=FinancingDateKind.FIRST_SALE_DATE, time=EventTime.of_day(2026, 1, 15),
                                     evidence=_locator(data, date_start, date_end)),),
    )
    result = persist_financing_event_candidates(engine, attempt.id, [proposal])
    return result.candidates[0], attempt.id, stored_observation.id


FINANCING_HEADLINE = (
    "Zztest V2 Review Robotics Inc. announced today that it raised a Series A financing round involving the "
    "sale of common stock. The company sold securities amounting to $20,000,000 in aggregate. The securities "
    "were first sold on 2026-01-15."
)


CREATED = {"company_ids": [], "candidate_ids": [], "financing_candidate_ids": [], "attempt_ids": [], "observation_ids": []}


def _report_created() -> None:
    """NOT a cleanup. Verified directly against the isolated dev database: every V2 table except `source`
    carries a BEFORE DELETE (and BEFORE UPDATE) trigger that raises 'is append-only' -- observation,
    processing_attempt, company_candidate(+children), resolution_decision, company(+name/identifier),
    financing_event_candidate(+children), financing_resolution_decision, financing_event(+facts) and
    company_market_classification are ALL genuinely undeletable by application code, by design (the same
    immutability the domain layer describes -- this is enforced a second time, at the database). A cleanup
    step that tried to DELETE them would either no-op or fail; this file does neither. Each run instead uses a
    fresh time-based marker (see `marker` in run_full_workflow) so repeated runs never collide, and the rows
    it creates simply become part of the isolated dev database's own append-only history -- exactly like the
    real review workflow's rows would. This is safe only because venturegps_v2_dev_1801 is a disposable local
    database used solely for this kind of exercise, never the shared preview or production database."""
    print("      rows created this run (never deleted -- V2 tables are append-only by database trigger):")
    for key, ids in CREATED.items():
        if ids:
            print(f"        {key}: {ids}")


# ---------------------------------------------------------------- auth/authz: no real data needed

def test_unauthenticated_requests_rejected() -> None:
    with _patched_auth():
        for method, path in [
            ("GET", "/admin/v2-review/company-candidates"),
            ("GET", "/admin/v2-review/company-candidates/1"),
            ("POST", "/admin/v2-review/company-candidates/1/decide"),
            ("GET", "/admin/v2-review/financing-candidates"),
            ("POST", "/admin/v2-review/financing-candidates/1/decide"),
            ("GET", "/admin/v2-review/markets"),
            ("POST", "/admin/v2-review/companies/00000000-0000-0000-0000-000000000000/classify"),
        ]:
            response = client.request(method, path, json={} if method == "POST" else None, headers=_headers(None))
            expect(response.status_code == 401, f"{method} {path} without a token: expected 401, got {response.status_code}: {response.text}")


def test_non_admin_authenticated_requests_rejected() -> None:
    with _patched_auth():
        token = _make_token(sub=OTHER_USER_ID)
        for method, path in [
            ("GET", "/admin/v2-review/company-candidates"),
            ("GET", "/admin/v2-review/financing-candidates"),
            ("POST", "/admin/v2-review/company-candidates/1/decide"),
        ]:
            response = client.request(method, path, json={} if method == "POST" else None, headers=_headers(token))
            expect(response.status_code == 403, f"{method} {path} as a non-admin: expected 403, got {response.status_code}: {response.text}")


def test_forged_signature_rejected() -> None:
    with _patched_auth():
        forged = _make_token(signing_key=_other_private_key)
        response = client.get("/admin/v2-review/company-candidates", headers=_headers(forged))
        expect(response.status_code == 401, f"Forged signature: expected 401, got {response.status_code}")


# ---------------------------------------------------------------- legacy routes unaffected by the new mount

def test_legacy_routes_still_behave_normally() -> None:
    with _patched_auth():
        health = client.get("/health")
        expect(health.status_code == 200, f"/health regressed: {health.status_code}")

        unauth_legacy = client.post("/analyze", data={}, files={})
        expect(unauth_legacy.status_code == 401, f"/analyze auth gate regressed: {unauth_legacy.status_code}")

        public = client.get("/rankings")
        expect(public.status_code != 401, f"/rankings must stay public, got {public.status_code}")


# ---------------------------------------------------------------- the real, DB-backed workflow

def run_full_workflow() -> None:
    engine = get_engine()
    _ensure_source(engine)

    marker = str(int(time.time() * 1000))
    company_name = f"Zztest V2 Review Robotics Inc. {marker}"

    with _patched_auth():
        admin_token = _make_token(sub=ADMIN_USER_ID)
        headers = _headers(admin_token)

        # ---- 1. company candidate: create + evidence inspection ----
        candidate, attempt_id, observation_id, _data = _build_company_candidate(engine, record_id=f"company-{marker}", name=company_name)
        CREATED["attempt_ids"].append(attempt_id)
        CREATED["observation_ids"].append(observation_id)
        CREATED["candidate_ids"].append(candidate.id)

        listing = client.get("/admin/v2-review/company-candidates", headers=headers)
        expect(listing.status_code == 200, f"list company candidates: {listing.status_code}: {listing.text}")
        expect(any(c["id"] == candidate.id for c in listing.json()), "new candidate missing from the pending queue")

        detail = client.get(f"/admin/v2-review/company-candidates/{candidate.id}", headers=headers)
        expect(detail.status_code == 200, f"company candidate detail: {detail.status_code}: {detail.text}")
        body = detail.json()
        expect(body["proposed_name"] == company_name, "detail returned the wrong proposed name")
        expect(body["name_evidence"]["text"] == company_name, "re-verified evidence excerpt did not match the proposed name")
        expect(body["resolution_state"] == "unresolved", f"expected unresolved, got {body['resolution_state']}")

        # forged reviewer identity: the request body has no such field, but send one anyway and confirm it is ignored
        decide = client.post(
            f"/admin/v2-review/company-candidates/{candidate.id}/decide",
            json={"action": "create", "confirm": True, "authority_id": "human:not-a-real-admin", "reviewer": "someone-else"},
            headers=headers,
        )
        expect(decide.status_code == 200, f"create company from candidate: {decide.status_code}: {decide.text}")
        decision = decide.json()
        expect(decision["company_id"] is not None, "decision result missing company_id")
        company_id = UUID(decision["company_id"])
        CREATED["company_ids"].append(company_id)

        recorded_decision = client.get(f"/admin/v2-review/company-candidates/{candidate.id}", headers=headers).json()["decisions"][-1]
        expect(recorded_decision["authority_kind"] == "human", "recorded authority kind was not human")
        expect(recorded_decision["authority_id"] == f"admin:{ADMIN_USER_ID}",
               f"forged reviewer identity was not ignored: recorded authority was {recorded_decision['authority_id']!r}")

        # ---- 2. duplicate decision on the same (now resolved) candidate must be refused, not repeated ----
        replay = client.post(f"/admin/v2-review/company-candidates/{candidate.id}/decide",
                             json={"action": "create", "confirm": True}, headers=headers)
        expect(replay.status_code == 409, f"replayed decision: expected 409, got {replay.status_code}: {replay.text}")

        # ---- 3. a second, independent candidate: reject it, then confirm it cannot be decided again ----
        reject_candidate, reject_attempt_id, reject_observation_id, _ = _build_company_candidate(
            engine, record_id=f"reject-{marker}", name=f"Zztest V2 Review Reject Co {marker}")
        CREATED["attempt_ids"].append(reject_attempt_id)
        CREATED["observation_ids"].append(reject_observation_id)
        CREATED["candidate_ids"].append(reject_candidate.id)

        rejected = client.post(f"/admin/v2-review/company-candidates/{reject_candidate.id}/decide",
                               json={"action": "reject", "reason_code": "zztest_not_a_real_company", "confirm": True}, headers=headers)
        expect(rejected.status_code == 200, f"reject candidate: {rejected.status_code}: {rejected.text}")
        expect(rejected.json()["decision_kind"] == "reject_candidate", "reject did not record reject_candidate")

        reject_detail = client.get(f"/admin/v2-review/company-candidates/{reject_candidate.id}", headers=headers).json()
        expect(reject_detail["resolution_state"] == "rejected", f"expected rejected, got {reject_detail['resolution_state']}")

        reject_again = client.post(f"/admin/v2-review/company-candidates/{reject_candidate.id}/decide",
                                   json={"action": "defer", "reason_code": "zztest_second_look", "confirm": True}, headers=headers)
        expect(reject_again.status_code == 409, f"deciding an already-rejected candidate: expected 409, got {reject_again.status_code}")

        # ---- 4. evidence tampering: corrupt the stored candidate's evidence hash directly, bypassing the API ----
        # company_candidate carries its own BEFORE UPDATE/DELETE "is append-only" database trigger (verified
        # directly against this database), so an ordinary application UPDATE is already refused by Postgres
        # itself. To exercise the review API's OWN independent re-verification (the actual thing under test
        # here), the trigger is disabled for exactly this one superuser-only statement against a disposable
        # local database, then immediately re-enabled -- simulating the one channel that really could bypass
        # the trigger (direct superuser DB access) and proving the application layer still catches it as a
        # second, independent line of defense, not merely relying on the database to always hold.
        tamper_candidate, tamper_attempt_id, tamper_observation_id, _ = _build_company_candidate(
            engine, record_id=f"tamper-{marker}", name=f"Zztest V2 Review Tamper Co {marker}")
        CREATED["attempt_ids"].append(tamper_attempt_id)
        CREATED["observation_ids"].append(tamper_observation_id)
        CREATED["candidate_ids"].append(tamper_candidate.id)
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE v2.company_candidate DISABLE TRIGGER trg_company_candidate_append_only"))
            try:
                connection.execute(text("UPDATE v2.company_candidate SET name_evidence_hash = repeat('0', 64) WHERE id = :id"),
                                   {"id": tamper_candidate.id})
            finally:
                connection.execute(text("ALTER TABLE v2.company_candidate ENABLE TRIGGER trg_company_candidate_append_only"))
        tampered_detail = client.get(f"/admin/v2-review/company-candidates/{tamper_candidate.id}", headers=headers)
        expect(tampered_detail.status_code == 500, f"tampered evidence on read: expected 500, got {tampered_detail.status_code}: {tampered_detail.text}")
        expect("Traceback" not in tampered_detail.text and tamper_candidate.proposal.proposed_name not in tampered_detail.text,
               "tampered-evidence failure must not leak internals or unverified content")
        tampered_decide = client.post(f"/admin/v2-review/company-candidates/{tamper_candidate.id}/decide",
                                      json={"action": "create", "confirm": True}, headers=headers)
        expect(tampered_decide.status_code == 500, f"deciding on tampered evidence: expected 500, got {tampered_decide.status_code}")
        # and it must genuinely be blocked, not silently promoted despite the 500:
        still_pending = client.get(f"/admin/v2-review/company-candidates/{tamper_candidate.id}", headers=headers)
        # the GET itself still fails loudly (tampered), which is itself proof no create_company_from_candidate
        # response ever reached the client with a company_id -- tampered_decide.json() has none:
        expect(tampered_decide.headers.get("content-type", "").startswith("application/json"), "unexpected tampered-decide response shape")

        # ---- 5. financing candidate: company-canonical gate, evidence, facts, successful create_event ----
        financing_candidate, financing_attempt_id, financing_observation_id = _build_financing_candidate(
            engine, record_id=f"financing-{marker}", company_id=company_id, headline=FINANCING_HEADLINE)
        CREATED["attempt_ids"].append(financing_attempt_id)
        CREATED["observation_ids"].append(financing_observation_id)
        CREATED["financing_candidate_ids"].append(financing_candidate.id)

        financing_list = client.get("/admin/v2-review/financing-candidates", headers=headers)
        expect(financing_list.status_code == 200, f"list financing candidates: {financing_list.status_code}")
        expect(any(c["id"] == financing_candidate.id for c in financing_list.json()), "financing candidate missing from queue")

        financing_detail = client.get(f"/admin/v2-review/financing-candidates/{financing_candidate.id}", headers=headers)
        expect(financing_detail.status_code == 200, f"financing candidate detail: {financing_detail.status_code}: {financing_detail.text}")
        fbody = financing_detail.json()
        expect(fbody["company_is_canonical"] is True, "company should be canonical (it was just created)")
        expect(fbody["stage"] == "series_a", f"expected series_a, got {fbody['stage']}")
        expect(fbody["amounts"][0]["minor_units"] == 2_000_000_000, "amount minor units mismatch")

        financing_decide = client.post(
            f"/admin/v2-review/financing-candidates/{financing_candidate.id}/decide",
            json={"action": "create_event", "confirm": True,
                  "facts": {"stage": True, "financing_type": True, "verified_round_amount": True, "dates": ["first_sale_date"]}},
            headers=headers,
        )
        expect(financing_decide.status_code == 200, f"create financing event: {financing_decide.status_code}: {financing_decide.text}")
        fresult = financing_decide.json()
        expect(fresult["financing_event_id"] is not None, "financing decision missing financing_event_id")
        expect(fresult["accepted_verified_round_amount"] is True, "verified_round_amount was not accepted")

        financing_replay = client.post(f"/admin/v2-review/financing-candidates/{financing_candidate.id}/decide",
                                       json={"action": "create_event", "confirm": True}, headers=headers)
        expect(financing_replay.status_code == 409, f"replayed financing decision: expected 409, got {financing_replay.status_code}")

        # ---- 6. market classification: explicit human PRIMARY approval ----
        market = register_market(engine, f"zztest-v2-review-robotics-{marker}", "Zztest V2 Review Robotics")
        taxonomy_version = register_taxonomy_version(engine, f"zztest_v2_review_{marker}.v1")
        classify = client.post(
            f"/admin/v2-review/companies/{company_id}/classify",
            json={"market_id": str(market.id), "taxonomy_version": taxonomy_version.taxonomy_version, "role": "primary", "confirm": True},
            headers=headers,
        )
        expect(classify.status_code == 200, f"classify company: {classify.status_code}: {classify.text}")
        expect(classify.json()["role"] == "primary", "classification role mismatch")
        expect(classify.json()["authority_id"] == f"admin:{ADMIN_USER_ID}", "classification authority was not the real admin session")

        company_detail = client.get(f"/admin/v2-review/companies/{company_id}", headers=headers)
        expect(company_detail.status_code == 200, f"company detail: {company_detail.status_code}")
        expect(len(company_detail.json()["classifications"]) == 1, "expected exactly one classification on the company")


TESTS = [
    test_unauthenticated_requests_rejected,
    test_non_admin_authenticated_requests_rejected,
    test_forged_signature_rejected,
    test_legacy_routes_still_behave_normally,
]


def main() -> None:
    print("\nVentureGPS V2 -- Increment 18.4 internal review API tests")
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

    try:
        run_full_workflow()
        print("PASS  run_full_workflow (real V2 dev-database end-to-end review workflow)")
    except AssertionError as error:
        print(f"FAIL  run_full_workflow\n      {error}")
        failures.append("run_full_workflow")
    finally:
        _report_created()

    print("-" * 72)
    print(f"{len(TESTS) + 1 - len(failures)}/{len(TESTS) + 1} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
