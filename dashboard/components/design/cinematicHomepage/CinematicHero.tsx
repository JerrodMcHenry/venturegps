import Image from "next/image";
import Link from "next/link";

import DirectionBadge from "@/components/markets/DirectionBadge.tsx";
import IllustrativeTag from "@/components/design/shared/IllustrativeTag";

import { DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";
import { SAMPLE_MARKET_SIGNALS } from "@/components/design/discover/sampleData";

// VentureGPS Increment 16.2 -- the cinematic hero, refined per Jerrod's approved-direction feedback. Built
// directly from the three reference images (see public/design-references/README.md for full provenance/
// licensing notes -- none is real photography of a real company, captioned everywhere used):
//
// - `cinematic-homepage.png` (primary reference): the real hero background image (`next/image`, `fill`).
// - `mobile-discovery-reference.png`: reused for its glassmorphism CARD language (backdrop-blur, translucent
//   surface), not as an image itself (it's a UI mockup with placeholder mockup text -- see the README).
// - `editorial-composition-reference.png`: reused for its dot-eyebrow pill, gradient-headline technique, and
//   gradient CTA pill -- never its "RoboTech" name/branding.
//
// Composition refinement pass (previous increment) -- five changes, no redesign: two-line headline with a
// wider desktop text column; replaced supporting copy; the featured-market panel became its own standalone
// card, bottom-right on desktop; the app's shared PublicHeader no longer renders above this one route
// (AppShell.tsx's `BARE_ROUTE_PREFIXES`); the full-width PrototypeRibbon banner replaced by a small corner
// disclaimer (CinematicPrototypeDisclaimer) for this route only.
//
// Readability refinement pass (this increment) -- three targeted changes, still no redesign:
// 1. The eyebrow/headline/copy now sit inside one translucent dark glass panel (`bg-black/45 backdrop-blur-xl`,
//    a soft border, generous padding) -- guarantees text contrast regardless of what's directly behind it in
//    the photo, while the image still shows through the blur (never opaque). The eyebrow's own separate pill
//    background from the previous pass was removed -- redundant once it sits inside a panel that already
//    provides contrast.
// 2. The nav bar gets a LIGHTER version of the same glass treatment (`bg-black/20 backdrop-blur-md`, a hairline
//    bottom border) -- distinct from the heavier headline panel, but enough to keep the wordmark and nav labels
//    (now full-opacity white, not `/75`) readable over the image's brightest neon highlights, which sit right
//    behind this bar.
// 3. Both ambient scrims (the two gradient divs below) were LIGHTENED, not removed -- now that the panels
//    themselves carry the contrast job, the image doesn't need a heavy image-wide wash just to make two small
//    regions of it legible ("do not darken the entire hero excessively"). The Featured Market card is
//    untouched -- same glass treatment and position as before, no second new panel added anywhere.
const featured = SAMPLE_MARKET_SIGNALS.find((m) => m.slug === "robotics") ?? SAMPLE_MARKET_SIGNALS[0];
const tone = DIRECTION_TONE[featured.direction];

const NAV_ITEMS = ["Discover", "Markets", "Companies", "Stories"];

function FeaturedMarketCard() {
  return (
    <div className="w-full max-w-sm rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur-xl sm:p-5 lg:w-72">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/60">Featured market</p>
      <div className="mt-2 flex items-center gap-1.5">
        <p className="text-lg font-bold text-white">{featured.displayName}</p>
        <IllustrativeTag variant="inverted" />
      </div>
      <div className="mt-2">
        <DirectionBadge symbol={DIRECTION_SYMBOL[featured.direction]} label={DIRECTION_LABEL[featured.direction]} tone={tone} size="sm" />
      </div>
      <Link
        href={`/markets/${featured.slug}`}
        className="mt-4 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-gradient-to-r from-accent to-secondary px-5 text-sm font-bold text-white shadow-lg shadow-primary/30 transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
      >
        Explore the market →
      </Link>
    </div>
  );
}

export default function CinematicHero() {
  return (
    <section
      aria-label="VentureGPS -- Navigate the Startup Economy"
      className="relative min-h-[100svh] w-full overflow-hidden bg-black"
    >
      <Image
        src="/design-references/cinematic-homepage.png"
        alt="" // decorative -- the section's own aria-label carries the meaning.
        fill
        priority
        sizes="100vw"
        // Refinement pass: nudged vertical focus up from 38%/42% to 34%/38% (a few percent tighter toward the
        // top of frame). Worked out against the source's real 1920x1080 geometry: at a narrow mobile aspect
        // ratio, object-cover's height-matched scaling crops most of the image's width away, and the original
        // vertical bias left too little headroom above the taller robot's head in that crop -- this keeps more
        // of it in frame across the phone widths this hero needs to work at (390/375/430).
        className="object-cover object-[28%_34%] sm:object-[32%_38%]"
      />

      {/* Readability refinement pass: the two ambient scrims are deliberately lighter than the previous pass --
          text contrast is now the glass panels' job (below), not a heavy image-wide wash. This is what "do not
          darken the entire hero excessively" asks for: the image should read clearly everywhere EXCEPT directly
          behind the panels, not be dimmed everywhere just so two small regions of it are legible. */}
      <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/5" />
      <div aria-hidden="true" className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/50 via-black/10 to-transparent" />

      {/* Nav overlay -- now its own lighter frosted-glass bar (Part 2): a subtle blur + a soft bottom border, not
          the heavier glass treatment the headline panel below uses -- distinguishes "persistent chrome" from
          "the hero's own content" while still guaranteeing the wordmark/labels read over the brightest part of
          the image (the neon ceiling lights sit right behind this bar). */}
      <div className="relative z-10 flex items-center justify-between border-b border-white/10 bg-black/20 px-4 py-4 backdrop-blur-md sm:px-8 sm:py-5">
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className="size-2 rounded-full bg-white" />
          <span className="text-base font-bold tracking-tight text-white">VentureGPS</span>
        </div>
        <nav aria-label="VentureGPS surfaces (concept)" className="hidden items-center gap-7 sm:flex">
          {NAV_ITEMS.map((item) => (
            <span key={item} className="text-sm font-medium tracking-wide text-white">
              {item}
            </span>
          ))}
        </nav>
      </div>

      {/* Content: headline block (left) + featured-market card. Row on large screens (card floats bottom-right
          via its own lg:absolute positioning below); a single stacked column below the headline on everything
          narrower than lg, since a phone has no spare "other corner" to place a second element into. */}
      <div className="relative z-10 flex min-h-[calc(100svh-84px)] flex-col justify-end gap-6 px-4 pb-10 sm:px-8 sm:pb-14 lg:min-h-[calc(100svh-100px)]">
        {/* Part 1: the headline glass panel. `bg-black/45` (translucent, not opaque) + `backdrop-blur-xl` is
            strong enough to guarantee contrast for white text over the image's brightest neon highlights, while
            the image itself still shows through, softened, behind it -- satisfies "ensure the image remains
            visible through the panel" directly rather than by accident. Padding narrows slightly on mobile
            (`p-5` vs `sm:p-8`) so the panel never approaches the 390px viewport's own edges. */}
        <div className="max-w-lg rounded-3xl border border-white/15 bg-black/45 p-5 shadow-2xl shadow-black/40 backdrop-blur-xl sm:p-8 lg:max-w-3xl">
          <div className="mb-4 inline-flex w-fit items-center gap-2 sm:mb-5">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
            <span className="text-xs font-medium tracking-wide text-white/85">Verified Startup Market Intelligence</span>
          </div>

          {/* Two lines, always: "Navigate the" / "Startup Economy" -- the wider lg:max-w-3xl panel above keeps
              "Startup Economy" from wrapping a third time at the lg:text-7xl size. Gradient on "Navigate"
              unchanged. */}
          <h1 className="text-4xl font-black leading-[1.02] tracking-tight text-white sm:text-6xl lg:text-7xl">
            <span className="bg-gradient-to-r from-accent via-primary to-secondary bg-clip-text text-transparent">Navigate</span> the
            <br />
            Startup Economy
          </h1>

          <p className="mt-4 max-w-md text-base leading-7 text-white/85 sm:mt-5 sm:text-lg">
            Discover the companies, markets and ideas shaping what&rsquo;s next.
          </p>
        </div>

        {/* Featured-market card: normal flow (below the headline) up to `lg`; absolutely positioned to the
            opposite (bottom-right) corner at `lg` and up, where the source photo's own composition (technicians
            and equipment, not the robots) tolerates a card without covering the image's actual subject. */}
        <div className="lg:absolute lg:bottom-10 lg:right-8 lg:mt-0">
          <FeaturedMarketCard />
        </div>
      </div>
    </section>
  );
}
