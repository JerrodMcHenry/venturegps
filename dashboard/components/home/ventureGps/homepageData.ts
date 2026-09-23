// VentureGPS Increment 17.1 -- the production homepage's ONLY data source. Real V2 market data and existing
// Capital Signals only (Jerrod's explicit instruction) -- this file never imports SAMPLE_MARKET_SIGNALS or any
// other fixture, and never invents a placeholder direction/number when a real one is unavailable. A market whose
// signal fetch fails is carried through with `signal: null` (a real, honest "unavailable" state, distinct from a
// real signal whose own `overall` is legitimately "insufficient_data" -- see MarketNotAvailable.tsx's identical
// unknown/unavailable distinction on /markets/[slug]) rather than silently dropped or backfilled.
//
// Bounded on purpose (Jerrod's explicit instruction): one `listMarkets` call capped at HOMEPAGE_MARKET_LIMIT,
// then at most that many `getCapitalSignal` calls, run in parallel -- never a request per visitor beyond what
// this one page load needs, and never an unbounded fetch of "every market."
import { cache } from "react";

import { getCapitalSignal, listMarkets } from "@/lib/api/v2/markets.ts";
import { getConfiguredTaxonomyVersion } from "@/lib/api/v2/taxonomyVersion.ts";

import type { CapitalSignalResponse, MarketOut } from "@/types/v2/capital";

// A market list and its Capital Signal both change slowly enough that reusing the same response across visitors
// for a few minutes is honest (the page always attributes numbers to the signal's own `as_of` date, never claims
// "live") -- same window MARKET_REVALIDATE_SECONDS uses on /markets/[slug].
const HOMEPAGE_REVALIDATE_SECONDS = 300;

// Matches the approved design's "one featured + three complementary" arrangement (Section B / the hero's
// Featured Market card) -- not a data limit chosen for its own sake, but not exceeded even if more real markets
// exist, per "keep homepage API requests bounded."
export const HOMEPAGE_MARKET_LIMIT = 4;

export type HomepageMarket = {
  market: MarketOut;
  signal: CapitalSignalResponse | null; // null = Capital Signal unavailable for this market right now (a real
  // service/coverage gap, never backfilled with a guess)
};

export type HomepageMarketsResult =
  | { status: "unavailable" } // the market list itself couldn't be fetched -- no honest content to show at all
  | { status: "empty" } // the list fetched fine and genuinely has zero markets yet
  | { status: "ok"; markets: HomepageMarket[] };

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

// Wrapped in React's cache() so a single request's generateMetadata + page render (both of which want the same
// homepage markets) trigger one network round trip each, not two -- same reasoning as
// app/markets/[slug]/page.tsx's loadMarketPageData.
export const loadHomepageMarkets = cache(async (): Promise<HomepageMarketsResult> => {
  let marketList: MarketOut[];

  try {
    const result = await listMarkets(HOMEPAGE_MARKET_LIMIT, 0, HOMEPAGE_REVALIDATE_SECONDS);
    marketList = result.markets;
  } catch {
    return { status: "unavailable" };
  }

  if (marketList.length === 0) {
    return { status: "empty" };
  }

  const taxonomyVersion = getConfiguredTaxonomyVersion();
  const asOf = todayIsoDate();

  const markets = await Promise.all(
    marketList.map(async (market): Promise<HomepageMarket> => {
      try {
        const signal = await getCapitalSignal({ marketId: market.id, taxonomyVersion, asOf }, HOMEPAGE_REVALIDATE_SECONDS);
        return { market, signal };
      } catch {
        // This one market's signal is unavailable -- the rest of the homepage (and the rest of this list) is
        // still real and still worth showing; never substitute fixture data to paper over a single gap.
        return { market, signal: null };
      }
    })
  );

  return { status: "ok", markets };
});
