// VentureGPS Increment 16, Section 4C -- a browsable grid of markets, the "explore" job distinct from the
// Signals rail above (that rail is about WHAT'S NOTABLE right now; this grid is about BROWSING the catalog).
// Reuses MarketSignalCard in its `compact` grid mode rather than inventing a second card component.
import MarketSignalCard from "./MarketSignalCard";

import type { SampleMarketSignal } from "./sampleData";

type ExploreMarketsSectionProps = {
  markets: SampleMarketSignal[];
};

export default function ExploreMarketsSection({ markets }: ExploreMarketsSectionProps) {
  return (
    <section aria-labelledby="explore-markets-heading" className="border-b border-border py-10 sm:py-14">
      <div className="mx-auto max-w-3xl px-4 sm:px-6">
        <h2 id="explore-markets-heading" className="text-2xl font-bold text-text-primary sm:text-3xl">
          Explore markets
        </h2>
        <p className="mt-2 max-w-xl text-base leading-7 text-text-secondary">
          Every market VentureGPS tracks, in one place. In this prototype, cards are for browsing only (Section
          11&rsquo;s isolation requirement) &mdash; the real market page already exists at{" "}
          <code className="rounded bg-surface-muted px-1 py-0.5 text-sm">/markets/[slug]</code>.
        </p>

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {markets.map((market) => (
            <MarketSignalCard key={market.slug} market={market} compact />
          ))}
        </div>
      </div>
    </section>
  );
}
