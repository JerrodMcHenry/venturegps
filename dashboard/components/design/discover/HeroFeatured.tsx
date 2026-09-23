import Link from "next/link";

import DirectionBadge from "@/components/markets/DirectionBadge.tsx";
import { DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";

import type { SampleMarketSignal } from "./sampleData";

// VentureGPS Increment 16, Section 4A -- the featured-story hero. A visitor arriving from a video link should
// land on something that reads like the video's own subject, not a generic homepage -- this simulates that:
// "here's the market the video was about, here's what VentureGPS can tell you, tap through." featured is
// deliberately just SampleMarketSignal (no separate "story" data model exists or is invented here) -- Increment
// 16 is design-only, so this is illustrating the SHAPE of the experience, not a new content type.
type HeroFeaturedProps = {
  featured: SampleMarketSignal;
};

export default function HeroFeatured({ featured }: HeroFeaturedProps) {
  const tone = DIRECTION_TONE[featured.direction];

  return (
    <header className="border-b border-border pb-10 pt-10 sm:pb-14 sm:pt-16">
      <div className="mx-auto max-w-3xl px-4 sm:px-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">VentureGPS</p>
        <h1 className="mt-2 text-4xl font-bold leading-[1.05] tracking-tight text-text-primary sm:text-6xl">
          Navigate the
          <br />
          Startup Economy
        </h1>
        <p className="mt-4 max-w-xl text-lg leading-8 text-text-secondary">
          Verified financing activity across startup markets, compared against each market&rsquo;s own history &mdash;
          never a forecast, never a recommendation.
        </p>

        <div className="mt-8 rounded-2xl border border-border bg-surface p-5 sm:p-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Today&rsquo;s featured market &middot; Sample</p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
            <h2 className="text-2xl font-bold text-text-primary">{featured.displayName}</h2>
            <DirectionBadge symbol={DIRECTION_SYMBOL[featured.direction]} label={DIRECTION_LABEL[featured.direction]} tone={tone} size="sm" />
          </div>
          <p className="mt-1.5 text-sm text-text-secondary">{featured.oneLiner}</p>

          <p className="mt-4 text-sm text-text-muted">
            This card is illustrative sample content. The real, live version of this experience is the market page
            built in Increment 15 &mdash;{" "}
            <Link href="/markets/robotics" className="font-semibold text-primary underline underline-offset-2">
              open a real market page
            </Link>{" "}
            (shows real data if that market exists in this environment, or VentureGPS&rsquo;s own honest
            &ldquo;not available&rdquo; state if it doesn&rsquo;t &mdash; both are real, working product states).
          </p>
        </div>
      </div>
    </header>
  );
}
