"""
Regression tests for Startup Discovery V1 --
app/database/db.py's discover_startups()/count_discover_startups()/
get_discovery_filter_options(), and GET /discover, GET /discover/
filter-options in app/api.py.

Real SQL against the real configured DATABASE_URL, same "no separate test
database" convention as test_startup_write_path.py/test_saved_startups.py.
Every row here uses a distinctive "ZZTest Discovery " company-name prefix
and unique test-only industry/stage/business_model values (so this file's
data can never collide with real canonical data or shift real filter-option
lists), cleaned up in a finally block even on failure.

No test here makes an LLM/Tavily call, and none touches
startup_memberships or Methodology v2 scoring logic -- discover_startups()
only reads already-computed methodology JSONB.

Run with:
    python -m app.tests.test_discovery
"""

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.api as api
from app.auth import AuthenticatedUser, get_current_user
from app.ai.sie_v2_methodology import METHODOLOGY_VERSION
from app.database.db import (
    MAX_DISCOVERY_LIMIT,
    count_discover_startups,
    discover_startups,
    engine,
    get_or_create_startup,
    get_rankings,
    save_analysis,
    save_startup_for_user,
)

TEST_PREFIX = "ZZTest Discovery"
TEST_INDUSTRY_A = "ZZTest Discovery IndustryA"
TEST_INDUSTRY_B = "ZZTest Discovery IndustryB"
TEST_STAGE_A = "ZZTest Discovery StageA"
TEST_STAGE_B = "ZZTest Discovery StageB"
TEST_MODEL_A = "ZZTest Discovery ModelA"
TEST_MODEL_B = "ZZTest Discovery ModelB"

TEST_USER = "zztest_discovery_user"
# Portfolio Release Task 3B -- Secure Analysis Visibility: discover_startups()/
# count_discover_startups()/get_rankings() now require a viewer to scope by.
# This file's own job is discovery's QUERY logic (filters/sorting/pagination/
# dedup) -- not the authorization feature itself, which has its own dedicated
# coverage in test_analysis_visibility.py and test_security_hardening.py's
# test_discovery_now_requires_auth. Every call below goes through an ADMIN
# viewer (viewer_is_admin=True bypasses the visibility filter entirely) so
# every existing assertion here keeps testing exactly what it always tested,
# unaffected by the new, orthogonal authorization dimension.
TEST_VIEWER = "zztest_discovery_admin_viewer"


def _discover(**kwargs):
    return discover_startups(TEST_VIEWER, True, **kwargs)


def _count(**kwargs):
    return count_discover_startups(TEST_VIEWER, True, **kwargs)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


def _methodology(
    sps: float,
    market: float | None = 7.0,
    team: float | None = 7.0,
    product: float | None = 7.0,
    execution: float | None = 7.0,
    traction: float | None = 7.0,
    financial_health: float | None = 7.0,
    version: str | None = None,
) -> dict:
    def pillar(score: float | None) -> dict:
        # An empty dict (no "score" key) is exactly how a real Unavailable
        # pillar is stored -- `methodology->'x'->>'score'` reads NULL for
        # it, the same as a real analysis.
        return {} if score is None else {"score": score}

    return {
        "startup_intelligence_score": sps,
        "market": pillar(market),
        "team": pillar(team),
        "product": pillar(product),
        "execution": pillar(execution),
        "traction": pillar(traction),
        "financial_health": pillar(financial_health),
        "analysis_context": {
            "methodology_version": version if version is not None else METHODOLOGY_VERSION
        },
    }


