// Relative, explicit-extension import (not the `@/` alias) specifically so this stays resolvable by Node's
// native TS execution when required transitively from tests/v2SectionBInteraction.test.ts -- the same
// discipline lib/api/v2/*.ts already follows, for the same reason.
import { SAMPLE_MARKET_SIGNALS, type SampleMarketSignal } from "../../discover/sampleData.ts";

// VentureGPS Increment 16.3 -- Section B's four markets. Deliberately does NOT modify or duplicate
// sampleData.ts (Increment 16, reused unchanged by Direction A/B/C and Discover too -- Section 8's "preserve...
// the earlier design experiments" boundary) -- this file only maps FOUR of its existing entries to their own
// hero image and an optional display-name override, and reads every numeric field (direction, financing
// activity, companies funded, verified capital, sparkline) straight from the shared, unmodified sample data.
// Nothing here invents a statistic; `displayNameOverride` only relabels "Climate Hardware" as "Climate
// Technology" (Jerrod's requested wording for this section) without touching the underlying data or the label
// any other prototype shows for that same slug.
export type SectionBMarket = {
  market: SampleMarketSignal;
  displayName: string;
  image: string;
  imageObjectPosition: string;
  featured?: boolean;
};

function findMarket(slug: string): SampleMarketSignal {
  const found = SAMPLE_MARKET_SIGNALS.find((m) => m.slug === slug);
  if (!found) throw new Error(`sectionBMarkets: no sample market for slug "${slug}" -- check sampleData.ts`);
  return found;
}

export const SECTION_B_MARKETS: SectionBMarket[] = [
  {
    market: findMarket("robotics"),
    displayName: "Robotics",
    image: "/design-references/cinematic-homepage.png",
    imageObjectPosition: "28% 30%",
    featured: true,
  },
  {
    market: findMarket("quantum-computing"),
    displayName: "Quantum Computing",
    image: "/design-references/market-quantum-computing.png",
    imageObjectPosition: "35% 30%",
  },
  {
    market: findMarket("climate-hardware"),
    displayName: "Climate Technology",
    image: "/design-references/market-climate-technology.png",
    imageObjectPosition: "50% 35%",
  },
  {
    market: findMarket("biotech"),
    displayName: "Biotech",
    image: "/design-references/market-biotech.png",
    imageObjectPosition: "40% 25%",
  },
];
