// VentureGPS Increment 16.1 -- Direction A: Cinematic Editorial.
//
// Concept: VentureGPS as a technology PUBLICATION first, a data tool second -- large type, full-bleed
// compositions, one thing at a time. Navigation is vertical scroll through "chapters," not a grid of cards
// (Increment 16's own critique: "repetitive rectangular cards, small charts, too much explanatory text"). Every
// section is full-width and deliberately spacious -- the opposite instinct from a dashboard's density.
import Link from "next/link";

import DirectionBadge from "@/components/markets/DirectionBadge.tsx";
import PrototypeRibbon from "@/components/design/shared/PrototypeRibbon";
import IllustrativeTag from "@/components/design/shared/IllustrativeTag";
import PlaceholderArt from "@/components/design/shared/PlaceholderArt";

import { DIRECTION_EXPLANATION, DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";
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

function Chapter({ market, index }: { market: SampleMarketSignal; index: number }) {
  const reversed = index % 2 === 1;
  const tone = DIRECTION_TONE[market.direction];

  return (
    <article className="border-b border-border">
      <div
        className={[
          "mx-auto flex max-w-6xl flex-col gap-8 px-4 py-16 sm:px-6 sm:py-20 lg:flex-row lg:items-center lg:gap-16",
          reversed ? "lg:flex-row-reverse" : "",
        ].join(" ")}
      >
        <PlaceholderArt palette={PALETTE_BY_DIRECTION[market.direction]} className="aspect-[4/3] w-full rounded-3xl lg:w-1/2">
          <div className="absolute inset-0 flex items-end p-6">
            <DirectionBadge symbol={DIRECTION_SYMBOL[market.direction]} label={DIRECTION_LABEL[market.direction]} tone={tone} />
          </div>
        </PlaceholderArt>

        <div className="lg:w-1/2">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Chapter {String(index + 1).padStart(2, "0")}</p>
          <h3 className="mt-3 text-4xl font-bold leading-[1.05] tracking-tight text-text-primary sm:text-5xl">{market.displayName}</h3>
          <p className="mt-4 max-w-md text-lg leading-8 text-text-secondary">{market.oneLiner}.</p>
          <p className="mt-4 max-w-md text-base leading-7 text-text-muted">{DIRECTION_EXPLANATION[market.direction]}</p>
          <div className="mt-6 flex items-center gap-3">
            <IllustrativeTag />
            <span className="text-sm font-semibold text-text-secondary">{market.verifiedCapitalLabel}</span>
          </div>
        </div>
      </div>
    </article>
  );
}

export default function DirectionA() {
  const featuredStory = SAMPLE_STORIES[0];
  const featuredMarket = SAMPLE_MARKET_SIGNALS.find((m) => m.slug === featuredStory.marketSlug) ?? SAMPLE_MARKET_SIGNALS[0];

  return (
    <div>
      <PrototypeRibbon letter="A" name="Cinematic Editorial" />

      {/* 1. FIRST SCREEN -- full-bleed hero, oversized type, one clear scroll cue. No nav clutter, no metrics. */}
      <PlaceholderArt palette="primary" className="flex min-h-[calc(100svh-84px)] flex-col justify-end">
        <div className="relative mx-auto w-full max-w-6xl px-4 pb-14 pt-24 sm:px-6 sm:pb-20">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-white/70">VentureGPS</p>
          <h1 className="mt-4 text-6xl font-black leading-[0.95] tracking-tight text-white sm:text-8xl">
            Navigate the
            <br />
            Startup Economy
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-white/80 sm:text-xl">
            The startup economy, told through verified financing activity &mdash; not forecasts, not hype. A
            technology publication built on evidence.
          </p>
          <div className="mt-8 flex items-center gap-2 text-sm font-medium text-white/60">
            <span aria-hidden="true" className="animate-bounce motion-reduce:animate-none">
              ↓
            </span>
            Scroll to explore
          </div>
        </div>
      </PlaceholderArt>

      {/* 2. FEATURED STORY -- distinct from the chapters below: this is the "story," they are "the intelligence." */}
      <section aria-labelledby="featured-heading" className="border-b border-border bg-surface-subtle">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Featured story</p>
            <IllustrativeTag>Planned content</IllustrativeTag>
          </div>
          <h2 id="featured-heading" className="mt-3 max-w-3xl text-3xl font-bold leading-tight text-text-primary sm:text-5xl">
            {featuredStory.title}
          </h2>
          <p className="mt-4 max-w-xl text-base leading-7 text-text-secondary">
            {featuredStory.format} &middot; would connect to the {featuredMarket.displayName} market
          </p>
          <PlaceholderArt palette="accent" className="mt-8 flex aspect-video w-full max-w-3xl items-center justify-center rounded-3xl">
            <span aria-hidden="true" className="flex size-16 items-center justify-center rounded-full bg-white/90 text-2xl text-background shadow-lg">
              ▶
            </span>
          </PlaceholderArt>
        </div>
      </section>

      {/* 3. EDITORIAL CHAPTERS -- vertical scroll, alternating composition, one market at a time. This is the
          "market discovery" interaction for this direction: read through, not browse a grid. */}
      <section aria-labelledby="chapters-heading">
        <div className="mx-auto max-w-6xl px-4 pt-16 sm:px-6">
          <h2 id="chapters-heading" className="text-sm font-semibold uppercase tracking-[0.2em] text-text-muted">
            The markets, one at a time
          </h2>
        </div>
        {SAMPLE_MARKET_SIGNALS.map((market, index) => (
          <Chapter key={market.slug} market={market} index={index} />
        ))}
      </section>

      {/* 4. VIDEO / EDITORIAL SECTION -- The Brief, editorial treatment (list, not cards). */}
      <section aria-labelledby="brief-heading" className="border-b border-border bg-surface-subtle">
        <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 sm:py-20">
          <div className="flex items-center gap-2">
            <h2 id="brief-heading" className="text-3xl font-bold text-text-primary">
              The VentureGPS Brief
            </h2>
            <IllustrativeTag>Planned</IllustrativeTag>
          </div>
          <p className="mt-3 max-w-xl text-base leading-7 text-text-secondary">
            Video breakdowns and written analysis, each grounded in the same verified intelligence as the market
            pages themselves.
          </p>
          <ol className="mt-8 space-y-6">
            {SAMPLE_STORIES.map((story, index) => (
              <li key={story.title} className="flex gap-5 border-t border-border pt-6 first:border-t-0 first:pt-0">
                <span className="text-2xl font-bold text-text-muted">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <p className="text-lg font-semibold text-text-primary">{story.title}</p>
                  <p className="mt-1 text-sm text-text-muted">
                    {story.format}
                    {story.marketSlug ? ` · ${story.marketSlug}` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 5. SHARING CONCEPT -- an oversized magazine-style pull-quote graphic. */}
      <section aria-labelledby="share-heading" className="py-16 sm:py-20">
        <div className="mx-auto max-w-3xl px-4 sm:px-6">
          <h2 id="share-heading" className="text-xl font-bold text-text-primary">
            Built to be quoted
          </h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-text-secondary">
            A shareable pull-quote card, generated from a market&rsquo;s real Capital Signal language &mdash; static
            mock here, not a functional share control (the real share action already exists on the production
            market page).
          </p>

          <div aria-hidden="true" className="mt-6 max-w-xl rounded-3xl border border-border bg-text-primary p-10 text-background">
            <p className="text-2xl font-bold leading-snug sm:text-3xl">
              &ldquo;{featuredMarket.displayName} activity stands at or above the top of its own last 8 historical
              periods.&rdquo;
            </p>
            <p className="mt-6 text-sm font-medium opacity-70">VentureGPS &middot; Navigate the Startup Economy</p>
          </div>
        </div>
      </section>

      <footer className="border-t border-border py-10 text-center">
        <Link href="/design/directions" className="text-sm font-semibold text-primary hover:text-primary-hover">
          ← Back to all three concepts
        </Link>
      </footer>
    </div>
  );
}
