// VentureGPS Increment 17.1 -- RIGHTS-CLEAR PLACEHOLDER visuals for a market card, standing in for the approved
// design's real per-market photography (see VentureGpsHero.tsx's header comment for the same blocker). Pure
// brand-token CSS gradients, no image files, so nothing here carries any licensing question. Deliberately NOT
// the approved production design -- replace with real, rights-cleared per-market imagery once available, and
// remove this file's use at that point rather than keeping it as a permanent fallback.
const CARD_GRADIENTS = [
  "bg-gradient-to-br from-primary/70 via-black to-accent/30",
  "bg-gradient-to-br from-secondary/70 via-black to-primary/30",
  "bg-gradient-to-br from-accent/70 via-black to-secondary/30",
  "bg-gradient-to-br from-primary/50 via-black to-secondary/50",
];

export function cardPlaceholderClass(index: number): string {
  return CARD_GRADIENTS[index % CARD_GRADIENTS.length];
}
