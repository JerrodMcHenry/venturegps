// VentureGPS Increment 17.1 -- the production homepage's market-selection/carousel index math. A deliberate,
// small, standalone copy of components/design/cinematicHomepage/sectionB/interactionLogic.ts's three functions
// (proven correct there: tests/v2SectionBInteraction.test.ts, tests/v2SectionBBrowserInteraction.test.ts, and
// the Increment 16.3.2 real-browser verification), not an import from that file -- production code should not
// depend on the `components/design/*` tree, which is understood throughout this project as a dev-only,
// NODE_ENV-gated prototype area that could be pruned independently of production. `selectFeaturedMarket` is
// generalized to a type parameter here (the prototype's version is tied to its own sample-data-shaped
// `SectionBMarket`) so this one file works for whatever real market-card shape the production components use,
// without a second near-duplicate per call site.

export function selectFeaturedMarket<T extends { slug: string }>(markets: T[], selectedSlug: string): { featured: T; others: T[] } {
  const featured = markets.find((m) => m.slug === selectedSlug) ?? markets[0];
  const others = markets.filter((m) => m.slug !== featured.slug);
  return { featured, others };
}

export function clampCarouselIndex(index: number, length: number): number {
  if (length <= 0) return 0;
  return Math.max(0, Math.min(index, length - 1));
}

export function indexFromScrollPosition(scrollLeft: number, slideWidth: number, length: number): number {
  if (slideWidth <= 0) return 0;
  return clampCarouselIndex(Math.round(scrollLeft / slideWidth), length);
}
