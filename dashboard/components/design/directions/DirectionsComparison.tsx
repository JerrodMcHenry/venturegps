import Link from "next/link";

import PrototypeRibbon from "@/components/design/shared/PrototypeRibbon";

// VentureGPS Increment 16.1 -- the comparison page. Deliberately plain/utilitarian (not a fourth visual
// direction of its own) -- its only job is letting Jerrod jump between the three concepts and read a short,
// honest strengths/tradeoffs summary next to each, not to make a fourth aesthetic case.
type ConceptSummary = {
  letter: string;
  name: string;
  href: string;
  concept: string;
  strengths: string[];
  tradeoffs: string[];
};

const CONCEPTS: ConceptSummary[] = [
  {
    letter: "A",
    name: "Cinematic Editorial",
    href: "/design/direction-a",
    concept: "VentureGPS as a technology publication: full-bleed compositions, oversized type, one market at a time in a vertical editorial scroll.",
    strengths: [
      "Strongest first-impression \"premium\" feel -- large type and full-bleed art read as a real publication, not a tool.",
      "Natural home for video/editorial content (Section 4's job) -- the format already reads like a magazine.",
      "Most straightforward to extend with real photography/video later without restructuring the layout.",
    ],
    tradeoffs: [
      "Longest page -- reaching the 6th market requires real scroll commitment; least \"seconds to understand everything\" of the three.",
      "Least distinctive market-discovery INTERACTION -- it's still fundamentally a scroll, just a beautiful one.",
      "Placeholder art needs real imagery to reach its full potential; today it's tasteful gradients, not yet cinematic.",
    ],
  },
  {
    letter: "B",
    name: "Interactive Intelligence",
    href: "/design/direction-b",
    concept: "A dark, technical instrument panel: markets as nodes in a spatial constellation you tap to bring into focus.",
    strengths: [
      "Most distinctive, most \"futuristic\" interaction of the three -- genuinely different navigational geometry, not a re-skinned list.",
      "Scales down to a single glance: the whole market set is visible and comparable at once.",
      "The HUD/terminal aesthetic differentiates VentureGPS sharply from both dashboards AND from typical consumer apps.",
    ],
    tradeoffs: [
      "Highest risk of feeling cold/technical rather than warm/inviting to a non-technical visitor from a TikTok link.",
      "The constellation's information density per node is intentionally low (name + one symbol) -- it teases, it doesn't explain, which may frustrate a visitor who wants the story immediately.",
      "Fixed-dark only (Section 2.2 of the Blueprint) -- doesn't participate in the app's light-mode support the way A and C do.",
    ],
  },
  {
    letter: "C",
    name: "Social Discovery",
    href: "/design/direction-c",
    concept: "A mobile-native, full-screen vertical story deck (scroll-snap) -- one market per \"slide,\" swipe up for the next.",
    strengths: [
      "Best fit for the actual distribution strategy (TikTok/Shorts/Reels audience already knows this exact interaction pattern).",
      "Every slide IS a complete first-screen experience -- no scrolling needed to \"get\" any single market.",
      "Native video-shaped slide for The Brief -- the format doesn't have to explain what a video slide is for.",
    ],
    tradeoffs: [
      "Hardest to make feel like \"intelligence\" rather than \"content\" -- the format inherently favors a single headline over comparative depth.",
      "Full-viewport-height slides mean desktop feels the most compromised of the three (a format built for a phone, adapted up).",
      "Depends most heavily on the exact chrome height above it (sticky header + prototype banner) for pixel-perfect snap alignment -- functional today, but the most fragile of the three to future chrome changes.",
    ],
  },
];

export default function DirectionsComparison() {
  return (
    <div>
      <PrototypeRibbon name="Comparing all three concepts" />

      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">VentureGPS Increment 16.1</p>
        <h1 className="mt-2 text-3xl font-bold text-text-primary sm:text-4xl">Three visual directions</h1>
        <p className="mt-3 max-w-xl text-base leading-7 text-text-secondary">
          Three substantially different, high-fidelity prototypes exploring VentureGPS&rsquo;s visual identity. No
          concept is selected here &mdash; this page exists only to make comparing them easy.
        </p>

        <div className="mt-10 space-y-8">
          {CONCEPTS.map((c) => (
            <div key={c.letter} className="rounded-2xl border border-border bg-surface p-6">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h2 className="text-xl font-bold text-text-primary">
                  Direction {c.letter}: {c.name}
                </h2>
                <Link href={c.href} className="text-sm font-semibold text-primary hover:text-primary-hover">
                  Open prototype →
                </Link>
              </div>
              <p className="mt-2 text-sm leading-6 text-text-secondary">{c.concept}</p>

              <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-success">Strengths</p>
                  <ul className="mt-1.5 space-y-1.5 text-sm leading-5 text-text-secondary">
                    {c.strengths.map((s) => (
                      <li key={s}>&bull; {s}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-warning">Tradeoffs</p>
                  <ul className="mt-1.5 space-y-1.5 text-sm leading-5 text-text-secondary">
                    {c.tradeoffs.map((t) => (
                      <li key={t}>&bull; {t}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-10 rounded-2xl border border-dashed border-border bg-surface-subtle p-6">
          <h2 className="text-base font-semibold text-text-primary">Shared elements across all three</h2>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            Regardless of which direction (or blend) is approved, these held up in every concept and are strong
            candidates for the final VentureGPS identity: the exact <code className="rounded bg-surface-muted px-1">DirectionBadge</code>{" "}
            symbol/tone/label vocabulary (never re-skinned per direction), verified-financing-first storytelling
            (no concept leads with a forecast or a recommendation), visible data-coverage honesty (every concept
            renders the <code className="rounded bg-surface-muted px-1">insufficient_data</code>/{" "}
            <code className="rounded bg-surface-muted px-1">mixed</code> states without hiding or softening them), and
            zero new runtime dependencies (every visual effect is CSS/SVG, reusing the existing token system).
            Full detail in <code className="rounded bg-surface-muted px-1">docs/product/VENTUREGPS_CONSUMER_EXPERIENCE_BLUEPRINT_V1.md</code>.
          </p>
        </div>
      </div>
    </div>
  );
}
