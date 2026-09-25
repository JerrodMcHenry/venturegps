"""
Regression tests for Compare Startups V1 --
app/database/db.py's get_startups_for_comparison(), and GET /compare in
app/api.py.

Real SQL against the real configured DATABASE_URL, same "no separate test
database" convention as test_discovery.py/test_saved_startups.py. Every
row here uses a distinctive "ZZTest Compare " company-name prefix, cleaned
up in a finally block even on failure.

No test here makes an LLM/Tavily call, and none touches
startup_memberships or Methodology v2 scoring logic -- comparison only
reads already-computed methodology JSONB and reshapes it.

Run with:
    python -m app.tests.test_compare
"""

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
import app.auth as auth
from app.auth import AuthenticatedUser, get_current_user
from app.ai.sie_v2_methodology import METHODOLOGY_VERSION
from app.database.db import (
    MAX_COMPARISON_STARTUPS,
    engine,
    get_or_create_startup,
    get_rankings,
    get_startups_for_comparison,
    save_analysis,
)

TEST_PREFIX = "ZZTest Compare"
# Portfolio Release Task 3B -- Secure Analysis Visibility:
# get_startups_for_comparison()/get_rankings() now require a viewer to
# scope by. This file's own job is comparison's dedup/ordering/pillar-
# preservation logic -- not the authorization feature itself, which has
# its own dedicated coverage in test_analysis_visibility.py and
# test_security_hardening.py's test_compare_now_requires_auth. Every
# DB-layer call below goes through an ADMIN viewer (bypasses the
# visibility filter entirely) so existing assertions keep testing exactly
# what they always tested. The API-layer (client.get("/compare", ...))
# tests instead use a scoped get_current_user() override (see main()) for
# the same reason test_discovery.py's own two API-layer tests do.
TEST_VIEWER = "zztest_compare_admin_viewer"


def _compare(ids: list[int]) -> list[dict]:
    return get_startups_for_comparison(ids, TEST_VIEWER, True)


class _authenticated_as_viewer:
    """Scoped get_current_user() override for the API-layer (client.get)
    tests below -- restored on exit even on failure, same shape as
    test_discovery.py's own two inline overrides, pulled into a small
    reusable context manager here since more call sites need it in this
    file.

    Also patches app.auth._resolve_admin_user_ids() so TEST_VIEWER is
    recognized as an admin through the REAL is_admin() call app.api.compare()
    makes -- overriding get_current_user() alone is not enough: this
    file's own _compare() DB-layer helper passes viewer_is_admin=True as a
    literal, but the real HTTP route resolves admin status for real (the
    same real ADMIN_USER_IDS-backed check every other authenticated route
    uses), and this test environment has no real ADMIN_USER_IDS set.
    Without this, TEST_VIEWER would be a genuine non-admin with no
    submitted analyses and no memberships -- correctly seeing nothing,
    which would make these tests fail for the RIGHT reason (the
    authorization fix working) while trying to test something else
    (comparison's own dedup/bounding/shape logic)."""

    def __enter__(self) -> "_authenticated_as_viewer":
        self._orig_resolve_admins = auth._resolve_admin_user_ids
        api.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id=TEST_VIEWER)
        auth._resolve_admin_user_ids = lambda: [TEST_VIEWER]
        return self

    def __exit__(self, *exc) -> bool:
        api.app.dependency_overrides.pop(get_current_user, None)
        auth._resolve_admin_user_ids = self._orig_resolve_admins
        return False


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


def _pillar(
    score: float | None,
    subscores: list[dict] | None = None,
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
) -> dict:
    return {
        "score": score,
        "confidence": "Medium",
        "summary": "Test summary.",
        "strengths": strengths or [],
        "weaknesses": weaknesses or [],
        "recommendations": [],
        "score_breakdown": {
            "pillar": "test",
            "score": score,
            "confidence": "Medium",
            "evidence_coverage": 80.0,
            "subscores": subscores or [],
        },
    }


