"use client";

// VentureGPS Increment 16.3 -- Section B's mobile interaction (Part 4): a swipeable carousel, one market per
// full-width slide, native CSS scroll-snap (no gesture/carousel library -- Section 8: "do not add unnecessary
// animation libraries"). "Visible navigation" is two real things, not decoration: dot buttons that jump to a
// slide (`scrollIntoView`) and prev/next buttons -- all real `<button>`s, so the whole carousel is keyboard-
// operable (Tab to a dot/arrow, Enter/Space to activate) even though the primary interaction is touch-swipe.
//
// Interaction bug fix investigation (Increment 16.3.1 -> 16.3.2): Jerrod reported the prev/next arrows did
// nothing, retested with browser automation extensions disabled, and confirmed it was a real bug. The actual
// root cause -- a Next.js dev-server origin-blocking issue that stopped hydration from completing anywhere on
// the page -- is documented in MarketShowcaseDesktop.tsx's comment, dashboard/next.config.ts, and
// docs/product/VENTUREGPS_CONSUMER_EXPERIENCE_BLUEPRINT_V1.md's Increment 16.3.2 section. Once hydration was
// fixed, a second, narrower bug surfaced here specifically: `handleScroll` synced the active dot to the scroll
// position using the track's `clientWidth` as the per-slide step, but slides are deliberately narrower than the
// track (the next one peeks in) -- see that function's own comment below for the fix. `clampCarouselIndex`/
// `indexFromScrollPosition` are pulled out as pure functions specifically so their correctness is verifiable by
// an automated test -- see interactionLogic.ts and tests/v2SectionBInteraction.test.ts.
import { useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";

import DirectionBadge from "@/components/markets/DirectionBadge.tsx";
import IllustrativeTag from "@/components/design/shared/IllustrativeTag";

import { DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";
import { SECTION_B_MARKETS } from "./sectionBMarkets";
import { clampCarouselIndex, indexFromScrollPosition } from "./interactionLogic";

export default function MarketCarouselMobile() {
  const trackRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);

  function goTo(index: number) {
    const track = trackRef.current;
    if (!track) return;
    const clamped = clampCarouselIndex(index, SECTION_B_MARKETS.length);
    const slide = track.children[clamped] as HTMLElement | undefined;
    // Reduced-motion: jump instantly rather than animate the scroll (Part 4's own requirement) -- checked at
    // click time, not cached, so it stays correct if the OS preference changes mid-session.
    const prefersReducedMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    slide?.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", inline: "start", block: "nearest" });
    setActiveIndex(clamped);
  }

  // Keeps the dots in sync when a visitor swipes by hand rather than using the buttons -- reads which slide is
  // nearest the scroll position on scroll-end, not on every scroll frame (no per-frame work, no dependency on
  // IntersectionObserver, which would be overkill for four slides).
  //
  // Increment 16.3.2 bug fix: this used to pass `track.clientWidth` as the per-slide step, but slides are
  // deliberately narrower than the track (`w-[85vw]`, so the next slide peeks in) plus a `gap-4` between them --
  // the real step between slide start positions is smaller than the container's width. Using clientWidth made
  // indexFromScrollPosition compute the wrong (usually one-too-low) index for every slide but the first two,
  // desyncing the dots/disabled-arrow-state from the slide actually in view. The real step is measured directly
  // from two consecutive slides' offsetLeft, which already accounts for the slide width and the gap.
  function handleScroll() {
    const track = trackRef.current;
    if (!track) return;
    const [first, second] = track.children as unknown as HTMLElement[];
    const step = first && second ? second.offsetLeft - first.offsetLeft : track.clientWidth;
    setActiveIndex(indexFromScrollPosition(track.scrollLeft, step, SECTION_B_MARKETS.length));
  }

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
        {SECTION_B_MARKETS.map((entry) => {
          const tone = DIRECTION_TONE[entry.market.direction];
          return (
            <div key={entry.market.slug} className="relative aspect-[4/5] w-[85vw] shrink-0 snap-start overflow-hidden rounded-3xl bg-black sm:w-[70vw]">
              <Image src={entry.image} alt="" fill sizes="85vw" className="object-cover" style={{ objectPosition: entry.imageObjectPosition }} />
              <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent" />
              <div className="absolute inset-x-0 bottom-0 p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-xl font-bold text-white">{entry.displayName}</p>
                  <IllustrativeTag variant="inverted" />
                </div>
                <div className="mt-2">
                  <DirectionBadge symbol={DIRECTION_SYMBOL[entry.market.direction]} label={DIRECTION_LABEL[entry.market.direction]} tone={tone} size="sm" />
                </div>
                <Link
                  href={`/markets/${entry.market.slug}`}
                  className="mt-4 inline-flex min-h-11 items-center rounded-xl bg-gradient-to-r from-accent to-secondary px-5 text-sm font-bold text-white shadow-lg shadow-primary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                >
                  Explore the market →
                </Link>
              </div>
            </div>
          );
        })}
      </div>

      {/* Visible navigation: prev/next + dots, all real buttons. */}
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
          {SECTION_B_MARKETS.map((entry, index) => (
            <button
              key={entry.market.slug}
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
          disabled={activeIndex === SECTION_B_MARKETS.length - 1}
          aria-label="Next market"
          className="flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border text-text-secondary disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          →
        </button>
      </div>
    </div>
  );
}
