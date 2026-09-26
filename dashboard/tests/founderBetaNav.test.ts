// Phase 15 -- Founder Beta Surface Audit tests.
//
// Same hand-rolled expect()/PASS-FAIL/main() convention as
// tests/playbooks.test.ts and tests/journey.test.ts (this repo has no
// jest/vitest). TopNav.tsx and PersonalMenu.tsx are "use client"
// components that import next/link, next/navigation, and @clerk/nextjs --
// none of which plain node can resolve outside Next's own build -- so
// this file reads them as source text (the same cross-boundary technique
// the other two test files' own firewall tests already use) rather than
// importing them.
//
// Run with:
//   node tests/founderBetaNav.test.ts
// or:
//   npm run test:founderBetaNav
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DASHBOARD_ROOT = path.resolve(__dirname, "..");

function readSource(relativePath: string): string {
  return readFileSync(path.join(DASHBOARD_ROOT, relativePath), "utf-8");
}

// --- Primary navigation: superseded by Portfolio Release Task 4 --------------
//
// TopNav.tsx and MobileTabBar.tsx (this section's original subjects) are
// deleted -- Task 4, Phase 2 consolidated them into components/layout/
// PublicNav.tsx, the one shared nav for both the homepage and the
// authenticated app. The primary switcher itself also changed, on that
// same task's own explicit instruction: Build/Analyze/My Startups/Learn
// (the array these tests originally asserted) is no longer the primary
// row -- it's Analyze/My Analyses/Saved now, with Build/My Startups/Learn
// demoted back to PersonalMenu's account menu (see
// test_demoted_destinations_are_reachable_from_account_menu below, and
// tests/unifiedNav.test.ts for the full current-architecture coverage).
// This is a deliberate reversal of Phase 32's own promotion, not a
// regression -- kept here as a comment, not a still-passing assertion,
// so the history stays legible without asserting behavior this
// codebase no longer has.
//
// What's still true and still checked below: Fundraising/Simulate must
// never be global primary destinations (unchanged, verified against
// PublicNav.tsx now), every de-emphasized route still exists on disk,
// ExplorePreview/EntryPaths are untouched.

function test_fundraising_and_simulate_never_become_primary_destinations(): void {
  const source = readSource("components/layout/PublicNav.tsx");
  const arrayStart = source.indexOf("export const PRIMARY_NAVIGATION");
  expect(arrayStart !== -1, "PRIMARY_NAVIGATION export not found -- has PublicNav.tsx been restructured?");

  const arrayEnd = source.indexOf("];", arrayStart);
  const arrayText = source.slice(arrayStart, arrayEnd);

  expect(!/label:\s*"Fundraising"/.test(arrayText), "\"Fundraising\" must never be a global primary destination -- it stays a founder tool inside the venture workspace");
  expect(!/label:\s*"Simulate"/.test(arrayText), "\"Simulate\" must never be a global primary destination -- it stays a founder tool inside the venture workspace");
}

// --- Account menu (PersonalMenu.tsx) ---

// Phase 15's Watchlist/Investor intelligence removal is unchanged by
// Task 4 -- that was a separate, still-valid judgment call ("the
// investor surface is not populated enough to expose") this task never
// asked to revisit.
function test_watchlist_and_investor_still_removed_from_account_menu(): void {
  const source = readSource("components/layout/PersonalMenu.tsx");
  expect(
    !/label="Watchlist"/.test(source),
    "Phase 15: \"Watchlist\" must not appear in the account menu -- it watches the same cold-start-affected discovery population as Explore"
  );
  expect(
    !/label="Investor intelligence"/.test(source),
    "Phase 15: \"Investor intelligence\" must not appear in the account menu -- this is a Founder Beta, and the investor surface is not populated enough to expose"
  );
  expect(/label="Send feedback"/.test(source), "\"Send feedback\" must remain -- it has no other home in the shell");
}

// Portfolio Release Task 4, Phase 2: "My Ideas"/"My Startup"/"Learn" are
// BACK in the account menu -- the deliberate reverse of Phase 32's own
// promotion (see PersonalMenu.tsx's own comment for the full history).
// The primary nav row is now Analyze/My Analyses/Saved
// (tests/unifiedNav.test.ts), so these three need a home again.
function test_demoted_destinations_are_reachable_from_account_menu(): void {
  const source = readSource("components/layout/PersonalMenu.tsx");
  expect(/label="My Ideas"/.test(source), "\"My Ideas\" must be reachable from the account menu now that it isn't primary nav");
  expect(/href="\/idea-lab"/.test(source), "\"My Ideas\" must still route to the existing /idea-lab experience");
  expect(/label="My Startup"/.test(source), "\"My Startup\" must be reachable from the account menu now that it isn't primary nav");
  expect(/href="\/founder"/.test(source), "\"My Startup\" must still route to the existing /founder Founder Workspace chooser");
  expect(/label="Learn"/.test(source), "\"Learn\" must be reachable from the account menu now that it isn't primary nav");
  expect(/href="\/playbooks"/.test(source), "\"Learn\" must still route into the existing /playbooks experience, not a new one");
}

