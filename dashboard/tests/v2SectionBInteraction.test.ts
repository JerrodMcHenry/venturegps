// VentureGPS Increment 16.3 (interaction bug fix) -- automated tests for Section B's two interactions' actual
// computation: desktop featured-market selection and mobile carousel index math.
//
// What this DOES prove: given the real SECTION_B_MARKETS data, selecting any market computes the correct
// featured/others split, the previously-featured market always returns to the tile list, and the carousel's
// index math clamps and rounds correctly at every boundary a real visitor could reach (start, end, a single-item
// list, overshoot in either direction).
//
// What this does NOT prove, and is not a substitute for: that a click or tap on the real page actually reaches
// these functions in a real browser. That question is covered instead by
// tests/v2SectionBBrowserInteraction.test.ts, which renders the real components into a real DOM and dispatches
// real click events at them -- see that file's own header comment, MarketShowcaseDesktop.tsx /
// MarketCarouselMobile.tsx's comments, and docs/product/VENTUREGPS_CONSUMER_EXPERIENCE_BLUEPRINT_V1.md's
// Increment 16.3.2 section for the full investigation and root cause.
//
// Run with:
//   node tests/v2SectionBInteraction.test.ts

import { selectFeaturedMarket, clampCarouselIndex, indexFromScrollPosition } from "../components/design/cinematicHomepage/sectionB/interactionLogic.ts";
import { SECTION_B_MARKETS } from "../components/design/cinematicHomepage/sectionB/sectionBMarkets.ts";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

const ALL_SLUGS = SECTION_B_MARKETS.map((m) => m.market.slug);

function test_robotics_is_featured_initially_and_the_other_three_are_the_tiles(): void {
  const { featured, others } = selectFeaturedMarket(SECTION_B_MARKETS, "robotics");
  expect(featured.market.slug === "robotics", `expected robotics featured, got ${featured.market.slug}`);
  expect(others.length === 3, `expected exactly 3 complementary tiles, got ${others.length}`);
  expect(!others.some((m) => m.market.slug === "robotics"), "the featured market must never also appear in the tile list");
}

function test_selecting_any_market_makes_it_featured() {
  for (const slug of ALL_SLUGS) {
    const { featured } = selectFeaturedMarket(SECTION_B_MARKETS, slug);
    expect(featured.market.slug === slug, `selecting ${slug} should feature it, got ${featured.market.slug} instead`);
  }
}

function test_the_previously_featured_market_returns_to_the_tile_list() {
  const { others: othersAfterQuantumFeatured } = selectFeaturedMarket(SECTION_B_MARKETS, "quantum-computing");
  expect(
    othersAfterQuantumFeatured.some((m) => m.market.slug === "robotics"),
    "robotics (the original featured market) must reappear in the tile list once a different market is selected"
  );
}

function test_others_never_contains_the_featured_slug_for_any_selection() {
  for (const slug of ALL_SLUGS) {
    const { featured, others } = selectFeaturedMarket(SECTION_B_MARKETS, slug);
    expect(!others.some((m) => m.market.slug === featured.market.slug), `others must exclude ${featured.market.slug} when it is featured`);
    expect(others.length === SECTION_B_MARKETS.length - 1, `expected exactly ${SECTION_B_MARKETS.length - 1} complementary tiles for ${slug}`);
  }
}

function test_an_unknown_slug_falls_back_to_the_first_market_rather_than_throwing() {
  const { featured } = selectFeaturedMarket(SECTION_B_MARKETS, "not-a-real-market");
  expect(featured.market.slug === SECTION_B_MARKETS[0].market.slug, "an unrecognized slug should fall back to the first market, not throw or return nothing");
}

function test_clamp_carousel_index_stays_within_bounds_at_both_ends() {
  expect(clampCarouselIndex(-1, 4) === 0, "an index below 0 must clamp to 0 (the 'previous' button disabled at the start)");
  expect(clampCarouselIndex(4, 4) === 3, "an index at length must clamp to length-1 (the 'next' button disabled at the end)");
  expect(clampCarouselIndex(100, 4) === 3, "a wildly out-of-range index must still clamp to the last valid index");
}

function test_clamp_carousel_index_normal_navigation() {
  expect(clampCarouselIndex(0, 4) === 0, "index 0 stays 0");
  expect(clampCarouselIndex(1, 4) === 1, "index 1 stays 1 -- next from the first slide");
  expect(clampCarouselIndex(2, 4) === 2, "index 2 stays 2");
}

function test_clamp_carousel_index_single_item_list() {
  expect(clampCarouselIndex(0, 1) === 0, "a single-slide carousel's only valid index is 0");
  expect(clampCarouselIndex(5, 1) === 0, "any index into a single-slide carousel clamps to 0");
}

function test_clamp_carousel_index_empty_list_never_throws() {
  expect(clampCarouselIndex(0, 0) === 0, "an empty carousel returns a safe 0 rather than throwing or returning -1");
}

function test_index_from_scroll_position_rounds_to_nearest_slide() {
  expect(indexFromScrollPosition(0, 300, 4) === 0, "scrollLeft 0 is slide 0");
  expect(indexFromScrollPosition(300, 300, 4) === 1, "scrollLeft exactly one slide-width in is slide 1");
  expect(indexFromScrollPosition(140, 300, 4) === 0, "less than half a slide-width in still rounds down to slide 0");
  expect(indexFromScrollPosition(160, 300, 4) === 1, "more than half a slide-width in rounds up to slide 1");
}

function test_index_from_scroll_position_clamps_overshoot() {
  expect(indexFromScrollPosition(10_000, 300, 4) === 3, "scrolling past the last slide still clamps to the last valid index");
  expect(indexFromScrollPosition(-50, 300, 4) === 0, "a negative scroll position (elastic overscroll) clamps to 0");
}

function test_index_from_scroll_position_zero_width_is_safe() {
  expect(indexFromScrollPosition(500, 0, 4) === 0, "a zero-width track (not yet laid out) returns a safe 0 rather than dividing by zero");
}

function main(): void {
  const tests = [
    test_robotics_is_featured_initially_and_the_other_three_are_the_tiles,
    test_selecting_any_market_makes_it_featured,
    test_the_previously_featured_market_returns_to_the_tile_list,
    test_others_never_contains_the_featured_slug_for_any_selection,
    test_an_unknown_slug_falls_back_to_the_first_market_rather_than_throwing,
    test_clamp_carousel_index_stays_within_bounds_at_both_ends,
    test_clamp_carousel_index_normal_navigation,
    test_clamp_carousel_index_single_item_list,
    test_clamp_carousel_index_empty_list_never_throws,
    test_index_from_scroll_position_rounds_to_nearest_slide,
    test_index_from_scroll_position_clamps_overshoot,
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
