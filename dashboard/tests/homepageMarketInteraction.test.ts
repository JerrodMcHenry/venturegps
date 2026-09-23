// VentureGPS Increment 17.1 -- unit tests for the production homepage's market-selection/carousel index math
// (components/home/ventureGps/interactionLogic.ts), the same shape of test as
// tests/v2SectionBInteraction.test.ts covers for the /design prototype's own (separate, untouched) copy.
//
// Run with:
//   node tests/homepageMarketInteraction.test.ts

import { clampCarouselIndex, indexFromScrollPosition, selectFeaturedMarket } from "../components/home/ventureGps/interactionLogic.ts";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

type Card = { slug: string; displayName: string };

const MARKETS: Card[] = [
  { slug: "robotics", displayName: "Robotics" },
  { slug: "quantum-computing", displayName: "Quantum Computing" },
  { slug: "biotech", displayName: "Biotech" },
];

function test_first_market_is_featured_by_default_and_the_rest_are_the_tiles(): void {
  const { featured, others } = selectFeaturedMarket(MARKETS, "robotics");
  expect(featured.slug === "robotics", `expected robotics featured, got ${featured.slug}`);
  expect(others.length === 2, `expected exactly 2 complementary tiles, got ${others.length}`);
  expect(!others.some((m) => m.slug === "robotics"), "the featured market must never also appear in the tile list");
}

function test_selecting_any_market_makes_it_featured(): void {
  for (const card of MARKETS) {
    const { featured } = selectFeaturedMarket(MARKETS, card.slug);
    expect(featured.slug === card.slug, `selecting ${card.slug} should feature it, got ${featured.slug} instead`);
  }
}

function test_the_previously_featured_market_returns_to_the_tile_list(): void {
  const { others } = selectFeaturedMarket(MARKETS, "quantum-computing");
  expect(others.some((m) => m.slug === "robotics"), "robotics (the original featured market) must reappear in the tile list once a different market is selected");
}

function test_an_unknown_slug_falls_back_to_the_first_market_rather_than_throwing(): void {
  const { featured } = selectFeaturedMarket(MARKETS, "not-a-real-market");
  expect(featured.slug === MARKETS[0].slug, "an unrecognized slug should fall back to the first market, not throw or return nothing");
}

function test_selectFeaturedMarket_works_for_a_bounded_list_smaller_than_four(): void {
  // The homepage's real market count is whatever the V2 API actually has, bounded to at most
  // HOMEPAGE_MARKET_LIMIT (4) -- never assumed to be exactly 4 the way the /design prototype's fixed sample set
  // was. This must work correctly for fewer real markets too.
  const two: Card[] = [MARKETS[0], MARKETS[1]];
  const { featured, others } = selectFeaturedMarket(two, "quantum-computing");
  expect(featured.slug === "quantum-computing", "featuring works with only 2 real markets");
  expect(others.length === 1, `expected exactly 1 complementary tile with 2 markets, got ${others.length}`);
}

function test_clamp_carousel_index_stays_within_bounds_at_both_ends(): void {
  expect(clampCarouselIndex(-1, 3) === 0, "an index below 0 must clamp to 0");
  expect(clampCarouselIndex(3, 3) === 2, "an index at length must clamp to length-1");
  expect(clampCarouselIndex(100, 3) === 2, "a wildly out-of-range index must still clamp to the last valid index");
}

function test_clamp_carousel_index_empty_list_never_throws(): void {
  expect(clampCarouselIndex(0, 0) === 0, "an empty (no real markets yet) carousel returns a safe 0 rather than throwing or returning -1");
}

function test_index_from_scroll_position_rounds_to_nearest_slide(): void {
  expect(indexFromScrollPosition(0, 300, 3) === 0, "scrollLeft 0 is slide 0");
  expect(indexFromScrollPosition(300, 300, 3) === 1, "scrollLeft exactly one slide-width in is slide 1");
  expect(indexFromScrollPosition(140, 300, 3) === 0, "less than half a slide-width in still rounds down to slide 0");
}

function test_index_from_scroll_position_zero_width_is_safe(): void {
  expect(indexFromScrollPosition(500, 0, 3) === 0, "a zero-width track (not yet laid out) returns a safe 0 rather than dividing by zero");
}

function main(): void {
  const tests = [
    test_first_market_is_featured_by_default_and_the_rest_are_the_tiles,
    test_selecting_any_market_makes_it_featured,
    test_the_previously_featured_market_returns_to_the_tile_list,
    test_an_unknown_slug_falls_back_to_the_first_market_rather_than_throwing,
    test_selectFeaturedMarket_works_for_a_bounded_list_smaller_than_four,
    test_clamp_carousel_index_stays_within_bounds_at_both_ends,
    test_clamp_carousel_index_empty_list_never_throws,
    test_index_from_scroll_position_rounds_to_nearest_slide,
    test_index_from_scroll_position_zero_width_is_safe,
  ];

  let failures = 0;
  for (const test of tests) {
    try {
      test();
      console.log(`PASS ${test.name}`);
    } catch (error) {
      failures += 1;
      console.error(`FAIL ${test.name}: ${(error as Error).message}`);
    }
  }

  if (failures > 0) {
    console.error(`${failures} test(s) failed`);
    process.exit(1);
  }

  console.log(`All ${tests.length} tests passed`);
}

main();