// --- Hide, don't delete: every de-emphasized route's page file must still exist ---

function test_deemphasized_routes_remain_present_on_disk(): void {
  const preservedRoutes = [
    "app/rankings/page.tsx",
    "app/search/page.tsx",
    "app/compare/page.tsx",
    "app/saved/page.tsx",
    "app/investor/page.tsx",
    "app/startup/[id]/page.tsx",
  ];

  for (const route of preservedRoutes) {
    expect(
      existsSync(path.join(DASHBOARD_ROOT, route)),
      `Phase 15 Part 16/17: ${route} must still exist -- de-emphasizing navigation must never delete a route`
    );
  }
}

function test_explore_preview_component_untouched_not_deleted(): void {
  expect(
    existsSync(path.join(DASHBOARD_ROOT, "components/home/ExplorePreview.tsx")),
    "components/home/ExplorePreview.tsx must still exist -- removed from the homepage's render, not deleted from the codebase"
  );
}

// --- Homepage: ExplorePreview no longer rendered, EntryPaths has no dangling Explore card ---

function test_homepage_no_longer_renders_explore_preview(): void {
  // Checks the actual import/JSX usage, not prose -- this file's own
  // comments legitimately reference "ExplorePreview" by name to explain
  // why it was removed and where it still lives.
  const source = readSource("app/page.tsx");
  expect(
    !/from\s+"@\/components\/home\/ExplorePreview"/.test(source),
    "app/page.tsx must not import ExplorePreview (Phase 15 Part 14/19)"
  );
  expect(!/<ExplorePreview\s*\/>/.test(source), "app/page.tsx must not render <ExplorePreview />");
}

// Phase 32, Part 6: EntryPaths' own three cards were rebuilt around user
// intent per the directive's exact recommended structure -- "Build an
// idea"/"Analyze my startup"/"Review my pitch deck" (the Phase 15-era
// titles this test originally asserted) are gone from the card grid
// itself; pitch deck review is deliberately subordinated to a small link
// below the three cards instead of a co-equal fourth card. The
// Founder-Beta-era assertion this test keeps -- no "Explore startups"
// card -- is still correct and unchanged.
function test_entry_paths_no_longer_offers_explore_startups_card(): void {
  const source = readSource("components/home/EntryPaths.tsx");
  expect(
    !/title:\s*"Explore startups"/.test(source),
    "EntryPaths must not offer an \"Explore startups\" entry path on the Founder Beta homepage"
  );
  // The three intent-based paths Phase 32 replaced them with must be there.
  for (const title of ["Explore an Idea", "Work on My Startup", "Analyze a Company"]) {
    expect(source.includes(title), `EntryPaths must still offer "${title}"`);
  }
  // Pitch deck review must remain reachable, just not as a fourth
  // co-equal card (Part 6's own explicit instruction).
  expect(source.includes("/analyze/deck"), "Pitch deck review must remain reachable from the homepage, even if subordinate to the three primary cards");
}

const TESTS: [string, () => void][] = [
  ["test_fundraising_and_simulate_never_become_primary_destinations", test_fundraising_and_simulate_never_become_primary_destinations],
  ["test_watchlist_and_investor_still_removed_from_account_menu", test_watchlist_and_investor_still_removed_from_account_menu],
  ["test_demoted_destinations_are_reachable_from_account_menu", test_demoted_destinations_are_reachable_from_account_menu],
  ["test_deemphasized_routes_remain_present_on_disk", test_deemphasized_routes_remain_present_on_disk],
  ["test_explore_preview_component_untouched_not_deleted", test_explore_preview_component_untouched_not_deleted],
  ["test_homepage_no_longer_renders_explore_preview", test_homepage_no_longer_renders_explore_preview],
  ["test_entry_paths_no_longer_offers_explore_startups_card", test_entry_paths_no_longer_offers_explore_startups_card],
];

function main(): void {
  console.log("\nFounder Beta Surface Audit tests");
  console.log("-".repeat(72));

  const failures: string[] = [];

  for (const [name, test] of TESTS) {
    try {
      test();
      console.log(`PASS  ${name}`);
    } catch (error) {
      console.log(`FAIL  ${name}\n      ${(error as Error).message}`);
      failures.push(name);
    }
  }

  console.log("-".repeat(72));
  console.log(`${TESTS.length - failures.length}/${TESTS.length} passed`);

  if (failures.length > 0) {
    process.exit(1);
  }
}

main();
