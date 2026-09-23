// VentureGPS Increment 16 -- Consumer Experience Blueprint prototype. SAMPLE DATA ONLY.
//
// Every value in this file is illustrative, hand-written content for a design review -- none of it is fetched,
// none of it is real financing activity, and none of it should ever be mistaken for a live number. Every card
// that renders from this file carries a visible "Sample" label (see PrototypeBanner.tsx and each card's own
// "SAMPLE" chip) precisely so a reviewer (or, if this ever leaked further, a visitor) can never confuse it with
// the real /markets/[slug] page's real data.
//
// It IS grounded in the REAL system's vocabulary on purpose: `CapitalDirection`, `ComponentMetric`, and the
// money/signal-label formatting helpers are all imported from the actual production modules (types/v2/capital.ts,
// lib/api/v2/{money,signalLabels}.ts) -- this demonstrates how the real Capital Intelligence contract would slot
// into this design without inventing a second, parallel vocabulary that could drift from the real one.
import type { CapitalDirection } from "@/types/v2/capital";

export type SampleMarketSignal = {
  slug: string;
  displayName: string;
  oneLiner: string;
  direction: CapitalDirection;
  financingActivity: number;
  companiesFunded: number;
  verifiedCapitalLabel: string; // pre-formatted, e.g. "$185.0M" -- illustrative, never a real amount
  verifiedCapitalCurrency: string;
  sparkline: number[]; // 9 illustrative relative values (0-1), NOT real historical windows
};

// Six sample markets -- enough to demonstrate a browsable "Explore Markets" rail without pretending to be an
// exhaustive real catalog. Directions deliberately cover a spread of the real vocabulary (including
// insufficient_data and mixed) so the design has to work for every real state, not just the flattering ones.
export const SAMPLE_MARKET_SIGNALS: SampleMarketSignal[] = [
  {
    slug: "robotics",
    displayName: "Robotics",
    oneLiner: "Industrial and field robotics ventures",
    direction: "strong_increase",
    financingActivity: 4,
    companiesFunded: 2,
    verifiedCapitalLabel: "$185.0M",
    verifiedCapitalCurrency: "USD",
    sparkline: [0.2, 0.25, 0.18, 0.22, 0.55, 0.6, 0.58, 0.62, 1],
  },
  {
    slug: "climate-hardware",
    displayName: "Climate Hardware",
    oneLiner: "Physical infrastructure for decarbonization",
    direction: "increase",
    financingActivity: 6,
    companiesFunded: 5,
    verifiedCapitalLabel: "$62.4M",
    verifiedCapitalCurrency: "USD",
    sparkline: [0.3, 0.35, 0.4, 0.38, 0.45, 0.5, 0.48, 0.6, 0.72],
  },
  {
    slug: "developer-tools",
    displayName: "Developer Tools",
    oneLiner: "Infrastructure and tooling for software teams",
    direction: "stable",
    financingActivity: 9,
    companiesFunded: 7,
    verifiedCapitalLabel: "€41.2M",
    verifiedCapitalCurrency: "EUR",
    sparkline: [0.5, 0.52, 0.48, 0.51, 0.49, 0.53, 0.5, 0.51, 0.5],
  },
  {
    slug: "biotech",
    displayName: "Biotech",
    oneLiner: "Therapeutics, diagnostics, and life-sciences platforms",
    direction: "insufficient_data",
    financingActivity: 0,
    companiesFunded: 0,
    verifiedCapitalLabel: "—",
    verifiedCapitalCurrency: "",
    sparkline: [0, 0, 0, 0, 0, 0, 0, 0, 0],
  },
  {
    slug: "consumer-marketplaces",
    displayName: "Consumer Marketplaces",
    oneLiner: "Peer-to-peer and demand-aggregation platforms",
    direction: "decrease",
    financingActivity: 2,
    companiesFunded: 2,
    verifiedCapitalLabel: "$8.1M",
    verifiedCapitalCurrency: "USD",
    sparkline: [0.7, 0.65, 0.6, 0.55, 0.5, 0.4, 0.35, 0.3, 0.22],
  },
  {
    slug: "quantum-computing",
    displayName: "Quantum Computing",
    oneLiner: "Hardware and software for quantum-scale computation",
    direction: "mixed",
    financingActivity: 3,
    companiesFunded: 3,
    verifiedCapitalLabel: "$140.0M",
    verifiedCapitalCurrency: "USD",
    sparkline: [0.3, 0.8, 0.25, 0.7, 0.3, 0.75, 0.28, 0.65, 0.4],
  },
];

export type SampleStory = {
  title: string;
  format: "Video" | "Short" | "Breakdown";
  marketSlug: string | null; // the market this story would deep-link to, if any
  status: "planned"; // every story in this prototype is a future placeholder -- there is no video content yet
};

// The Brief -- explicitly a FUTURE surface. Jerrod has not published VentureGPS video content yet, so every
// entry here is a clearly-labeled placeholder illustrating the intended shape (title, format, and which market
// it would connect to), never a real, clickable piece of content.
export const SAMPLE_STORIES: SampleStory[] = [
  { title: "Why robotics funding just had its biggest month in a year", format: "Video", marketSlug: "robotics", status: "planned" },
  { title: "60 seconds on climate hardware's funding curve", format: "Short", marketSlug: "climate-hardware", status: "planned" },
  { title: "Reading a Capital Signal: what \"insufficient data\" really means", format: "Breakdown", marketSlug: null, status: "planned" },
];
