"use client";

// VentureGPS Increment 16.3 -- Section B's desktop interaction (Part 4): selecting one of the three
// "complementary" tiles swaps it into the large "featured" position, and whichever market WAS featured moves
// back into the tile list -- a real, working selection, not a static illustration of one. Real <button>
// elements throughout (keyboard-operable, focus-visible rings) rather than div-based click targets; the
// transition on the featured pane's image is `motion-reduce:transition-none`-guarded (Part 4: "compatible with
// reduced-motion preferences"). No animation library -- a single CSS opacity/transform transition.
//
// Interaction bug fix investigation (Increment 16.3.1 -> 16.3.2): Jerrod reported clicking a tile does nothing,
// retested with browser automation extensions disabled, and confirmed it was a real bug, not an artifact of the
// investigation tooling. The actual root cause: Next.js 16's dev server treats "127.0.0.1" and "localhost" as
// different origins and, by default, blocks cross-origin access to its own dev resources (including the
// Turbopack `/_next/hmr` endpoint) -- reached via 127.0.0.1, that block cascaded into React never completing
// hydration ANYWHERE on the page, not just here, which presents as every onClick handler in the app doing
// nothing while the server-rendered HTML still looks correct. Fixed in dashboard/next.config.ts
// (`allowedDevOrigins`), not in this component -- see that file's own comment and
// docs/product/VENTUREGPS_CONSUMER_EXPERIENCE_BLUEPRINT_V1.md's Increment 16.3.2 section for the full writeup.
// `selectFeaturedMarket` below is pulled out as a pure function specifically so its correctness can be verified
// by an automated test independent of the browser -- see interactionLogic.ts and
// tests/v2SectionBInteraction.test.ts.
import { useState } from "react";
import Image from "next/image";
import Link from "next/link";

import DirectionBadge from "@/components/markets/DirectionBadge.tsx";
import IllustrativeTag from "@/components/design/shared/IllustrativeTag";

import { DIRECTION_EXPLANATION, DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";
import { SECTION_B_MARKETS, type SectionBMarket } from "./sectionBMarkets";
import { selectFeaturedMarket } from "./interactionLogic";

function initialFeaturedSlug(): string {
  return SECTION_B_MARKETS.find((m) => m.featured)?.market.slug ?? SECTION_B_MARKETS[0].market.slug;
}

export default function MarketShowcaseDesktop() {
  const [selectedSlug, setSelectedSlug] = useState(initialFeaturedSlug);

  const { featured, others } = selectFeaturedMarket(SECTION_B_MARKETS, selectedSlug);
  const tone = DIRECTION_TONE[featured.market.direction];
  const sufficientHistory = featured.market.direction !== "insufficient_data";

  return (
    <div className="mx-auto hidden max-w-6xl gap-4 px-4 pb-20 sm:px-6 lg:grid lg:grid-cols-[2fr_1fr]">
      {/* The featured pane. */}
      <div className="relative aspect-[16/10] overflow-hidden rounded-3xl bg-black">
        <Image
          key={featured.market.slug}
          src={featured.image}
          alt=""
          fill
          sizes="(min-width: 1024px) 66vw, 100vw"
          className="object-cover transition-opacity duration-300 motion-reduce:transition-none"
          style={{ objectPosition: featured.imageObjectPosition }}
        />
        <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />

        <div className="absolute inset-x-0 bottom-0 p-6">
          <div className="max-w-md rounded-2xl border border-white/15 bg-black/45 p-5 backdrop-blur-xl">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xl font-bold text-white">{featured.displayName}</p>
              <IllustrativeTag variant="inverted" />
            </div>

            {sufficientHistory ? (
              <div className="mt-2">
                <DirectionBadge symbol={DIRECTION_SYMBOL[featured.market.direction]} label={DIRECTION_LABEL[featured.market.direction]} tone={tone} size="sm" />
              </div>
            ) : (
              <div className="mt-2">
                <DirectionBadge symbol={DIRECTION_SYMBOL.insufficient_data} label={DIRECTION_LABEL.insufficient_data} tone="unknown" size="sm" />
              </div>
            )}

            <p className="mt-2 text-sm leading-6 text-white/80">{DIRECTION_EXPLANATION[featured.market.direction]}</p>

            <Link
              href={`/markets/${featured.market.slug}`}
              className="mt-4 inline-flex min-h-11 items-center rounded-xl bg-gradient-to-r from-accent to-secondary px-5 text-sm font-bold text-white shadow-lg shadow-primary/30 transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              Explore the market →
            </Link>
          </div>
        </div>
      </div>

      {/* The three complementary tiles -- whichever markets AREN'T currently featured. `h-full` picks up the
          grid's own default `align-items: stretch` (both this element and the featured pane are direct children
          of the same single-row `lg:grid-cols-[2fr_1fr]` grid, so this stretches to match the featured pane's
          own aspect-ratio-driven height) -- `grid-rows-3`'s implicit `1fr` tracks then divide that real height
          evenly, rather than each tile falling back to its own small `min-h-28` and leaving the column visibly
          shorter than the featured pane beside it. */}
      <div className="grid h-full grid-rows-3 gap-4" role="group" aria-label="Other markets -- select one to feature it">
        {others.map((entry) => (
          <MarketTileButton
            key={entry.market.slug}
            entry={entry}
            onSelect={() => setSelectedSlug(entry.market.slug)}
          />
        ))}
      </div>
    </div>
  );
}

function MarketTileButton({ entry, onSelect }: { entry: SectionBMarket; onSelect: () => void }) {
  const tone = DIRECTION_TONE[entry.market.direction];

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-label={`Feature ${entry.displayName}: ${DIRECTION_LABEL[entry.market.direction]}`}
      className="group relative min-h-28 overflow-hidden rounded-2xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <Image
        src={entry.image}
        alt=""
        fill
        sizes="(min-width: 1024px) 22vw, 100vw"
        className="object-cover transition-transform duration-300 group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100"
        style={{ objectPosition: entry.imageObjectPosition }}
      />
      <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-black/10" />
      <div className="relative flex h-full flex-col justify-end p-4">
        <p className="text-base font-bold text-white">{entry.displayName}</p>
        <div className="mt-1.5">
          <DirectionBadge symbol={DIRECTION_SYMBOL[entry.market.direction]} label={DIRECTION_LABEL[entry.market.direction]} tone={tone} size="sm" />
        </div>
      </div>
    </button>
  );
}