def _methodology(
    sps: float,
    market_score: float | None = 7.0,
    team_score: float | None = 7.0,
    version: str | None = None,
    market_subscores: list[dict] | None = None,
) -> dict:
    return {
        "context": {
            "company_name": "placeholder",
            "industry": "ZZTest Compare Industry",
            "business_model": "ZZTest Compare Model",
            "company_stage": "ZZTest Compare Stage",
            "funding_stage": "ZZTest Compare Stage",
        },
        "startup_intelligence_score": sps,
        "market": _pillar(
            market_score,
            subscores=market_subscores
            or [
                {
                    "name": "Market Size",
                    "score": market_score,
                    "weight": 0.25,
                    "confidence": "Medium",
                    "evidence_status": "Observed" if market_score is not None else "Unavailable",
                    "rationale": "Test rationale.",
                    "recommendations": [],
                    "missing_information": [] if market_score is not None else ["Market sizing data"],
                }
            ],
        ),
        "team": _pillar(team_score),
        "product": _pillar(7.0),
        "execution": _pillar(7.0),
        "traction": _pillar(7.0),
        "financial_health": _pillar(7.0),
        "analysis_context": {
            "methodology_version": version if version is not None else METHODOLOGY_VERSION
        },
    }


def _save(company_name: str, methodology: dict | None) -> int:
    return save_analysis(
        company_text=f"Test company text for {company_name}",
        summary="s",
        risk_analysis="r",
        competitor_analysis="c",
        memo="m",
        structured_analysis={
            "company_name": company_name,
            "industry": "ZZTest Compare Industry",
            "stage": "ZZTest Compare Stage",
            "business_model": "ZZTest Compare Model",
        },
        investment_score={},
        founder_analysis={},
        market_analysis={},
        sources=[],
        traction_analysis={},
        market_score=None,
        team_score=None,
        product_score=None,
        competition_score=None,
        traction_score=None,
        financial_score=None,
        overall_score=None,
        recommendation=None,
        readiness_score=None,
        readiness_summary=None,
        methodology=methodology,
    )


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                DELETE FROM analyses
                WHERE startup_id IN (
                    SELECT id FROM startups WHERE normalized_name LIKE :pattern
                )
            """),
            {"pattern": f"{TEST_PREFIX.lower()}%"},
        )
        connection.execute(
            text("DELETE FROM startups WHERE normalized_name LIKE :pattern"),
            {"pattern": f"{TEST_PREFIX.lower()}%"},
        )


# --- 1-4: basic count handling ----------------------------------------------


def test_compare_two_valid_canonical_startups() -> None:
    ids = _seed_two()
    try:
        rows = _compare(ids)
        expect(len(rows) == 2, f"Expected 2 rows, got {len(rows)}")
    finally:
        _cleanup()


def test_compare_four_valid_startups() -> None:
    ids = []
    for i in range(4):
        name = f"{TEST_PREFIX} Four{i}"
        _save(name, _methodology(80.0))
        ids.append(get_or_create_startup(name))
    try:
        rows = _compare(ids)
        expect(len(rows) == 4, f"Expected 4 rows, got {len(rows)}")
    finally:
        _cleanup()


def test_one_startup_produces_useful_response_api_layer() -> None:
    ids = _seed_two()
    try:
        with _authenticated_as_viewer():
            response = client.get("/compare", params={"startups": str(ids[0])})
        expect(response.status_code == 400, f"Expected 400 for a single id, got {response.status_code}")
        expect(
            "at least" in response.json()["detail"].lower(),
            f"Expected a helpful message, got {response.json()}",
        )
    finally:
        _cleanup()


def test_more_than_four_startups_bounded_api_layer() -> None:
    ids = []
    for i in range(6):
        name = f"{TEST_PREFIX} Bound{i}"
        _save(name, _methodology(80.0))
        ids.append(get_or_create_startup(name))
    try:
        with _authenticated_as_viewer():
            response = client.get("/compare", params={"startups": ",".join(str(i) for i in ids)})
        expect(response.status_code == 200, f"Expected 200 (bounded, not rejected), got {response.status_code}")
        body = response.json()
        expect(
            len(body["startups"]) <= MAX_COMPARISON_STARTUPS,
            f"Expected at most {MAX_COMPARISON_STARTUPS} startups, got {len(body['startups'])}",
        )
    finally:
        _cleanup()


# --- 5-9: identity/dedup/exclusion/ordering ---------------------------------


def test_duplicate_ids_deduplicated_safely() -> None:
    ids = _seed_two()
    try:
        rows = _compare([ids[0], ids[1], ids[0]])
        expect(len(rows) == 2, f"Expected exactly 2 rows after dedup, got {len(rows)}")
    finally:
        _cleanup()


def test_invalid_startup_id_handled_cleanly() -> None:
    ids = _seed_two()
    try:
        rows = _compare([ids[0], 999_999_999, ids[1]])
        expect(len(rows) == 2, f"Expected the 2 valid rows, invalid id silently dropped; got {len(rows)}")

        with _authenticated_as_viewer():
            response = client.get("/compare", params={"startups": f"{ids[0]},999999999,{ids[1]}"})
        expect(response.status_code == 200, f"Expected 200, got {response.status_code}")
        expect(
            response.json()["missing_startup_ids"] == [999999999],
            f"Expected missing_startup_ids=[999999999], got {response.json()['missing_startup_ids']}",
        )
    finally:
        _cleanup()


def test_legacy_analysis_excluded() -> None:
    name = f"{TEST_PREFIX} Legacy"
    _save(name, _methodology(99.0, version="1.0"))
    startup_id = get_or_create_startup(name)
    try:
        rows = _compare([startup_id])
        expect(len(rows) == 0, f"A non-canonical analysis must never resolve; got {rows}")
    finally:
        _cleanup()


def test_latest_canonical_analysis_selected() -> None:
    name = f"{TEST_PREFIX} Latest"
    _save(name, _methodology(40.0))
    startup_id = get_or_create_startup(name)
    _save(name, _methodology(95.0))
    try:
        rows = _compare([startup_id])
        expect(len(rows) == 1, f"Expected exactly one row, got {len(rows)}")
        expect(
            rows[0]["methodology"]["startup_intelligence_score"] == 95.0,
            f"Expected the NEWER score, got {rows[0]['methodology']['startup_intelligence_score']!r}",
        )
    finally:
        _cleanup()


def test_startup_returned_once() -> None:
    name = f"{TEST_PREFIX} Once"
    _save(name, _methodology(50.0))
    startup_id = get_or_create_startup(name)
    _save(name, _methodology(60.0))
    _save(name, _methodology(70.0))
    try:
        rows = _compare([startup_id])
        matching = [r for r in rows if r["startup_id"] == startup_id]
        expect(len(matching) == 1, f"A startup with 3 analyses must appear exactly once, got {len(matching)}")
    finally:
        _cleanup()


# --- 10-11: pillar/dimension preservation ------------------------------------


def test_pillar_scores_preserved() -> None:
    ids = _seed_two()
    try:
        with _authenticated_as_viewer():
            response = client.get("/compare", params={"startups": f"{ids[0]},{ids[1]}"})
        body = response.json()
        alpha = next(s for s in body["startups"] if s["startup_id"] == ids[0])
        expect(alpha["market"]["score"] == 9.0, f"Expected Alpha's market score 9.0, got {alpha['market']['score']!r}")
        expect(alpha["team"]["score"] == 9.0, f"Expected Alpha's team score 9.0, got {alpha['team']['score']!r}")
        expect(
            alpha["market"]["subscores"][0]["name"] == "Market Size",
            "Subscore detail must be preserved through to the API response",
        )
    finally:
        _cleanup()


def test_unavailable_pillar_and_dimension_remain_unavailable() -> None:
    name = f"{TEST_PREFIX} Unavailable"
    _save(name, _methodology(70.0, team_score=None, market_subscores=[
        {
            "name": "Market Size",
            "score": None,
            "weight": 0.25,
            "confidence": "Low",
            "evidence_status": "Unavailable",
            "rationale": "No evidence found.",
            "recommendations": [],
            "missing_information": ["Market sizing data"],
        }
    ]))
    startup_id = get_or_create_startup(name)
    ids = _seed_two()
    try:
        with _authenticated_as_viewer():
            response = client.get("/compare", params={"startups": f"{startup_id},{ids[0]}"})
        body = response.json()
        target = next(s for s in body["startups"] if s["startup_id"] == startup_id)

        expect(target["team"]["score"] is None, f"Unavailable team pillar must stay None, got {target['team']['score']!r}")
        expect(
            target["market"]["subscores"][0]["score"] is None,
            "Unavailable dimension must stay None, never coerced to 0",
        )
        expect(
            target["market"]["subscores"][0]["evidence_status"] == "Unavailable",
            f"Expected evidence_status Unavailable, got {target['market']['subscores'][0]['evidence_status']!r}",
        )
    finally:
        _cleanup()


# --- 12: SPS parity with Rankings/Profile -----------------------------------


def test_sps_matches_rankings() -> None:
    name = f"{TEST_PREFIX} Parity"
    _save(name, _methodology(66.6))
    startup_id = get_or_create_startup(name)
    try:
        rows = _compare([startup_id])
        compare_sps = rows[0]["methodology"]["startup_intelligence_score"]

        rankings = get_rankings(TEST_VIEWER, True)
        ranking_row = next(r for r in rankings if r["company_name"] == name)

        expect(
            compare_sps == ranking_row["overall_score"],
            f"Compare SPS ({compare_sps}) must match Rankings SPS ({ranking_row['overall_score']})",
        )
    finally:
        _cleanup()


# --- 13: endpoint now requires auth ------------------------------------------


def test_compare_endpoint_now_requires_auth() -> None:
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility: /compare is no
    longer public (approved decision -- no public scores-only exception,
    and explicit startup ids must not bypass authorization). Anonymous
    access is rejected; an authenticated caller can still compare startups
    they're authorized to see (here, via the admin-equivalent TEST_VIEWER,
    same as every other API-layer test in this file).
    """
    ids = _seed_two()
    try:
        anonymous_response = client.get("/compare", params={"startups": f"{ids[0]},{ids[1]}"})
        expect(
            anonymous_response.status_code == 401,
            f"Expected anonymous /compare access to require auth, got {anonymous_response.status_code}",
        )

        with _authenticated_as_viewer():
            authenticated_response = client.get("/compare", params={"startups": f"{ids[0]},{ids[1]}"})
        expect(
            authenticated_response.status_code == 200,
            f"Expected an authenticated caller to reach /compare, got {authenticated_response.status_code}",
        )
    finally:
        _cleanup()