def _save(
    company_name: str,
    industry: str,
    stage: str,
    business_model: str,
    methodology: dict | None,
) -> int:
    return save_analysis(
        company_text=f"Test company text for {company_name}",
        summary="s",
        risk_analysis="r",
        competitor_analysis="c",
        memo="m",
        structured_analysis={
            "company_name": company_name,
            "industry": industry,
            "stage": stage,
            "business_model": business_model,
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
            text("DELETE FROM saved_startups WHERE user_id = :u"), {"u": TEST_USER}
        )
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
        connection.execute(text("DELETE FROM users WHERE id = :u"), {"u": TEST_USER})


def _seed() -> None:
    """
    Alpha: high across the board (SPS 90, all pillars 9.0), IndustryA/
    StageA/ModelA.
    Beta: low across the board (SPS 50, all pillars 5.0), IndustryB/
    StageA/ModelB.
    Gamma: mid SPS (70), IndustryA/StageB/ModelA, but team is
    Unavailable (no score at all) -- the pillar-filter NULL-safety case.
    Legacy: a non-canonical (methodology_version "1.0") analysis -- must
    never appear in discovery at all.
    Repeat: TWO canonical analyses for the SAME company -- an older one
    (SPS 40) and a newer one (SPS 95) -- discovery must resolve to the
    newer one exactly once, never both.
    """
    _save(
        f"{TEST_PREFIX} Alpha", TEST_INDUSTRY_A, TEST_STAGE_A, TEST_MODEL_A,
        _methodology(90.0, market=9.0, team=9.0, product=9.0, execution=9.0, traction=9.0, financial_health=9.0),
    )
    _save(
        f"{TEST_PREFIX} Beta", TEST_INDUSTRY_B, TEST_STAGE_A, TEST_MODEL_B,
        _methodology(50.0, market=5.0, team=5.0, product=5.0, execution=5.0, traction=5.0, financial_health=5.0),
    )
    _save(
        f"{TEST_PREFIX} Gamma", TEST_INDUSTRY_A, TEST_STAGE_B, TEST_MODEL_A,
        _methodology(70.0, team=None),
    )
    _save(
        f"{TEST_PREFIX} Legacy", TEST_INDUSTRY_A, TEST_STAGE_A, TEST_MODEL_A,
        _methodology(99.0, version="1.0"),
    )
    _save(f"{TEST_PREFIX} Repeat", TEST_INDUSTRY_A, TEST_STAGE_A, TEST_MODEL_A, _methodology(40.0))
    _save(f"{TEST_PREFIX} Repeat", TEST_INDUSTRY_A, TEST_STAGE_A, TEST_MODEL_A, _methodology(95.0))


def _names(rows: list[dict]) -> list[str]:
    return [row["company_name"] for row in rows]


# --- 1-2: latest canonical only, no duplicates ------------------------------


def test_discovery_returns_latest_canonical_startup_once() -> None:
    rows = _discover(query=f"{TEST_PREFIX} Repeat")
    expect(len(rows) == 1, f"Expected exactly one row for a twice-analyzed startup, got {len(rows)}")
    expect(rows[0]["overall_score"] == 95.0, f"Expected the NEWER score (95.0), got {rows[0]['overall_score']!r}")


def test_old_analyses_do_not_create_duplicates() -> None:
    count = _count(query=f"{TEST_PREFIX} Repeat")
    expect(count == 1, f"Expected count=1 for a twice-analyzed startup, got {count}")


# --- 3: legacy/non-v2 analyses excluded -------------------------------------


def test_legacy_analyses_are_excluded() -> None:
    rows = _discover(query=f"{TEST_PREFIX} Legacy")
    expect(len(rows) == 0, f"A non-canonical (methodology_version 1.0) analysis must never appear, got {rows}")


# --- 4-8: individual filters -------------------------------------------------


def test_text_query_filter() -> None:
    rows = _discover(query=f"{TEST_PREFIX} Alpha")
    expect(_names(rows) == [f"{TEST_PREFIX} Alpha"], f"Unexpected match set: {_names(rows)}")


def test_industry_filter() -> None:
    # Alpha, Gamma, and Repeat are all seeded as IndustryA (Legacy is too,
    # but it's non-canonical -- version "1.0" -- so it must still be
    # excluded here regardless of industry, same as
    # test_legacy_analyses_are_excluded already confirms directly).
    rows = _discover(industry=TEST_INDUSTRY_A, query=TEST_PREFIX)
    names = set(_names(rows))
    expect(
        names == {f"{TEST_PREFIX} Alpha", f"{TEST_PREFIX} Gamma", f"{TEST_PREFIX} Repeat"},
        f"Expected Alpha+Gamma+Repeat for IndustryA, got {names}",
    )


def test_stage_filter() -> None:
    rows = _discover(stage=TEST_STAGE_B, query=TEST_PREFIX)
    expect(_names(rows) == [f"{TEST_PREFIX} Gamma"], f"Expected only Gamma for StageB, got {_names(rows)}")


def test_business_model_filter() -> None:
    rows = _discover(business_model=TEST_MODEL_B, query=TEST_PREFIX)
    expect(_names(rows) == [f"{TEST_PREFIX} Beta"], f"Expected only Beta for ModelB, got {_names(rows)}")


# funding_stage filter: deliberately NOT implemented in Discovery V1 (see
# Part 1's real-data finding -- funding_stage is identical to company
# stage in 100% of current canonical rows, making a separate filter
# redundant today) -- no test for it, per Part 14's own "if implemented"
# qualifier.


# --- 9-11: SPS range + combined filters -------------------------------------


def test_min_sps_filter() -> None:
    rows = _discover(min_sps=60, query=TEST_PREFIX)
    names = set(_names(rows)) & {f"{TEST_PREFIX} Alpha", f"{TEST_PREFIX} Beta", f"{TEST_PREFIX} Gamma"}
    expect(
        names == {f"{TEST_PREFIX} Alpha", f"{TEST_PREFIX} Gamma"},
        f"min_sps=60 should include Alpha(90)/Gamma(70), exclude Beta(50); got {names}",
    )


def test_max_sps_filter() -> None:
    rows = _discover(max_sps=60, query=TEST_PREFIX)
    names = set(_names(rows)) & {f"{TEST_PREFIX} Alpha", f"{TEST_PREFIX} Beta", f"{TEST_PREFIX} Gamma"}
    expect(names == {f"{TEST_PREFIX} Beta"}, f"max_sps=60 should include only Beta(50); got {names}")


def test_combined_filters() -> None:
    # IndustryA AND SPS >= 80: Alpha(90) and Repeat(95, its latest score)
    # both qualify; Gamma(70) and IndustryB's Beta do not.
    rows = _discover(industry=TEST_INDUSTRY_A, min_sps=80, query=TEST_PREFIX)
    names = set(_names(rows))
    expect(
        names == {f"{TEST_PREFIX} Alpha", f"{TEST_PREFIX} Repeat"},
        f"Expected Alpha+Repeat, got {names}",
    )


# --- 12: unavailable pillar never falsely matches a minimum ----------------


def test_unavailable_pillar_never_matches_minimum() -> None:
    rows = _discover(min_team=1.0, query=f"{TEST_PREFIX} Gamma")
    expect(
        len(rows) == 0,
        f"Gamma's team pillar is Unavailable (NULL) -- it must never satisfy ANY min_team, even 1.0; got {rows}",
    )


# --- pillar filters: dedicated per-pillar coverage --------------------------


def test_each_pillar_minimum_filter() -> None:
    """Alpha (all pillars 9.0) vs. Beta (all pillars 5.0) -- for every one
    of the six pillar-minimum filters, a threshold of 7.0 must include
    Alpha and exclude Beta. Exercises each pillar's own filter path
    individually, not just one representative pillar."""
    pillar_kwargs = [
        ("min_market", {"min_market": 7.0}),
        ("min_team", {"min_team": 7.0}),
        ("min_product", {"min_product": 7.0}),
        ("min_execution", {"min_execution": 7.0}),
        ("min_traction", {"min_traction": 7.0}),
        ("min_financial_health", {"min_financial_health": 7.0}),
    ]

    for label, kwargs in pillar_kwargs:
        rows = _discover(query=TEST_PREFIX, **kwargs)
        names = set(_names(rows)) & {f"{TEST_PREFIX} Alpha", f"{TEST_PREFIX} Beta"}
        expect(
            names == {f"{TEST_PREFIX} Alpha"},
            f"{label}=7.0 should include Alpha(9.0) and exclude Beta(5.0); got {names}",
        )


# --- 13-15: sorting -----------------------------------------------------


def test_sorting_sps_descending() -> None:
    # Within IndustryA: Repeat resolves to its newer analysis (SPS 95),
    # Alpha is 90, Gamma is 70 -- descending order is Repeat, Alpha, Gamma.
    rows = _discover(
        query=TEST_PREFIX, industry=TEST_INDUSTRY_A, sort="sps_desc"
    )
    names = _names(rows)
    expect(
        names == [f"{TEST_PREFIX} Repeat", f"{TEST_PREFIX} Alpha", f"{TEST_PREFIX} Gamma"],
        f"Expected SPS-descending order (95, 90, 70), got {names}",
    )


def test_sorting_sps_ascending() -> None:
    rows = _discover(
        query=TEST_PREFIX, industry=TEST_INDUSTRY_A, sort="sps_asc"
    )
    names = _names(rows)
    expect(
        names == [f"{TEST_PREFIX} Gamma", f"{TEST_PREFIX} Alpha", f"{TEST_PREFIX} Repeat"],
        f"Expected SPS-ascending order, got {names}",
    )


def test_sorting_newest() -> None:
    rows = _discover(query=TEST_PREFIX, sort="newest")
    # The Repeat startup's newest analysis (SPS 95) was saved last of all
    # seeded rows -- it must sort first under "newest".
    expect(
        rows[0]["company_name"] == f"{TEST_PREFIX} Repeat",
        f"Expected the most-recently-analyzed startup first, got {rows[0]['company_name']!r}",
    )


# --- 16-17: bounds fail cleanly / limit is bounded --------------------------


def test_invalid_numeric_bounds_fail_cleanly_api_layer() -> None:
    """
    Portfolio Release Task 3B: /discover now resolves RequireAuth before
    Query(...) validation, so an unauthenticated request gets 401 before
    it ever reaches the invalid-param check this test is actually about --
    a real, meaningful interaction (auth is checked first), not a reason
    to weaken this test. A minimal, LOCALLY SCOPED get_current_user()
    override (restored in `finally`, matching the pattern
    test_analyze_unified.py's own setup_module()/teardown_module() use at
    the whole-module level) supplies just enough of a real identity to
    reach the 422 check -- this file otherwise has no JWT-mocking harness
    of its own, and doesn't need one for its own actual job (discovery's
    query logic, not auth plumbing).
    """
    api.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id=TEST_VIEWER)
    try:
        response = client.get("/discover", params={"min_sps": 200})
        expect(response.status_code == 422, f"Expected 422 for out-of-range min_sps, got {response.status_code}")

        response = client.get("/discover", params={"sort": "not_a_real_sort"})
        expect(response.status_code == 422, f"Expected 422 for an invalid sort value, got {response.status_code}")
    finally:
        api.app.dependency_overrides.pop(get_current_user, None)


