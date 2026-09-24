// VentureGPS /markets/[slug] page-data tests.
//
// loadMarketPageData (app/markets/[slug]/marketPageData.ts -- split out from page.tsx specifically so this pure
// logic is testable under plain `node` with no JSX/custom-loader involved, the same separation
// components/home/ventureGps/homepageData.ts already uses for the homepage) is the one place that turns a slug
// into either a real market page or one of two honest fallback states. Before this test existed, only the FIRST
// of its two fetches (the Capital Signal) was ever exercised against a failure -- the market lookup itself
// (getMarketBySlug) had no failure-path coverage at all, which is exactly how the real production bug this file
// locks in a fix for went unnoticed: an unreachable V2 API crashed the whole page with a generic Next.js error
// screen instead of the app's own "couldn't reach ... try again in a moment" message, because that first call
// was never wrapped in a try/catch. Three real, honest outcomes, never a fourth:
// - "unknown": the lookup succeeded and genuinely found no such market.
// - "unavailable" with market: null: the lookup ITSELF failed -- we never learned whether the slug is real.
// - "unavailable" with a real market: the lookup succeeded, but that market's Capital Signal failed.
// - "ok": both calls succeeded.
//
// Each test uses its own never-repeated slug string so React's cache() wrapper (request-scoped memoization)
// can never return a stale result from an earlier test in this same process.
//
// Run with:
//   node tests/v2MarketPageAvailability.test.ts

import { loadMarketPageData } from "../app/markets/[slug]/marketPageData.ts";
import type { MarketOut } from "../types/v2/capital.ts";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

const ROBOTICS: MarketOut = { id: "11111111-1111-1111-1111-111111111111", slug: "robotics", display_name: "Robotics" };

const SIGNAL_BODY = {
  market: ROBOTICS,
  taxonomy_version: "venturegps_taxonomy.v1",
  as_of: "2026-09-24T00:00:00Z",
  methodology_version: "capital_signal.v1",
  current_window: { start: "2026-08-25T00:00:00Z", end: "2026-09-24T00:00:00Z", metrics: { financing_activity: 0, companies_funded: 0, capital_deployed: [], capital_concentration: [], stage_distribution: { pre_seed: 0, seed: 0, series_a: 0, series_b: 0, growth: 0, unknown: 0 }, diagnostics: { events_considered: 0, events_included: 0, events_excluded_missing_date: 0, events_excluded_outside_period: 0, events_without_verified_amount: 0, events_without_known_stage: 0, classified_company_count: 0 } } },
  historical_windows: [],
  financing_activity: { metric: "financing_activity", currency_code: null, current_value: "0", historical_values: [], historical_nonzero_windows: 0, percentile_rank: null, direction: "insufficient_data", votes: false },
  companies_funded: { metric: "companies_funded", currency_code: null, current_value: "0", historical_values: [], historical_nonzero_windows: 0, percentile_rank: null, direction: "insufficient_data", votes: false },
  capital_deployed: [],
  capital_concentration: [],
  overall: "insufficient_data",
  methodology: {
    methodology_version: "capital_signal.v1", date_policy: "", attribution_policy: "", verified_amount_policy: "",
    currency_policy: "", historical_window_policy: "", minimum_history_rule: "", comparison_method: "",
    concentration_voting_policy: "", limitations: "",
  },
};

type FetchStep = { status: number; body?: unknown } | "network-error";

// Installs a fake fetch for the duration of one test, resolving a queue of steps in call order (call 1 = the
// market lookup, call 2 = the Capital Signal fetch) -- never leaves the real global.fetch replaced once a test
// finishes, even if the test throws.
function withFakeFetch(steps: FetchStep[]) {
  let callIndex = 0;
  const realFetch = globalThis.fetch;

  globalThis.fetch = (async () => {
    const step = steps[callIndex] ?? steps[steps.length - 1];
    callIndex += 1;
    if (step === "network-error") {
      throw new Error("simulated network failure");
    }
    return new Response(JSON.stringify(step.body ?? {}), { status: step.status, headers: { "content-type": "application/json" } });
  }) as typeof fetch;

  return {
    restore: () => {
      globalThis.fetch = realFetch;
    },
  };
}

