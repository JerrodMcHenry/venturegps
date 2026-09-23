import MarketDiscoveryIntro from "./MarketDiscoveryIntro";
import MarketShowcaseDesktop from "./MarketShowcaseDesktop";
import MarketCarouselMobile from "./MarketCarouselMobile";

import type { HomepageMarketsResult } from "./homepageData";
import type { MarketDiscoveryCard } from "./marketDiscoveryCard";

// VentureGPS Increment 17.1 -- promoted from the approved
// components/design/cinematicHomepage/sectionB/SectionB.tsx prototype. Same two-components-not-one structure
// (desktop click-to-feature vs. mobile swipe are genuinely different interaction models -- see that file's own
// comment), now driven by `result: HomepageMarketsResult` (real V2 data, homepageData.ts) instead of
// SAMPLE_MARKET_SIGNALS. Three real, honest outcomes, never a fabricated fourth:
// - "unavailable": the market list itself couldn't be fetched -- an explicit unavailable message, not an empty
//   section that looks like a bug.
// - "empty": the fetch worked and there is genuinely no market coverage yet -- an explicit "building coverage"
//   message, not sample markets standing in for real ones.
// - "ok": real markets, rendered through the same interaction components as the prototype.
export default function MarketDiscoverySection({ result }: { result: HomepageMarketsResult }) {
  return (
    <section aria-labelledby="market-discovery-heading" className="bg-background">
      <MarketDiscoveryIntro />
      {result.status === "ok" ? <MarketDiscoveryContent result={result} /> : <MarketDiscoveryUnavailable status={result.status} />}
    </section>
  );
}

function MarketDiscoveryContent({ result }: { result: Extract<HomepageMarketsResult, { status: "ok" }> }) {
  const markets: MarketDiscoveryCard[] = result.markets.map(({ market, signal }) => ({
    slug: market.slug,
    displayName: market.display_name,
    direction: signal?.overall ?? null,
  }));

  return (
    <>
      <MarketShowcaseDesktop markets={markets} />
      <div className="pb-16">
        <MarketCarouselMobile markets={markets} />
      </div>
    </>
  );
}

function MarketDiscoveryUnavailable({ status }: { status: "unavailable" | "empty" }) {
  return (
    <div className="mx-auto max-w-md px-4 pb-20 text-center">
      <p className="text-sm leading-6 text-text-secondary">
        {status === "unavailable"
          ? "VentureGPS couldn't reach market data just now. Try again in a moment."
          : "VentureGPS is still building market coverage. Check back soon."}
      </p>
    </div>
  );
}