def test_limit_is_bounded() -> None:
    rows = _discover(limit=999_999)
    expect(
        len(rows) <= MAX_DISCOVERY_LIMIT,
        f"discover_startups() must clamp limit to MAX_DISCOVERY_LIMIT, got {len(rows)} rows",
    )

    # See test_invalid_numeric_bounds_fail_cleanly_api_layer's own comment
    # for why a real (if fake-identity) authenticated request is needed to
    # reach this 422 check at all now.
    api.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id=TEST_VIEWER)
    try:
        response = client.get("/discover", params={"limit": 999_999})
        expect(response.status_code == 422, f"Expected 422 for an out-of-bounds limit, got {response.status_code}")
    finally:
        api.app.dependency_overrides.pop(get_current_user, None)


# --- 18: discovery endpoint now requires auth --------------------------------


def test_discovery_endpoint_now_requires_auth() -> None:
    """
    Portfolio Release Task 3B -- Secure Analysis Visibility: /discover and
    /discover/filter-options are no longer public (approved decision -- no
    public scores-only exception). Just the anonymous-rejection half here
    -- the authenticated-success half, through the real route with a real
    token, is test_security_hardening.py's test_discovery_now_requires_auth;
    this file's own job is discovery's query logic, not auth plumbing.
    """
    response = client.get("/discover")
    expect(response.status_code == 401, f"Expected 401 with no auth, got {response.status_code}")

    response = client.get("/discover/filter-options")
    expect(response.status_code == 401, f"Expected 401 with no auth, got {response.status_code}")


