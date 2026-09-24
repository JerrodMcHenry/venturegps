// Data loading for the public /markets/[slug] page, split out from page.tsx (mirrors
// components/home/ventureGps/homepageData.ts's own separation of data-loading from rendering) so this pure
// logic can be unit-tested directly under plain `node` -- no JSX, no custom loader needed, same simplicity as
// tests/v2MarketSlug.test.ts already has for getMarketBySlug alone.
import { cache } from "react";

// Relative, not "@/..." -- matches lib/api/v2/markets.ts's/client.ts's own convention for their runtime imports
// of each other (only type-only imports use the "@/" alias, which erases at compile time and never needs
// runtime resolution). This file is imported both by page.tsx (bundled by Next.js, where "@/" works fine) and
// directly by tests/v2MarketPageAvailability.test.ts under plain `node` (which has no tsconfig path-alias
// resolution) -- relative imports are what make the second one possible without a custom loader.
import { getCapitalSignal, getMarketBySlug } from "../../../lib/api/v2/markets.ts";
import { getConfiguredTaxonomyVersion } from "../../../lib/api/v2/taxonomyVersion.ts";

import type { CapitalSignalResponse, MarketOut } from "@/types/v2/capital";

// A market's own record (slug/name) barely ever changes; its Capital Signal is safe to reuse across visitors for
// a few minutes without misleadingly claiming real-time freshness -- the page always shows the response's own
// `as_of` date rather than implying "live."
export const MARKET_REVALIDATE_SECONDS = 300;

export function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

export type MarketPageData =
  | { status: "unknown" }
  | { status: "unavailable"; market: MarketOut | null }
  | { status: "ok"; market: MarketOut; signal: CapitalSignalResponse };

// Wrapped in React's `cache()` so generateMetadata and the page component -- both of which need the same
// market+signal data -- trigger exactly one network round trip per request, not two (see Next's own
// "memoizing data requests" guidance in node_modules/next/dist/docs).
export const loadMarketPageData = cache(async (slug: string): Promise<MarketPageData> => {
  let market: MarketOut | null;

  try {
    market = await getMarketBySlug(slug, MARKET_REVALIDATE_SECONDS);
  } catch {
    // The LOOKUP ITSELF failed (network error, timeout, the V2 API unreachable) -- distinct from a market that
    // genuinely does not exist (getMarketBySlug resolving cleanly to null, handled below via "unknown"). We do
    // not yet know whether this slug is real, only that the service could not be reached to find out, so this
    // is a service problem, never reported as "this market isn't on VentureGPS."
    return { status: "unavailable", market: null };
  }

  if (!market) return { status: "unknown" };

  try {
    const signal = await getCapitalSignal(
      { marketId: market.id, taxonomyVersion: getConfiguredTaxonomyVersion(), asOf: todayIsoDate() },
      MARKET_REVALIDATE_SECONDS
    );
    return { status: "ok", market, signal };
  } catch {
    // The market itself resolved fine -- any failure fetching its Capital Signal (taxonomy misconfiguration,
    // database unavailable, a transient 5xx) is a service problem, not "this market doesn't exist."
    return { status: "unavailable", market };
  }
});