# --- 14: input order preserved ----------------------------------------------


def test_input_order_preserved() -> None:
    ids = _seed_two()  # [Alpha, Beta]
    reversed_ids = [ids[1], ids[0]]
    try:
        rows = _compare(reversed_ids)
        expect(
            [r["startup_id"] for r in rows] == reversed_ids,
            f"Expected order {reversed_ids}, got {[r['startup_id'] for r in rows]}",
        )
    finally:
        _cleanup()


# --- 15: auth dependency present ----------------------------------------------


def test_auth_dependency_present() -> None:
    """
    Portfolio Release Task 3B supersedes this test's original assertion
    ("GET /compare must never depend on RequireAuth -- it's public
    intelligence") -- that product decision changed (approved decision:
    no public scores-only exception). Flipped to confirm the dependency
    IS now present, as a structural regression guard against it silently
    being removed again later.
    """
    import inspect

    signature = inspect.signature(api.compare)
    expect(
        "current_user" in signature.parameters,
        "GET /compare must depend on RequireAuth -- comparison is scoped to the caller's own authorized analyses",
    )


def _seed_two() -> list[int]:
    """Alpha: SPS 90, market/team 9.0. Beta: SPS 50, market/team 5.0."""
    _save(f"{TEST_PREFIX} Alpha", _methodology(90.0, market_score=9.0, team_score=9.0))
    _save(f"{TEST_PREFIX} Beta", _methodology(50.0, market_score=5.0, team_score=5.0))
    return [
        get_or_create_startup(f"{TEST_PREFIX} Alpha"),
        get_or_create_startup(f"{TEST_PREFIX} Beta"),
    ]


TESTS = [
    test_compare_two_valid_canonical_startups,
    test_compare_four_valid_startups,
    test_one_startup_produces_useful_response_api_layer,
    test_more_than_four_startups_bounded_api_layer,
    test_duplicate_ids_deduplicated_safely,
    test_invalid_startup_id_handled_cleanly,
    test_legacy_analysis_excluded,
    test_latest_canonical_analysis_selected,
    test_startup_returned_once,
    test_pillar_scores_preserved,
    test_unavailable_pillar_and_dimension_remain_unavailable,
    test_sps_matches_rankings,
    test_compare_endpoint_now_requires_auth,
    test_input_order_preserved,
    test_auth_dependency_present,
]


def main() -> None:
    print("\nCompare Startups V1 tests")
    print("-" * 72)

    # Precautionary: a previous interrupted run could have left ZZTest
    # Compare rows behind (each test also cleans up in its own finally
    # block, but this guards against that not having happened).
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
