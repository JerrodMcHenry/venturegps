"use client";

// VentureGPS Increment 16, Sections 4B+4D combined -- "What's Moving" and "Capital Flow" merged into one
// section deliberately (see the Blueprint doc's "challenging the hierarchy" note): both are fundamentally the
// same question ("which markets have something happening, and what does the capital picture look like"), and a
// first-time mobile visitor reading two back-to-back sections making the same kind of claim reads as padding,
// not two distinct product ideas. This is also the section's real interactive moment: tapping a card selects it
// and updates the detail panel below -- a genuine client-side interaction, not a fake/disabled control.
import { useState } from "react";

import MarketSignalCard from "./MarketSignalCard";
import { DIRECTION_EXPLANATION, DIRECTION_LABEL } from "@/lib/api/v2/signalLabels.ts";

import type { SampleMarketSignal } from "./sampleData";

type SignalsRailProps = {
  markets: SampleMarketSignal[];
};

export default function SignalsRail({ markets }: SignalsRailProps) {
  const [selectedSlug, setSelectedSlug] = useState(markets[0]?.slug ?? null);
  const selected = markets.find((m) => m.slug === selectedSlug) ?? markets[0] ?? null;

  return (
    <section aria-labelledby="signals-heading" className="border-b border-border py-10 sm:py-14">
      <div className="mx-auto max-w-3xl px-4 sm:px-6">
        <h2 id="signals-heading" className="text-2xl font-bold text-text-primary sm:text-3xl">
          What&rsquo;s moving
        </h2>
        <p className="mt-2 max-w-xl text-base leading-7 text-text-secondary">
          Verified financing activity and capital deployed, compared against each market&rsquo;s own recent history.
          Tap a market for a closer look.
        </p>
      </div>

      {/* Horizontal scroll rail -- the mobile-native "browse a set of cards" pattern, touch-friendly, no
          pagination controls needed. -mx-4/px-4 lets cards bleed to the screen edge on mobile while the rest of
          the section stays within the max-w-3xl reading column. */}
      <div className="mt-5 flex gap-3 overflow-x-auto px-4 pb-2 sm:px-6" style={{ scrollSnapType: "x proximity" }}>
        {markets.map((market) => (
          <div key={market.slug} style={{ scrollSnapAlign: "start" }}>
            <MarketSignalCard market={market} selected={market.slug === selectedSlug} onSelect={() => setSelectedSlug(market.slug)} />
          </div>
        ))}
      </div>

      {selected ? (
        <div className="mx-auto mt-6 max-w-3xl px-4 sm:px-6">
          <div className="rounded-2xl border border-border bg-surface-subtle p-5">
            <p className="text-sm font-semibold text-text-primary">
              {selected.displayName}: {DIRECTION_LABEL[selected.direction]}
            </p>
            <p className="mt-1.5 text-sm leading-6 text-text-secondary">{DIRECTION_EXPLANATION[selected.direction]}</p>
            <p className="mt-3 text-xs text-text-muted">
              Sample data for this prototype. On the real market page, this reads directly from the live Capital
              Signal API.
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
