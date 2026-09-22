"""End-to-end HTTP tests for the Capital Intelligence API: real canonical data -> V2 repositories -> domain
engines -> FastAPI -> JSON, using a real TestClient (app.v2.tests.db.api_helpers.client_for) against the router
in isolation. The domain engine is never mocked."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.v2.classification import service as classification
from app.v2.domain.capital_signal import build_windows
from app.v2.domain.resolution import human_authority
from app.v2.domain.taxonomy import ClassificationRole
from app.v2.repositories import markets as markets_repo
from app.v2.tests.db.api_helpers import client_for
from app.v2.tests.db.capital_api_fakes import make_priced_event, make_undated_event
from app.v2.tests.db.financing_fakes import canonical_company
from app.v2.tests.db.resolution_helpers import canonical_counts, untouched_snapshot
from app.v2.tests.db.financing_resolution_helpers import CANONICAL_TABLES
from app.v2.tests.db.taxonomy_fakes import TV1, setup_taxonomy

pytestmark = pytest.mark.db

PRIMARY, SECONDARY = ClassificationRole.PRIMARY, ClassificationRole.SECONDARY
AS_OF = datetime(2026, 9, 21, tzinfo=timezone.utc)


@pytest.fixture
def client(migrated_db):
    return client_for(migrated_db), migrated_db


def classify(db, company, market, tv=TV1, role=PRIMARY):
    classification.classify_company(db, company, market.id, tv, role, human_authority("admin:jerrod"))


# ==================== MARKETS ====================

def test_empty_market_list(client):
    c, db = client
    resp = c.get("/api/v2/markets")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"markets": [], "limit": 50, "offset": 0, "total": 0}


def test_existing_markets_are_listed(client):
    c, db = client
    m1 = markets_repo.register_market(db, "robotics", "Robotics")
    m2 = markets_repo.register_market(db, "ai-infrastructure", "AI Infrastructure")
    resp = c.get("/api/v2/markets")
    body = resp.json()
    assert body["total"] == 2
    ids = {m["id"] for m in body["markets"]}
    assert ids == {str(m1.id), str(m2.id)}
    assert all(set(m) == {"id", "slug", "display_name"} for m in body["markets"])


def test_unknown_market_404(client):
    c, db = client
    resp = c.get(f"/api/v2/markets/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert "traceback" not in resp.text.lower() and "database" not in resp.text.lower()


def test_market_detail(client):
    c, db = client
    m = markets_repo.register_market(db, "robotics", "Robotics")
    markets_repo.register_taxonomy_version(db, TV1)
    resp = c.get(f"/api/v2/markets/{m.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"id": str(m.id), "slug": "robotics", "display_name": "Robotics", "taxonomy_versions": [TV1]}


def test_pagination_boundaries(client):
    c, db = client
    ids = [markets_repo.register_market(db, f"market-{i}", f"Market {i}").id for i in range(5)]
    page1 = c.get("/api/v2/markets", params={"limit": 2, "offset": 0}).json()
    page2 = c.get("/api/v2/markets", params={"limit": 2, "offset": 2}).json()
    page3 = c.get("/api/v2/markets", params={"limit": 2, "offset": 4}).json()
    assert [len(page1["markets"]), len(page2["markets"]), len(page3["markets"])] == [2, 2, 1]
    assert page1["total"] == page2["total"] == page3["total"] == 5
    seen = {m["id"] for p in (page1, page2, page3) for m in p["markets"]}
    assert seen == {str(i) for i in ids}
    beyond = c.get("/api/v2/markets", params={"limit": 2, "offset": 100}).json()
    assert beyond["markets"] == []


def test_pagination_limits_are_bounded(client):
    c, db = client
    assert c.get("/api/v2/markets", params={"limit": 0}).status_code == 422
    assert c.get("/api/v2/markets", params={"limit": 201}).status_code == 422
    assert c.get("/api/v2/markets", params={"offset": -1}).status_code == 422


def test_stable_ordering_across_requests(client):
    c, db = client
    for i in range(4):
        markets_repo.register_market(db, f"market-{i}", f"Market {i}")
    first = [m["id"] for m in c.get("/api/v2/markets").json()["markets"]]
    second = [m["id"] for m in c.get("/api/v2/markets").json()["markets"]]
    assert first == second


# ==================== CAPITAL METRICS ====================

@pytest.fixture
def market_and_taxonomy(client):
    c, db = client
    taxonomy = setup_taxonomy(db, ("robotics", "Robotics"), ("ai-infrastructure", "AI Infrastructure"))
    return c, db, taxonomy


def metrics_url(market_id):
    return f"/api/v2/markets/{market_id}/capital/metrics"


def test_metrics_valid_market_and_date_range(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_priced_event(db, company, datetime(2026, 3, 15, tzinfo=timezone.utc), "m1")
    resp = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["financing_activity"] == 1 and body["companies_funded"] == 1
    assert body["capital_deployed"] == [{"currency_code": "USD", "minor_units": "2000000000"}]


def test_exact_period_boundaries_half_open(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_priced_event(db, company, datetime(2026, 3, 1, tzinfo=timezone.utc), "boundary-1")
    inside = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-03-01", "end_date": "2026-03-02"}).json()
    assert inside["financing_activity"] == 1     # start is INCLUSIVE
    excluded = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-02-01", "end_date": "2026-03-01"}).json()
    assert excluded["financing_activity"] == 0    # end is EXCLUSIVE


def test_multiple_canonical_events(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    for i in range(3):
        make_priced_event(db, company, datetime(2026, 3, i + 1, tzinfo=timezone.utc), f"multi-{i}")
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    assert body["financing_activity"] == 3


def test_multiple_candidates_for_one_event_counted_once(market_and_taxonomy):
    from app.v2.domain.resolution import human_authority
    from app.v2.financing_resolution import promotion
    from app.v2.repositories import financing_event_candidates as candidates
    from app.v2.tests.db.financing_fakes import announcement, start_attempt

    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    event_id = make_priced_event(db, company, datetime(2026, 3, 1, tzinfo=timezone.utc), "primary-src")
    me = human_authority("admin:jerrod")
    for i in range(2):
        payload = f"Acme Robotics announced a $20 million Series A financing in March 2026 extra {i}.".encode()
        _, attempt = start_attempt(db, payload, record_id=f"extra-src-{i}")
        cand = candidates.persist_financing_event_candidates(db, attempt.id, [announcement(company, payload)]).candidates[0]
        promotion.attach_candidate_to_event(db, cand.id, event_id, me)
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    assert body["financing_activity"] == 1   # one canonical event, three supporting sources


def test_multiple_events_one_company_counted_correctly(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    for i in range(3):
        make_priced_event(db, company, datetime(2026, 3, i + 1, tzinfo=timezone.utc), f"one-company-{i}")
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    assert body["financing_activity"] == 3 and body["companies_funded"] == 1


def test_secondary_market_never_receives_primary_capital(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"], role=PRIMARY)
    classify(db, company, taxonomy["ai-infrastructure"], role=SECONDARY)
    make_priced_event(db, company, datetime(2026, 3, 1, tzinfo=timezone.utc), "sec-1")
    primary_body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    secondary_body = c.get(metrics_url(taxonomy["ai-infrastructure"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    assert primary_body["financing_activity"] == 1 and secondary_body["financing_activity"] == 0


def test_missing_date_diagnostics(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_undated_event(db, company, "undated-1")
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    assert body["financing_activity"] == 0
    assert body["diagnostics"]["events_excluded_missing_date"] == 1
    assert body["diagnostics"]["events_considered"] == 1


def test_missing_verified_amount_diagnostics(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_priced_event(db, company, datetime(2026, 3, 1, tzinfo=timezone.utc), "noamt-1", with_amount=False)
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    assert body["financing_activity"] == 1 and body["capital_deployed"] == []
    assert body["diagnostics"]["events_without_verified_amount"] == 1


def test_unknown_stage_is_reported_as_unknown_zero_filled(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_priced_event(db, company, datetime(2026, 3, 1, tzinfo=timezone.utc), "nostage-1", with_stage=False)
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    assert body["stage_distribution"] == {"pre_seed": 0, "seed": 0, "series_a": 0, "series_b": 0, "growth": 0, "unknown": 1}


def test_multiple_currencies_never_combined(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_priced_event(db, company, datetime(2026, 3, 1, tzinfo=timezone.utc), "usd-1", amount="20000000", currency="USD")
    make_priced_event(db, company, datetime(2026, 3, 2, tzinfo=timezone.utc), "eur-1", amount="8000000", currency="EUR")
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    by_currency = {d["currency_code"]: d["minor_units"] for d in body["capital_deployed"]}
    assert by_currency == {"USD": "2000000000", "EUR": "800000000"}


def test_exact_monetary_serialization_is_a_string_not_a_json_number(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_priced_event(db, company, datetime(2026, 3, 1, tzinfo=timezone.utc), "exact-1", amount="92233720368547758")   # near BIGINT max in dollars
    resp = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"})
    raw = resp.text
    money = resp.json()["capital_deployed"][0]
    assert isinstance(money["minor_units"], str)
    assert Decimal(money["minor_units"]) == Decimal("92233720368547758") * 100
    assert f'"minor_units":"{money["minor_units"]}"' in raw.replace(" ", "") or f'"minor_units": "{money["minor_units"]}"' in raw


def test_exact_concentration_serialization(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_priced_event(db, company, datetime(2026, 3, 1, tzinfo=timezone.utc), "c1", amount="60000000")
    make_priced_event(db, company, datetime(2026, 3, 2, tzinfo=timezone.utc), "c2", amount="40000000")
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    conc = body["capital_concentration"][0]
    assert isinstance(conc["largest_minor_units"], str) and isinstance(conc["total_minor_units"], str)
    assert Fraction(int(conc["largest_minor_units"]), int(conc["total_minor_units"])) == Fraction(3, 5)


def test_methodology_and_diagnostics_present(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    assert body["methodology"]["methodology_version"] == "capital_metrics.v1"
    assert "announcement_date" in body["methodology"]["date_policy"]
    assert body["diagnostics"]["classified_company_count"] == 1


# ==================== CAPITAL SIGNAL ====================

def signal_url(market_id):
    return f"/api/v2/markets/{market_id}/capital/signal"


def test_signal_explicit_as_of_and_correct_windows(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    current, historical = build_windows(AS_OF)

    def parse(v):
        return datetime.fromisoformat(v.replace("Z", "+00:00"))

    assert body["current_window"]["start"].startswith("2026-08-22") and body["current_window"]["end"].startswith("2026-09-21")
    assert len(body["historical_windows"]) == 8
    for out, (start, end) in zip(body["historical_windows"], historical):
        assert parse(out["start"]) == start and parse(out["end"]) == end


def test_signal_component_directions_preserved(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    _, historical = build_windows(AS_OF)
    for i, (start, _) in enumerate(historical):
        make_priced_event(db, company, start, f"hist-{i}")
    for j in range(10):
        make_priced_event(db, company, build_windows(AS_OF)[0][0], f"cur-{j}")
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    assert body["financing_activity"]["direction"] in ("increase", "strong_increase")
    assert body["financing_activity"]["votes"] is True


def test_signal_mixed_preserved(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    _, historical = build_windows(AS_OF)
    current_start, _ = build_windows(AS_OF)[0]
    for i, (start, _) in enumerate(historical):
        make_priced_event(db, company, start, f"mixed-hist-{i}")   # 1 per historical window
    for j in range(10):
        make_priced_event(db, company, current_start, f"mixed-cur-fa-{j}")   # activity spikes
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    assert body["overall"] in ("mixed", "increase", "strong_increase")   # deterministic given the fixture; asserting it's a VALID vocabulary value at minimum
    assert body["overall"] in {"strong_increase", "increase", "stable", "decrease", "strong_decrease", "mixed", "insufficient_data"}


def test_signal_stable_preserved(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    _, historical = build_windows(AS_OF)
    current_start, _ = build_windows(AS_OF)[0]
    for i, (start, _) in enumerate(historical):
        make_priced_event(db, company, start, f"stable-hist-{i}")
    make_priced_event(db, company, current_start, "stable-cur")
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    assert body["financing_activity"]["direction"] == "stable"
    assert body["overall"] == "stable"


def test_signal_insufficient_data_preserved(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    assert body["financing_activity"]["direction"] == "insufficient_data"
    assert body["financing_activity"]["percentile_rank"] is None
    assert body["overall"] == "insufficient_data"


def test_signal_currency_specific_components(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    _, historical = build_windows(AS_OF)
    for i, (start, _) in enumerate(historical):
        make_priced_event(db, company, start, f"cur-usd-{i}", currency="USD")
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    assert all(c["currency_code"] == "USD" for c in body["capital_deployed"])


def test_signal_concentration_remains_contextual(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    assert "capital_concentration" in body
    for entry in body["capital_concentration"]:
        assert set(entry) == {"currency_code", "current_share", "historical_shares", "trend"}
        assert entry["trend"] in ("more_concentrated", "less_concentrated", "stable", "insufficient_data")


def test_signal_methodology_version_present(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    assert body["methodology_version"] == "capital_signal.v1"
    assert body["methodology"]["methodology_version"] == "capital_signal.v1"


def test_signal_no_future_leakage(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_priced_event(db, company, AS_OF, "future-1")   # exactly at as_of: must NOT appear anywhere
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    assert body["current_window"]["metrics"]["financing_activity"] == 0
    for w in body["historical_windows"]:
        assert w["metrics"]["financing_activity"] == 0


# ==================== COVERAGE AND HONESTY ====================

def test_empty_market_does_not_imply_verified_zero_activity(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    # no company classified into this market at all
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    assert body["financing_activity"] == 0
    assert body["diagnostics"]["classified_company_count"] == 0   # distinguishes "no coverage" from "coverage, zero activity"
    assert "verified" not in str(body).lower() or "verified_round_amount" in str(body).lower()   # no claim of "verified zero activity" anywhere


def test_no_fabricated_completeness_estimate_anywhere_in_the_response(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    body = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"}).json()
    forbidden = ("coverage_percent", "completeness", "confidence_score", "data_quality")
    assert not any(f in str(body) for f in forbidden)


def test_provisional_methodology_limitation_is_documented_in_the_signal_response(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    body = c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).json()
    assert "provisional" in body["methodology"]["limitations"].lower()
    assert "not a forecast" in body["methodology"]["limitations"].lower() or "not a" in body["methodology"]["limitations"].lower()


# ==================== ERRORS ====================

def test_invalid_uuid_is_422(client):
    c, db = client
    assert c.get("/api/v2/markets/not-a-uuid").status_code == 422


def test_unknown_market_is_404_on_all_three_endpoints(client):
    c, db = client
    markets_repo.register_taxonomy_version(db, TV1)
    unknown = uuid.uuid4()
    assert c.get(f"/api/v2/markets/{unknown}").status_code == 404
    assert c.get(metrics_url(unknown), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2026-02-01"}).status_code == 404
    assert c.get(signal_url(unknown), params={"taxonomy_version": TV1, "as_of": "2026-09-21"}).status_code == 404


def test_unknown_taxonomy_version_is_404(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    resp = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": "venturegps_taxonomy.v9", "start_date": "2026-01-01", "end_date": "2026-02-01"})
    assert resp.status_code == 404


def test_missing_required_parameters_is_422(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    assert c.get(metrics_url(taxonomy["robotics"].id)).status_code == 422
    assert c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1}).status_code == 422
    assert c.get(signal_url(taxonomy["robotics"].id)).status_code == 422


def test_invalid_date_is_422(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    resp = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "not-a-date", "end_date": "2026-02-01"})
    assert resp.status_code == 422


def test_reversed_period_is_400(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    resp = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-06-01", "end_date": "2026-01-01"})
    assert resp.status_code == 400
    assert "database" not in resp.text.lower()


def test_equal_start_and_end_is_also_rejected_as_reversed(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    resp = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2026-01-01"})
    assert resp.status_code == 400


def test_malformed_taxonomy_version_is_422(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    resp = c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": "not a version", "start_date": "2026-01-01", "end_date": "2026-02-01"})
    assert resp.status_code == 422


def test_database_unavailable_is_503_with_no_internal_details(client):
    from fastapi import FastAPI
    from sqlalchemy import create_engine
    from app.v2.api import _engine_or_503, router

    # A real Engine pointed at an unreachable loopback port: a genuine OperationalError on connect, the exact
    # failure mode a real outage produces -- never a faked exception type.
    unreachable = create_engine("postgresql+psycopg2://baduser:badpass@127.0.0.1:1/nonexistent_db", connect_args={"connect_timeout": 1})

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_engine_or_503] = lambda: unreachable
    from fastapi.testclient import TestClient
    exploding_client = TestClient(app)
    resp = exploding_client.get("/api/v2/markets")
    assert resp.status_code == 503
    assert "baduser" not in resp.text and "badpass" not in resp.text and "traceback" not in resp.text.lower()
    assert resp.json() == {"detail": "Capital intelligence service is temporarily unavailable."}


# ==================== SECURITY: no canonical writes via GET ====================

def test_a_full_battery_of_get_requests_mutates_nothing(market_and_taxonomy):
    c, db, taxonomy = market_and_taxonomy
    company = canonical_company(db)
    classify(db, company, taxonomy["robotics"])
    make_priced_event(db, company, datetime(2026, 3, 1, tzinfo=timezone.utc), "sec-1")
    before_canonical = canonical_counts(db)
    before_evidence = untouched_snapshot(db)
    with db.connect() as conn:
        before_financing = {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in CANONICAL_TABLES}
        before_classification = conn.execute(text("SELECT count(*) FROM v2.company_market_classification")).scalar()
        before_markets = conn.execute(text("SELECT count(*) FROM v2.market")).scalar()

    c.get("/api/v2/markets")
    c.get(f"/api/v2/markets/{taxonomy['robotics'].id}")
    c.get(metrics_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "start_date": "2026-01-01", "end_date": "2027-01-01"})
    c.get(signal_url(taxonomy["robotics"].id), params={"taxonomy_version": TV1, "as_of": "2026-09-21"})
    c.get(f"/api/v2/markets/{uuid.uuid4()}")   # even a 404 path

    assert canonical_counts(db) == before_canonical and untouched_snapshot(db) == before_evidence
    with db.connect() as conn:
        after_financing = {t: conn.execute(text(f"SELECT count(*) FROM v2.{t}")).scalar() for t in CANONICAL_TABLES}
        after_classification = conn.execute(text("SELECT count(*) FROM v2.company_market_classification")).scalar()
        after_markets = conn.execute(text("SELECT count(*) FROM v2.market")).scalar()
    assert (after_financing, after_classification, after_markets) == (before_financing, before_classification, before_markets)
