// VentureGPS Increment 16.1 -- Direction C: Social Discovery.
//
// Concept: a mobile-native, full-viewport-height vertical story deck (CSS scroll-snap on the y-axis) -- swipe
// or scroll to the next market, TikTok/Reels-shaped. Genuinely different navigational geometry from Direction
// A's linear editorial scroll and Direction B's spatial constellation: here, only ONE slide is ever on screen
// at a time, deliberately. No JS gesture library is used -- native CSS scroll-snap already gives the swipe-like
// feel on a touch device, and degrades to normal (if snappy) scroll-wheel behavior on desktop, satisfying
// "responsive, purposeful interactions" with zero new dependencies.
import Link from "next/link";

import DirectionBadge from "@/components/markets/DirectionBadge.tsx";
import PrototypeRibbon from "@/components/design/shared/PrototypeRibbon";
import IllustrativeTag from "@/components/design/shared/IllustrativeTag";
import PlaceholderArt from "@/components/design/shared/PlaceholderArt";

import { DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";
import { SAMPLE_MARKET_SIGNALS, SAMPLE_STORIES, type SampleMarketSignal } from "@/components/design/discover/sampleData";

const PALETTE_BY_DIRECTION: Record<string, "primary" | "success" | "accent"> = {
  strong_increase: "success",
  increase: "success",
  stable: "primary",
  decrease: "accent",
  strong_decrease: "accent",
  mixed: "accent",
  insufficient_data: "primary",
};

// Every slide is real content: either a market (from sampleData) or the one video/editorial slide. A discriminated
// union keeps that explicit rather than overloading one shape with optional fields.
type Slide = { kind: "intro" } | { kind: "market"; market: SampleMarketSignal } | { kind: "video" } | { kind: "end" };

function buildSlides(): Slide[] {
  const slides: Slide[] = [{ kind: "intro" }];
  SAMPLE_MARKET_SIGNALS.forEach((market, index) => {
    slides.push({ kind: "market", market });
    if (index === 1) slides.push({ kind: "video" }); // one video/editorial slide, interspersed
  });
  slides.push({ kind: "end" });
  return slides;
}

function slideId(slide: Slide, index: number): string {
  if (slide.kind === "market") return `slide-${slide.market.slug}`;
  return `slide-${slide.kind}-${index}`;
}

function slideDotLabel(slide: Slide): string {
  if (slide.kind === "market") return slide.market.displayName;
  if (slide.kind === "video") return "The Brief";
  if (slide.kind === "intro") return "Start";
  return "End";
}

// A floating, TikTok-style share affordance -- static mock, not a functional share control (Data Honesty +
// Engineering Boundaries: no new share logic, the real ShareMarketButton already exists on the market page).
function ShareRail() {
  return (
    <div className="absolute bottom-24 right-4 flex flex-col items-center gap-4 sm:bottom-10">
      <span aria-hidden="true" className="flex size-11 items-center justify-center rounded-full border border-white/30 bg-black/30 text-lg text-white backdrop-blur-sm">
        ↗
      </span>
      <span className="text-[10px] font-medium text-white/70">Share</span>
    </div>
  );
}

export default function DirectionC() {
  const slides = buildSlides();

  return (
    <div>
      <PrototypeRibbon letter="C" name="Social Discovery" />

      <div className="relative">
        {/* Jump dots -- real anchor links to each slide's id, so desktop/keyboard users get instant, non-scroll
            navigation too, not just swipe. */}
        <nav aria-label="Jump to a slide" className="fixed right-2 top-1/2 z-20 hidden -translate-y-1/2 flex-col gap-2 sm:flex">
          {slides.map((slide, index) => (
            <a
              key={slideId(slide, index)}
              href={`#${slideId(slide, index)}`}
              aria-label={slideDotLabel(slide)}
              className="size-2 rounded-full bg-text-muted/50 transition-colors hover:bg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            />
          ))}
        </nav>

        <div className="snap-y snap-mandatory" style={{ scrollSnapType: "y mandatory" }}>
          {slides.map((slide, index) => {
            const id = slideId(slide, index);

            if (slide.kind === "intro") {
              return (
                <section key={id} id={id} className="relative flex min-h-[100svh] snap-start flex-col justify-end" style={{ scrollSnapAlign: "start" }}>
                  <PlaceholderArt palette="primary" className="absolute inset-0" />
                  <div className="relative px-6 pb-20 sm:px-10 sm:pb-28">
                    <p className="text-xs font-semibold uppercase tracking-[0.3em] text-white/70">VentureGPS</p>
                    <h1 className="mt-3 text-5xl font-black leading-[0.98] tracking-tight text-white sm:text-7xl">
                      Navigate the
                      <br />
                      Startup Economy
                    </h1>
                    <p className="mt-4 max-w-sm text-base leading-7 text-white/80">Swipe up for verified market signals &mdash; one at a time.</p>
                    <div className="mt-6 flex items-center gap-2 text-sm font-medium text-white/60">
                      <span aria-hidden="true" className="animate-bounce motion-reduce:animate-none">
                        ↑
                      </span>
                      Swipe up
                    </div>
                  </div>
                </section>
              );
            }

            if (slide.kind === "market") {
              const { market } = slide;
              const tone = DIRECTION_TONE[market.direction];
              return (
                <section key={id} id={id} className="relative flex min-h-[100svh] snap-start flex-col justify-end" style={{ scrollSnapAlign: "start" }}>
                  <PlaceholderArt palette={PALETTE_BY_DIRECTION[market.direction]} className="absolute inset-0" />
                  <ShareRail />
                  <div className="relative px-6 pb-20 sm:px-10 sm:pb-28">
                    <IllustrativeTag variant="inverted" />
                    <h2 className="mt-3 text-4xl font-bold leading-tight text-white sm:text-6xl">{market.displayName}</h2>
                    <p className="mt-2 max-w-sm text-base text-white/80">{market.oneLiner}</p>
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      <DirectionBadge symbol={DIRECTION_SYMBOL[market.direction]} label={DIRECTION_LABEL[market.direction]} tone={tone} />
                      {market.verifiedCapitalLabel !== "—" ? <span className="text-lg font-bold text-white">{market.verifiedCapitalLabel}</span> : null}
                    </div>
                  </div>
                </section>
              );
            }

            if (slide.kind === "video") {
              const story = SAMPLE_STORIES[0];
              return (
                <section key={id} id={id} className="relative flex min-h-[100svh] snap-start flex-col items-center justify-center bg-text-primary" style={{ scrollSnapAlign: "start" }}>
                  <ShareRail />
                  <div className="flex w-full max-w-xs flex-col items-center px-6 text-center">
                    <span className="flex size-16 items-center justify-center rounded-full bg-white/90 text-2xl text-background shadow-lg" aria-hidden="true">
                      ▶
                    </span>
                    <p className="mt-5 text-lg font-semibold leading-snug text-background">{story.title}</p>
                    <div className="mt-3 flex items-center gap-2">
                      <IllustrativeTag>Planned content</IllustrativeTag>
                    </div>
                    <p className="mt-2 text-xs text-background/70">{story.format} &middot; The VentureGPS Brief</p>
                  </div>
                </section>
              );
            }

            // "end" slide
            return (
              <section key={id} id={id} className="flex min-h-[100svh] snap-start flex-col items-center justify-center gap-4 bg-surface-subtle px-6 text-center" style={{ scrollSnapAlign: "start" }}>
                <p className="text-2xl font-bold text-text-primary">You&rsquo;re caught up.</p>
                <p className="max-w-xs text-sm text-text-secondary">That&rsquo;s every sample market in this prototype.</p>
                <Link href="/design/directions" className="mt-2 text-sm font-semibold text-primary hover:text-primary-hover">
                  ← Back to all three concepts
                </Link>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