async function test_a_successful_response_returns_ok_with_the_market_and_its_signal(): Promise<void> {
  const fake = withFakeFetch([{ status: 200, body: { markets: [ROBOTICS] } }, { status: 200, body: SIGNAL_BODY }]);
  try {
    const data = await loadMarketPageData("robotics-ok-1");
    expect(data.status === "ok", `expected status "ok", got ${data.status}`);
    if (data.status === "ok") {
      expect(data.market.slug === "robotics", "expected the resolved market to be returned");
      expect(data.signal.overall === "insufficient_data", "expected the fetched signal to be returned unmodified");
    }
  } finally {
    fake.restore();
  }
}

async function test_a_genuinely_missing_market_returns_unknown_never_unavailable(): Promise<void> {
  const fake = withFakeFetch([{ status: 200, body: { markets: [] } }]);
  try {
    const data = await loadMarketPageData("no-such-market-2");
    expect(data.status === "unknown", `a market the lookup successfully found nothing for must be "unknown", got ${data.status}`);
  } finally {
    fake.restore();
  }
}

async function test_an_unreachable_backend_on_the_market_lookup_itself_is_unavailable_not_a_crash(): Promise<void> {
  const fake = withFakeFetch(["network-error"]);
  try {
    const data = await loadMarketPageData("robotics-lookup-down-3");
    expect(data.status === "unavailable", `an unreachable market lookup must degrade to "unavailable", got ${data.status} (a thrown error here would have been the real production bug -- crashing the page with a generic error screen instead of the app's own message)`);
    if (data.status === "unavailable") {
      expect(data.market === null, "the market is not yet known when the lookup itself failed -- must be null, never a guessed/partial value");
    }
  } finally {
    fake.restore();
  }
}

async function test_a_resolved_market_with_an_unreachable_signal_is_unavailable_with_the_market_preserved(): Promise<void> {
  const fake = withFakeFetch([{ status: 200, body: { markets: [ROBOTICS] } }, "network-error"]);
  try {
    const data = await loadMarketPageData("robotics-signal-down-4");
    expect(data.status === "unavailable", `a resolved market whose signal fetch fails must be "unavailable", got ${data.status}`);
    if (data.status === "unavailable") {
      expect(data.market !== null && data.market.slug === "robotics", "the market resolved fine and must still be carried through, unlike the lookup-failure case");
    }
  } finally {
    fake.restore();
  }
}

async function test_a_backend_error_response_on_the_lookup_is_also_unavailable_not_a_crash(): Promise<void> {
  // Distinct from a network-level failure: the fetch itself succeeds, but the V2 API returns a non-2xx (e.g. a
  // 503 while its database is unreachable) -- lib/api/v2/client.ts turns this into a thrown V2ApiError, which
  // must be caught exactly the same way as a raw network error.
  const fake = withFakeFetch([{ status: 503, body: { detail: "database unavailable" } }]);
  try {
    const data = await loadMarketPageData("robotics-lookup-503-5");
    expect(data.status === "unavailable", `a 503 from the market lookup must degrade to "unavailable", got ${data.status}`);
    if (data.status === "unavailable") {
      expect(data.market === null, "the market is not known when the lookup itself returned an error response");
    }
  } finally {
    fake.restore();
  }
}

async function main(): Promise<void> {
  const tests = [
    test_a_successful_response_returns_ok_with_the_market_and_its_signal,
    test_a_genuinely_missing_market_returns_unknown_never_unavailable,
    test_an_unreachable_backend_on_the_market_lookup_itself_is_unavailable_not_a_crash,
    test_a_resolved_market_with_an_unreachable_signal_is_unavailable_with_the_market_preserved,
    test_a_backend_error_response_on_the_lookup_is_also_unavailable_not_a_crash,
  ];

  let failures = 0;

  for (const test of tests) {
    try {
      await test();
      console.log(`PASS ${test.name}`);
    } catch (error) {
      failures += 1;
      console.error(`FAIL ${test.name}: ${(error as Error).message}`);
    }
  }

  if (failures > 0) {
    console.error(`${failures} test(s) failed`);
    process.exit(1);
  }

  console.log(`All ${tests.length} tests passed`);
}

main();
