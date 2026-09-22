// VentureGPS V2 market-slug resolution tests.
//
// getMarketBySlug is the ONE place the public /markets/[slug] route turns a URL slug into a market. Unlike most
// of the other V2 lib modules, this one talks to the network, so these tests install a fake global.fetch rather
// than exercising a pure function -- the goal is to lock in two behaviors the page depends on: (1) an unknown
// slug resolves to `null`, never a thrown error, so the route can render its own "market not found" state
// instead of an error boundary; (2) the request is scoped by `?slug=` server-side, never fetched as a full list
// and filtered client-side.
//
// Run with:
//   node tests/v2MarketSlug.test.ts

import { getMarketBySlug } from "../lib/api/v2/markets.ts";
import { V2ApiError, isV2NotFound, isV2ServiceUnavailable } from "../lib/api/v2/client.ts";
import type { MarketOut } from "../types/v2/capital.ts";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

const ROBOTICS: MarketOut = { id: "11111111-1111-1111-1111-111111111111", slug: "robotics", display_name: "Robotics" };

type FetchCall = { url: string };

// Installs a fake fetch for the duration of one test and returns a spy plus a restore function -- never leaves
// the real global.fetch replaced once a test finishes, even if the test throws.
function withFakeFetch(handler: (url: string) => { status: number; body: unknown }) {
  const calls: FetchCall[] = [];
  const realFetch = globalThis.fetch;

  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push({ url });
    const { status, body } = handler(url);
    return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  }) as typeof fetch;

  return {
    calls,
    restore: () => {
      globalThis.fetch = realFetch;
    },
  };
}

async function test_known_slug_resolves_to_its_market(): Promise<void> {
  const fake = withFakeFetch(() => ({ status: 200, body: { markets: [ROBOTICS] } }));
  try {
    const result = await getMarketBySlug("robotics");
    expect(result !== null && result.id === ROBOTICS.id, "expected the matching market to be returned");
  } finally {
    fake.restore();
  }
}

async function test_unknown_slug_resolves_to_null_not_an_error(): Promise<void> {
  const fake = withFakeFetch(() => ({ status: 200, body: { markets: [] } }));
  try {
    const result = await getMarketBySlug("no-such-market");
    expect(result === null, "an unknown slug must resolve to null so the route can render its own not-found state");
  } finally {
    fake.restore();
  }
}

async function test_slug_lookup_is_scoped_server_side_via_query_param(): Promise<void> {
  const fake = withFakeFetch(() => ({ status: 200, body: { markets: [] } }));
  try {
    await getMarketBySlug("robotics");
    expect(fake.calls.length === 1, `expected exactly one fetch, got ${fake.calls.length}`);
    expect(fake.calls[0].url.includes("/markets?slug=robotics"), `expected the slug to be sent as a query param, got: ${fake.calls[0].url}`);
  } finally {
    fake.restore();
  }
}

async function test_a_slug_needing_url_encoding_is_encoded(): Promise<void> {
  const fake = withFakeFetch(() => ({ status: 200, body: { markets: [] } }));
  try {
    await getMarketBySlug("ai & robotics");
    expect(fake.calls[0].url.includes("slug=ai+%26+robotics") || fake.calls[0].url.includes("slug=ai%20%26%20robotics"), `expected the slug to be URL-encoded, got: ${fake.calls[0].url}`);
  } finally {
    fake.restore();
  }
}

async function test_a_backend_error_response_throws_a_typed_v2_api_error(): Promise<void> {
  const fake = withFakeFetch(() => ({ status: 503, body: { detail: "database unavailable" } }));
  try {
    let thrown: unknown = null;
    try {
      await getMarketBySlug("robotics");
    } catch (error) {
      thrown = error;
    }
    expect(thrown instanceof V2ApiError, "expected a V2ApiError to be thrown, not left unhandled or swallowed");
    expect(isV2ServiceUnavailable(thrown), "a 503 response must classify as isV2ServiceUnavailable");
    expect(!isV2NotFound(thrown), "a 503 must not also classify as isV2NotFound");
  } finally {
    fake.restore();
  }
}

async function test_isV2NotFound_only_matches_404_v2_api_errors(): Promise<void> {
  expect(isV2NotFound(new V2ApiError(404, "not found")), "a 404 V2ApiError must classify as not-found");
  expect(!isV2NotFound(new V2ApiError(500, "server error")), "a 500 V2ApiError must not classify as not-found");
  expect(!isV2NotFound(new Error("plain error")), "a plain Error must never classify as a V2 not-found");
  expect(!isV2NotFound(null), "null must never classify as a V2 not-found");
}

async function main(): Promise<void> {
  const tests = [
    test_known_slug_resolves_to_its_market,
    test_unknown_slug_resolves_to_null_not_an_error,
    test_slug_lookup_is_scoped_server_side_via_query_param,
    test_a_slug_needing_url_encoding_is_encoded,
    test_a_backend_error_response_throws_a_typed_v2_api_error,
    test_isV2NotFound_only_matches_404_v2_api_errors,
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
