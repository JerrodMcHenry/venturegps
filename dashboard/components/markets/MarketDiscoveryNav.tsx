// VentureGPS Increment 15, Part 5 -- "a small useful navigator to other markets," explicitly NOT a discovery
// feed, personalized recommendations, a heatmap, or global search (all out of scope per this increment's
// non-goals). A server component: it fetches its own short market list independently of the page's signal
// fetch, so a slow/failed discovery fetch never blocks the page's primary content from rendering (see
// app/markets/[slug]/page.tsx, where this is awaited alongside, not before, the hero).
import Link from "next/link";

import { listMarkets } from "@/lib/api/v2/markets.ts";

type MarketDiscoveryNavProps = {
  currentSlug: string;
};

// A market list changes rarely (new markets are added by taxonomy updates, not by the minute) -- a longer
// revalidate window than the Capital Signal data itself is appropriate here.
const DISCOVERY_REVALIDATE_SECONDS = 900;
const DISCOVERY_LIMIT = 9; // fetch one extra over the display count of 8, in case the current market is in the page

export default async function MarketDiscoveryNav({ currentSlug }: MarketDiscoveryNavProps) {
  let markets: { id: string; slug: string; display_name: string }[] = [];

  try {
    const result = await listMarkets(DISCOVERY_LIMIT, 0, DISCOVERY_REVALIDATE_SECONDS);
    markets = result.markets.filter((market) => market.slug !== currentSlug).slice(0, 8);
  } catch {
    // A discovery-nav failure is never worth showing an error for -- the page's primary content (this market's
    // own data) already rendered; simply omit the navigator rather than fail the whole page.
    return null;
  }

  if (markets.length === 0) return null;

  return (
    <nav aria-labelledby="discover-heading" className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <h2 id="discover-heading" className="text-lg font-semibold text-text-primary">
        Other markets on VentureGPS
      </h2>

      <ul className="mt-4 flex flex-wrap gap-2">
        {markets.map((market) => (
          <li key={market.id}>
            <Link
              href={`/markets/${market.slug}`}
              className="inline-flex min-h-11 items-center rounded-full border border-border bg-surface px-4 text-sm font-medium text-text-secondary transition-colors hover:border-primary/40 hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              {market.display_name}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
