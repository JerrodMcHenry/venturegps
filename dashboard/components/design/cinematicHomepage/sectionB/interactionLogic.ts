import type { SectionBMarket } from "./sectionBMarkets";

// VentureGPS Increment 16.3 (interaction bug fix) -- the actual COMPUTATION behind both Section B interactions,
// pulled out of the two client components as pure, dependency-free functions specifically so it can be unit
// tested (see tests/v2SectionBInteraction.test.ts) without a browser or a DOM. This is deliberately NOT a
// substitute for real end-to-end browser verification of the click/tap itself reaching these functions -- see
// the investigation notes in MarketShowcaseDesktop.tsx and MarketCarouselMobile.tsx for what that verification
// found and why it still needs Jerrod's own manual confirmation. What this DOES guarantee: if a click/tap does
// reach the handler, the resulting state is correct -- the "presence of an onClick handler" was never the
// question; whether it computes the right answer is.

// Desktop: which market is "featured" and which three are "complementary" -- given the full market list and
// whichever slug is currently selected. The featured market is never present in `others`, and `others`
// preserves SECTION_B_MARKETS' own original order (never re-sorted based on click history), so the tile
// positions don't visually shuffle unpredictably as a visitor clicks around.
export function selectFeaturedMarket(
  markets: SectionBMarket[],
  selectedSlug: string
): { featured: SectionBMarket; others: SectionBMarket[] } {
  const featured = markets.find((m) => m.market.slug === selectedSlug) ?? markets[0];
  const others = markets.filter((m) => m.market.slug !== featured.market.slug);
  return { featured, others };
}

// Mobile: the next/previous arrow buttons' index math. Clamped, never wraps -- Part "MOBILE ACCEPTANCE
// CRITERIA": "Arrow disabled states reflect the current position," which only makes sense for an index that
// genuinely stops at the ends rather than cycling back around.
export function clampCarouselIndex(index: number, length: number): number {
  if (length <= 0) return 0;
  return Math.max(0, Math.min(index, length - 1));
}

// Mobile: which slide is "active" for the dots, computed from the track's own scroll position -- used both when
// a visitor manually swipes (Part: "swiping and manual scrolling update the active dot") and, indirectly, after
// a dot/arrow click completes its scroll. `slideWidth` is the scroll container's own `clientWidth` (each slide
// is one full container-width apart in the layout), so this is a straightforward round-to-nearest, clamped into
// range for the same reason as clampCarouselIndex.
export function indexFromScrollPosition(scrollLeft: number, slideWidth: number, length: number): number {
  if (slideWidth <= 0) return 0;
  return clampCarouselIndex(Math.round(scrollLeft / slideWidth), length);
}
