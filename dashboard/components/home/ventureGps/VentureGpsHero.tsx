import Image from "next/image";
import Link from "next/link";

import PublicNav from "@/components/layout/PublicNav.tsx";
import DirectionBadge from "@/components/markets/DirectionBadge.tsx";

import { DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";

import type { HomepageMarket } from "./homepageData";

// VentureGPS Increment 17.1/17.2 -- the production hero, promoted from the approved
// components/design/cinematicHomepage/CinematicHero.tsx prototype. Preserves that prototype's approved
// structure (full-bleed section, glass headline panel, gradient "Navigate" text, featured-market card bottom-
// right on desktop) and copy verbatim. Two real, deliberate differences from the prototype:
//
// 1. IMAGE: cinematic-homepage.png is now the real, cleared background (Increment 17.2 -- see
//    public/design-references/README.md's "cleared for production" section for the rights basis). Increment
//    17.1 briefly used a rights-clear gradient placeholder here while that clearance was pending; that placeholder
//    is gone now that the real, approved image is in use.
// 2. NAV: the prototype builds its own inline nav bar (plain, non-interactive <span> labels, explicitly a
//    "(concept)" mockup). This renders the real, shared PublicNav (variant="overlay") instead -- same visual
//    position and glass treatment, but with real links and a working mobile menu, because this is now a
//    production page a visitor can actually navigate from.
//
// The featured-market card reads real data (HomepageMarket, from homepageData.ts -- never
// SAMPLE_MARKET_SIGNALS): `featured` is the first of the bounded, real markets this page fetched, or null if
// VentureGPS has no real market coverage to show yet -- rendered as an honest "building coverage" state, never a
// fabricated placeholder market. The hero's own background image is fixed (cinematic-homepage.png, the section's
// brand visual), independent of which market happens to be featured -- same as the approved prototype, which
// never swapped the hero photo per market either.
type VentureGpsHeroProps = {
  featured: HomepageMarket | null;
};

function FeaturedMarketCard({ featured }: { featured: HomepageMarket }) {
  const { market, signal } = featured;

  return (
    <div className="w-full max-w-sm rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur-xl sm:p-5 lg:w-72">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/60">Featured market</p>
      <div className="mt-2 flex items-center gap-1.5">
        <p className="text-lg font-bold text-white">{market.display_name}</p>
      </div>
      <div className="mt-2">
        {signal ? (
          <DirectionBadge symbol={DIRECTION_SYMBOL[signal.overall]} label={DIRECTION_LABEL[signal.overall]} tone={DIRECTION_TONE[signal.overall]} size="sm" />
        ) : (
          <DirectionBadge symbol={DIRECTION_SYMBOL.insufficient_data} label="Signal unavailable right now" tone="unknown" size="sm" />
        )}
      </div>
      <Link
        href={`/markets/${market.slug}`}
        className="mt-4 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-gradient-to-r from-accent to-secondary px-5 text-sm font-bold text-white shadow-lg shadow-primary/30 transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
      >
        Explore the market →
      </Link>
    </div>
  );
}

function NoCoverageCard() {
  return (
    <div className="w-full max-w-sm rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur-xl sm:p-5 lg:w-72">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/60">Featured market</p>
      <p className="mt-2 text-sm leading-6 text-white/85">VentureGPS is still building market coverage. Check back soon.</p>
    </div>
  );
}

export default function VentureGpsHero({ featured }: VentureGpsHeroProps) {
  return (
    <section aria-label="VentureGPS -- Navigate the Startup Economy" className="relative min-h-[100svh] w-full overflow-hidden bg-black">
      {/* The approved cinematic hero image (Increment 17.2 -- cleared for production; see
          public/design-references/README.md's "cleared for production" section). Same file, same crop/focus, as
          the approved /design/cinematic-homepage prototype. */}
      <Image
        src="/design-references/cinematic-homepage.png"
        alt="" // decorative -- the section's own aria-label carries the meaning.
        fill
        priority
        sizes="100vw"
        className="object-cover object-[28%_34%] sm:object-[32%_38%]"
      />

      {/* Same ambient scrims as the approved prototype -- text contrast is the glass panels' job, not a heavy
          image-wide wash (the image should read clearly everywhere except directly behind the panels). */}
      <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/5" />
      <div aria-hidden="true" className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/50 via-black/10 to-transparent" />

      <div className="relative z-10">
        <PublicNav variant="overlay" />
      </div>

      <div className="relative z-10 flex min-h-[calc(100svh-84px)] flex-col justify-end gap-6 px-4 pb-10 sm:px-8 sm:pb-14 lg:min-h-[calc(100svh-100px)]">
        <div className="max-w-lg rounded-3xl border border-white/15 bg-black/45 p-5 shadow-2xl shadow-black/40 backdrop-blur-xl sm:p-8 lg:max-w-3xl">
          <div className="mb-4 inline-flex w-fit items-center gap-2 sm:mb-5">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
            <span className="text-xs font-medium tracking-wide text-white/85">Evidence-Backed Startup Analysis</span>
          </div>

          {/* Portfolio Release Task 4 -- Phase 4 (Homepage Coherence): headline/supporting text/primary CTA
              realigned with the current portfolio-release product -- evidence-backed startup analysis -- from
              the earlier Markets-first "Navigate the Startup Economy" framing. The visual treatment itself
              (gradient word, glass panel, full-bleed hero image) is unchanged; only the copy and the addition of
              a primary CTA button (there was none before -- the only path to /analyze was a small top-nav link)
              changed. */}
          <h1 className="text-4xl font-black leading-[1.02] tracking-tight text-white sm:text-6xl lg:text-7xl">
            <span className="bg-gradient-to-r from-accent via-primary to-secondary bg-clip-text text-transparent">Evidence-backed</span>
            <br />
            startup analysis
          </h1>

          <p className="mt-4 max-w-md text-base leading-7 text-white/85 sm:mt-5 sm:text-lg">
            Submit a startup and get a defensible analysis across market, team, product, execution, traction and
            financial health -- every score backed by evidence, never a guess.
          </p>

          <Link
            href="/analyze"
            className="mt-6 inline-flex min-h-11 w-fit items-center justify-center rounded-full bg-gradient-to-r from-accent to-secondary px-6 text-sm font-bold text-white shadow-lg shadow-primary/30 transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white sm:mt-8 sm:text-base"
          >
            Analyze a startup →
          </Link>
        </div>

        <div className="lg:absolute lg:bottom-10 lg:right-8 lg:mt-0">{featured ? <FeaturedMarketCard featured={featured} /> : <NoCoverageCard />}</div>
      </div>
    </section>
  );
}