# --- 19: saved-startup behavior remains user-isolated -----------------------


def test_saved_startup_behavior_remains_user_isolated() -> None:
    """Light confirmation only -- full isolation coverage lives in
    test_saved_startups.py. This just confirms Discovery's own new code
    (startup_id resolution) didn't disturb that guarantee."""
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
            {"id": TEST_USER},
        )

    startup_id = get_or_create_startup(f"{TEST_PREFIX} Alpha")
    save_startup_for_user(TEST_USER, startup_id)

    with engine.begin() as connection:
        other_user_count = connection.execute(
            text("SELECT COUNT(*) FROM saved_startups WHERE user_id != :u AND startup_id = :s"),
            {"u": TEST_USER, "s": startup_id},
        ).scalar()

    expect(other_user_count == 0, "No other user should see this save -- isolation broken")


# --- 20: Rankings behavior remains unchanged --------------------------------


def test_rankings_behavior_remains_unchanged() -> None:
    """discover_startups() must never influence get_rankings() -- they are
    independent queries over the same canonical population. This company
    is well within Rankings' own eligibility rules, so it must appear
    there too, with the SAME resolved (latest, 95.0) score Discovery
    resolves -- proving Discovery didn't fork a second definition of
    "current startup"."""
    rankings = get_rankings(TEST_VIEWER, True)
    matching = [row for row in rankings if row["company_name"] == f"{TEST_PREFIX} Repeat"]

    expect(len(matching) == 1, f"Expected the test startup to appear exactly once in Rankings, got {len(matching)}")
    expect(
        matching[0]["overall_score"] == 95.0,
        f"Rankings and Discovery must resolve to the SAME latest score; Rankings got {matching[0]['overall_score']!r}",
    )


TESTS = [
    test_discovery_returns_latest_canonical_startup_once,
    test_old_analyses_do_not_create_duplicates,
    test_legacy_analyses_are_excluded,
    test_text_query_filter,
    test_industry_filter,
    test_stage_filter,
    test_business_model_filter,
    test_min_sps_filter,
    test_max_sps_filter,
    test_combined_filters,
    test_unavailable_pillar_never_matches_minimum,
    test_each_pillar_minimum_filter,
    test_sorting_sps_descending,
    test_sorting_sps_ascending,
    test_sorting_newest,
    test_invalid_numeric_bounds_fail_cleanly_api_layer,
    test_limit_is_bounded,
    test_discovery_endpoint_now_requires_auth,
    test_saved_startup_behavior_remains_user_isolated,
    test_rankings_behavior_remains_unchanged,
]


def main() -> None:
    print("\nStartup Discovery V1 tests")
    print("-" * 72)

    _cleanup()
    _seed()

    failures: list[str] = []

    try:
        for test in TESTS:
            name = test.__name__

            try:
                test()
            except AssertionError as error:
                print(f"FAIL  {name}\n      {error}")
                failures.append(name)
            else:
                print(f"PASS  {name}")
    finally:
        _cleanup()

    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
