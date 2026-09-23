"use client";

// VentureGPS Increment 17.1/17.2 -- promoted from the approved
// components/design/cinematicHomepage/sectionB/MarketCarouselMobile.tsx prototype, INCLUDING the Increment
// 16.3.2 interaction fixes: `handleScroll` measures the real per-slide step from two consecutive slides'
// `offsetLeft` (never the track's own `clientWidth`, which desynced the active dot from slide 2 onward -- see
// that file's own comment for the full writeup) and `goTo` keeps `scrollIntoView`, not a documented-and-reverted
// `scrollTo` swap that did not actually fix anything. Same data/imagery approach as MarketShowcaseDesktop.tsx
// (this file's sibling) -- see that file's header comment, and MarketCardBackground.tsx.
import { useRef, useState } from "react";
import Link from "next/link";

import DirectionBadge from "@/components/markets/DirectionBadge.tsx";

import { DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";
import { clampCarouselIndex, indexFromScrollPosition } from "./interactionLogic";
import MarketCardBackground from "./MarketCardBackground";
import type { MarketDiscoveryCard } from "./marketDiscoveryCard";

type MarketCarouselMobileProps = {
  markets: MarketDiscoveryCard[];
};

export default function MarketCarouselMobile({ markets }: MarketCarouselMobileProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);

  function goTo(index: number) {
    const track = trackRef.current;
    if (!track) return;
    const clamped = clampCarouselIndex(index, markets.length);
    const slide = track.children[clamped] as HTMLElement | undefined;
    const prefersReducedMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    slide?.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", inline: "start", block: "nearest" });
    setActiveIndex(clamped);
  }

  function handleScroll() {
    const track = trackRef.current;
    if (!track) return;
    const [first, second] = track.children as unknown as HTMLElement[];
    const step = first && second ? second.offsetLeft - first.offsetLeft : track.clientWidth;
    setActiveIndex(indexFromScrollPosition(track.scrollLeft, step, markets.length));
  }

  if (markets.length === 0) return null;

  return (
    <div className="lg:hidden">
      <div
        ref={trackRef}
        onScroll={handleScroll}
        className="flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-2 sm:px-6"
        style={{ scrollSnapType: "x mandatory" }}
        role="group"
        aria-label="Markets carousel -- swipe or use the controls below to browse"
      >
        {markets.map((entry, index) => {
          const tone = entry.direction ? DIRECTION_TONE[entry.direction] : "unknown";
          const symbol = entry.direction ? DIRECTION_SYMBOL[entry.direction] : DIRECTION_SYMBOL.insufficient_data;
          const label = entry.direction ? DIRECTION_LABEL[entry.direction] : "Signal unavailable right now";
          return (
            <div key={entry.slug} className="relative aspect-[4/5] w-[85vw] shrink-0 snap-start overflow-hidden rounded-3xl bg-black sm:w-[70vw]">
              <MarketCardBackground slug={entry.slug} index={index} sizes="85vw" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent" />
              <div className="absolute inset-x-0 bottom-0 p-5">
                <p className="text-xl font-bold text-white">{entry.displayName}</p>
                <div className="mt-2">
                  <DirectionBadge symbol={symbol} label={label} tone={tone} size="sm" />
                </div>
                <Link
                  href={`/markets/${entry.slug}`}
                  className="mt-4 inline-flex min-h-11 items-center rounded-xl bg-gradient-to-r from-accent to-secondary px-5 text-sm font-bold text-white shadow-lg shadow-primary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                >
                  Explore the market →
                </Link>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex items-center justify-center gap-5 px-4">
        <button
          type="button"
          onClick={() => goTo(activeIndex - 1)}
          disabled={activeIndex === 0}
          aria-label="Previous market"
          className="flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border text-text-secondary disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          ←
        </button>

        <div className="flex items-center gap-2">
          {markets.map((entry, index) => (
            <button
              key={entry.slug}
              type="button"
              onClick={() => goTo(index)}
              aria-label={`Go to ${entry.displayName}`}
              aria-current={index === activeIndex}
              className={["size-2.5 rounded-full transition-colors", index === activeIndex ? "bg-primary" : "bg-border"].join(" ")}
            />
          ))}
        </div>

        <button
          type="button"
          onClick={() => goTo(activeIndex + 1)}
          disabled={activeIndex === markets.length - 1}
          aria-label="Next market"
          className="flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border text-text-secondary disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          →
        </button>
      </div>
    </div>
  );
}
