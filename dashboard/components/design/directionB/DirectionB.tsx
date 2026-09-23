// VentureGPS Increment 16.1 -- Direction B: Interactive Intelligence.
//
// Concept: VentureGPS as a futuristic instrument panel for reading the startup economy -- dark, technical,
// monospaced accents, a spatial constellation instead of a card grid or a vertical scroll. The market-discovery
// interaction (MarketConstellation.tsx) is genuinely spatial, not a re-skinned list.
import Link from "next/link";

import PrototypeRibbon from "@/components/design/shared/PrototypeRibbon";
import IllustrativeTag from "@/components/design/shared/IllustrativeTag";
import MarketConstellation from "./MarketConstellation";

import { DIRECTION_LABEL, DIRECTION_SYMBOL } from "@/lib/api/v2/signalLabels.ts";
import { SAMPLE_MARKET_SIGNALS, SAMPLE_STORIES } from "@/components/design/discover/sampleData";

export default function DirectionB() {
  // `dark` forces the app's existing dark-mode CSS custom properties (globals.css's `.dark` block) on every
  // descendant regardless of the visitor's system/app theme preference -- this direction's whole concept is a
  // fixed-dark instrument panel, not a page that should flip light in light mode. This also means the shared
  // components reused below (DirectionBadge, MarketConstellation's own `text-text-primary`/`bg-surface`/
  // `var(--border)` usage) automatically resolve to the correct dark values via ordinary CSS custom-property
  // inheritance -- no per-class color overrides needed.
  return (
    <div className="dark bg-[#05070d] text-[#eef4ff]">
      <PrototypeRibbon letter="B" name="Interactive Intelligence" />

      {/* 1. FIRST SCREEN -- dark instrument-panel hero. Monospace label, tight grid line texture (CSS only). */}
      <header className="relative overflow-hidden border-b border-white/10 px-4 pb-14 pt-16 sm:px-6 sm:pb-20 sm:pt-20">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[0.15]"
          style={{
            backgroundImage: "linear-gradient(to right, #4f8cff 1px, transparent 1px), linear-gradient(to bottom, #4f8cff 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
        <div className="relative mx-auto max-w-3xl">
          <p className="font-mono text-xs uppercase tracking-[0.3em] text-[#4f8cff]">VentureGPS // Signal Interface</p>
          <h1 className="mt-4 text-5xl font-bold leading-[1.02] tracking-tight sm:text-7xl">Navigate the Startup Economy</h1>
          <p className="mt-5 max-w-lg text-lg leading-8 text-[#a8b6ca]">
            Every market as a live node. Tap to focus. Verified financing activity, read the way an instrument
            reads a signal &mdash; exact, comparative, never a forecast.
          </p>
        </div>
      </header>

      {/* 2. MARKET DISCOVERY -- the constellation, this direction's signature interaction. */}
      <section aria-labelledby="constellation-heading" className="border-b border-white/10 px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-3xl text-center">
          <h2 id="constellation-heading" className="text-2xl font-bold sm:text-3xl">
            Market constellation
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#a8b6ca]">Tap any node to bring that market into focus.</p>
        </div>
        <div className="mt-10">
          <MarketConstellation markets={SAMPLE_MARKET_SIGNALS} />
        </div>
      </section>

      {/* 3. FEATURED MARKET is the constellation's own center node by construction -- no separate section needed;
          duplicating a "featured" block here would just repeat what the interaction already foregrounds. */}

      {/* 4. VIDEO / EDITORIAL -- a "transmission log" HUD panel rather than a card list. */}
      <section aria-labelledby="log-heading" className="border-b border-white/10 px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-2xl">
          <div className="flex items-center gap-2">
            <h2 id="log-heading" className="font-mono text-sm uppercase tracking-[0.25em] text-[#4f8cff]">
              Transmission log
            </h2>
            <IllustrativeTag variant="inverted">Planned</IllustrativeTag>
          </div>
          <div className="mt-6 rounded-2xl border border-white/15 bg-black/30 p-1">
            {SAMPLE_STORIES.map((story, index) => (
              <div key={story.title} className="flex items-start gap-4 border-b border-white/10 px-4 py-4 font-mono text-sm last:border-b-0">
                <span className="text-[#4f8cff]">{String(index + 1).padStart(2, "0")}</span>
                <span className="text-[#8492a8]">[{story.format.toUpperCase()}]</span>
                <span className="text-[#eef4ff]">{story.title}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 5. SHARING CONCEPT -- a compact "signal card," data-forward, terminal-styled. */}
      <section aria-labelledby="share-heading" className="px-4 py-16 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-2xl">
          <h2 id="share-heading" className="text-xl font-bold">
            Shareable signal card
          </h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-[#a8b6ca]">
            Static mock of the intended shared-card format &mdash; not a functional share control.
          </p>
          <div aria-hidden="true" className="mt-6 max-w-sm rounded-2xl border border-[#4f8cff]/40 bg-black/40 p-5 font-mono">
            <div className="flex items-center justify-between text-xs uppercase tracking-widest text-[#4f8cff]">
              <span>VentureGPS</span>
              <span>Signal</span>
            </div>
            <p className="mt-4 text-2xl font-bold text-[#eef4ff]">{SAMPLE_MARKET_SIGNALS[0].displayName}</p>
            <p className="mt-1 text-sm text-[#4f8cff]">
              {DIRECTION_SYMBOL[SAMPLE_MARKET_SIGNALS[0].direction]} {DIRECTION_LABEL[SAMPLE_MARKET_SIGNALS[0].direction]}
            </p>
            <p className="mt-4 text-xs text-[#8492a8]">venturegps.com/markets/{SAMPLE_MARKET_SIGNALS[0].slug}</p>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/10 py-10 text-center">
        <Link href="/design/directions" className="text-sm font-semibold text-[#4f8cff] hover:text-[#70a2ff]">
          ← Back to all three concepts
        </Link>
      </footer>
    </div>
  );
}
