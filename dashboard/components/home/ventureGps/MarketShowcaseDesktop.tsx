"use client";

// VentureGPS Increment 17.1/17.2 -- promoted from the approved
// components/design/cinematicHomepage/sectionB/MarketShowcaseDesktop.tsx prototype. Same interaction (click a
// secondary tile to feature it; the previously featured market returns to the tile list; keyboard-operable
// plain <button>s), same `selectFeaturedMarket` index math (see interactionLogic.ts's own header comment for why
// this is a standalone copy, not an import from the prototype tree). Two real differences:
// - Data: `markets` is real (HomepageMarket[] -> MarketDiscoveryCard[], from homepageData.ts), never
//   SAMPLE_MARKET_SIGNALS. A market whose signal is null renders DirectionBadge's own "insufficient_data"
//   treatment -- the same honest vocabulary the real /markets/[slug] page already uses for that case, not a
//   fabricated direction.
// - Imagery: MarketCardBackground.tsx renders the real, approved per-market photo (Increment 17.2 -- see
//   public/design-references/README.md's "cleared for production" section) when this market's slug has one, or
//   a rights-clear gradient placeholder otherwise (a real market the approved image set doesn't cover yet).
import { useState } from "react";
import Link from "next/link";

import DirectionBadge from "@/components/markets/DirectionBadge.tsx";

import { DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";
import { selectFeaturedMarket } from "./interactionLogic";
import MarketCardBackground from "./MarketCardBackground";
import type { MarketDiscoveryCard } from "./marketDiscoveryCard";

type MarketShowcaseDesktopProps = {
  markets: MarketDiscoveryCard[];
};

export default function MarketShowcaseDesktop({ markets }: MarketShowcaseDesktopProps) {
  const [selectedSlug, setSelectedSlug] = useState(markets[0]?.slug ?? "");

  const { featured, others } = selectFeaturedMarket(markets, selectedSlug);
  const featuredIndex = markets.findIndex((m) => m.slug === featured.slug);
  const tone = featured.direction ? DIRECTION_TONE[featured.direction] : "unknown";

  return (
    <div className="mx-auto hidden max-w-6xl gap-4 px-4 pb-20 sm:px-6 lg:grid lg:grid-cols-[2fr_1fr]">
      <div className="relative aspect-[16/10] overflow-hidden rounded-3xl bg-black">
        <MarketCardBackground slug={featured.slug} index={featuredIndex} sizes="(min-width: 1024px) 66vw, 100vw" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />

        <div className="absolute inset-x-0 bottom-0 p-6">
          <div className="max-w-md rounded-2xl border border-white/15 bg-black/45 p-5 backdrop-blur-xl">
            <p className="text-xl font-bold text-white">{featured.displayName}</p>

            <div className="mt-2">
              {featured.direction ? (
                <DirectionBadge symbol={DIRECTION_SYMBOL[featured.direction]} label={DIRECTION_LABEL[featured.direction]} tone={tone} size="sm" />
              ) : (
                <DirectionBadge symbol={DIRECTION_SYMBOL.insufficient_data} label="Signal unavailable right now" tone="unknown" size="sm" />
              )}
            </div>

            <Link
              href={`/markets/${featured.slug}`}
              className="mt-4 inline-flex min-h-11 items-center rounded-xl bg-gradient-to-r from-accent to-secondary px-5 text-sm font-bold text-white shadow-lg shadow-primary/30 transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              Explore the market →
            </Link>
          </div>
        </div>
      </div>

      <div className="grid h-full grid-rows-3 gap-4" role="group" aria-label="Other markets -- select one to feature it">
        {others.map((entry) => {
          const entryIndex = markets.findIndex((m) => m.slug === entry.slug);
          return <MarketTileButton key={entry.slug} entry={entry} index={entryIndex} onSelect={() => setSelectedSlug(entry.slug)} />;
        })}
      </div>
    </div>
  );
}

function MarketTileButton({ entry, index, onSelect }: { entry: MarketDiscoveryCard; index: number; onSelect: () => void }) {
  const label = entry.direction ? DIRECTION_LABEL[entry.direction] : "Signal unavailable right now";
  const tone = entry.direction ? DIRECTION_TONE[entry.direction] : "unknown";
  const symbol = entry.direction ? DIRECTION_SYMBOL[entry.direction] : DIRECTION_SYMBOL.insufficient_data;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-label={`Feature ${entry.displayName}: ${label}`}
      className="group relative min-h-28 overflow-hidden rounded-2xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <MarketCardBackground slug={entry.slug} index={index} sizes="(min-width: 1024px) 22vw, 100vw" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-black/10" />
      <div className="relative flex h-full flex-col justify-end p-4">
        <p className="text-base font-bold text-white">{entry.displayName}</p>
        <div className="mt-1.5">
          <DirectionBadge symbol={symbol} label={label} tone={tone} size="sm" />
        </div>
      </div>
    </button>
  );
}
