// VentureGPS Increment 17.2 -- the approved production imagery, cleared for commercial use (see
// public/design-references/README.md's "cleared for production" section for the full rights basis; do not
// change this mapping without reading that first). Keyed by real V2 market slug, not by array position -- the
// homepage's markets are real, bounded V2 data (homepageData.ts), never a fixed four-item sample set, so a
// market whose slug isn't in this map (a real market the approved image set doesn't cover yet) must fall back
// to cardPlaceholder.ts's rights-clear gradient rather than borrowing another market's photo or guessing.
export type MarketImage = {
  src: string;
  objectPosition: string;
};

const MARKET_IMAGES: Record<string, MarketImage> = {
  robotics: { src: "/design-references/cinematic-homepage.png", objectPosition: "28% 30%" },
  "quantum-computing": { src: "/design-references/market-quantum-computing.png", objectPosition: "35% 30%" },
  "climate-hardware": { src: "/design-references/market-climate-technology.png", objectPosition: "50% 35%" },
  biotech: { src: "/design-references/market-biotech.png", objectPosition: "40% 25%" },
};

export function marketImageFor(slug: string): MarketImage | null {
  return MARKET_IMAGES[slug] ?? null;
}
