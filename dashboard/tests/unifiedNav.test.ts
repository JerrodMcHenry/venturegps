// Milestone 1, Task 1 -- Unify Navigation tests.
//
// Same hand-rolled expect()/PASS-FAIL/main() convention, and the same "read as source text" technique
// tests/founderBetaNav.test.ts already established for these exact files: TopNav.tsx, PublicNav.tsx,
// PersonalMenu.tsx and AppShell.tsx are all "use client" components importing next/link, next/navigation and
// @clerk/nextjs, none of which plain node can resolve outside Next's own build.
//
// Run with:
//   node tests/unifiedNav.test.ts
// or:
//   npm run test:unifiedNav
import { readFileSync } from "node:fs";
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

// --- PublicNav: Search/Analyze reachable, without implying they're the same data as Markets ---

function test_public_nav_links_to_markets_search_and_analyze(): void {
  const source = readSource("components/layout/PublicNav.tsx");
  const arrayStart = source.indexOf("const NAV_LINKS");
  const arrayEnd = source.indexOf("];", arrayStart);
  const arrayText = source.slice(arrayStart, arrayEnd);

  expect(/label:\s*"Markets",\s*href:\s*"\/markets"/.test(arrayText), "PublicNav must still link \"Markets\" to /markets");
  expect(/label:\s*"Search",\s*href:\s*"\/search"/.test(arrayText), "PublicNav must link \"Search\" to the existing /search route");
  expect(/label:\s*"Analyze",\s*href:\s*"\/analyze"/.test(arrayText), "PublicNav must link \"Analyze\" to the existing /analyze route");
}

function test_public_nav_does_not_relabel_search_or_analyze_as_markets_data(): void {
  // The task's own explicit requirement: never imply legacy SIE search/assessments and V2 verified Markets
  // records are the same kind of data. This is a narrow, literal check on the one place that risk could sneak
  // in -- the link labels themselves -- not a claim about the full page content of either route.
  const source = readSource("components/layout/PublicNav.tsx");
  expect(!/label:\s*"Markets Search"/.test(source), "Search must not be relabeled to imply it is part of Markets");
  expect(!/label:\s*"Verified Analyze"/.test(source), "Analyze must not be relabeled to imply it is V2-verified data");
}

// --- PublicNav: sign-in / account access ---

function test_public_nav_has_signed_out_and_signed_in_states(): void {
  const source = readSource("components/layout/PublicNav.tsx");
  expect(/import\s*\{\s*Show\s*\}\s*from\s*"@clerk\/nextjs"/.test(source), "PublicNav must use Clerk's own <Show> (reuse, not a hand-rolled auth check)");
  expect(/<Show when="signed-out">/.test(source), "PublicNav must render a signed-out sign-in affordance");
  expect(/href="\/sign-in"/.test(source), "PublicNav's signed-out affordance must link to the existing /sign-in route");
  expect(/<Show when="signed-in">/.test(source), "PublicNav must render a signed-in account affordance");
  expect(/import PersonalMenu from "\.\/PersonalMenu"/.test(source), "PublicNav must reuse the existing PersonalMenu component, not a second implementation");
  expect((source.match(/<PersonalMenu\s*\/>/g) ?? []).length >= 2, "PersonalMenu must be rendered for both the desktop and mobile layouts");
}

// --- AppShell: /admin gets the unified VentureGPS chrome, without touching its own auth ---

function test_admin_routes_get_the_unified_public_nav_chrome(): void {
  const source = readSource("components/layout/AppShell.tsx");
  const arrayStart = source.indexOf("const REAL_PUBLIC_NAV_ROUTE_PREFIXES");
  const arrayEnd = source.indexOf(";", arrayStart);
  const arrayText = source.slice(arrayStart, arrayEnd);

  expect(/"\/markets"/.test(arrayText), "/markets must remain on the unified PublicNav chrome");
  expect(/"\/admin"/.test(arrayText), "/admin must be added to the unified PublicNav chrome (was falling through to the old TopNav shell)");
}

function test_homepage_bare_chrome_is_unchanged_no_homepage_redesign(): void {
  const source = readSource("components/layout/AppShell.tsx");
  const arrayStart = source.indexOf("const BARE_ROUTE_PREFIXES");
  const arrayEnd = source.indexOf(";", arrayStart);
  const arrayText = source.slice(arrayStart, arrayEnd);

  expect(/"\/design\/cinematic-homepage"/.test(arrayText), "the cinematic homepage prototype's bare chrome must be unchanged");
  expect(/"\/"/.test(arrayText), "\"/\" must remain on bare chrome -- the homepage renders its own nav, unchanged, per this task's own \"no homepage redesign\" boundary");
}

function test_admin_pages_still_call_the_real_auth_boundary(): void {
  // The nav link added in PersonalMenu.tsx must never be treated as the security boundary -- this regression-
  // proofs that the actual page-level Clerk check is still present and untouched.
  for (const page of ["app/admin/v2-review/page.tsx", "app/admin/analytics/page.tsx"]) {
    const source = readSource(page);
    expect(/await auth\.protect\(\)/.test(source), `${page} must still call auth.protect() -- adding a nav link must never weaken this`);
  }
}

// --- TopNav: unified VentureGPS branding, no second "Startup Intelligence" / "SI" identity ---

function test_top_nav_uses_ventures_gps_branding_not_a_second_product_identity(): void {
  const source = readSource("components/layout/TopNav.tsx");
  // Checks the actual rendered JSX text node, not prose -- this file's own comments (including the one
  // documenting this exact change) legitimately reference the old "Startup Intelligence" wordmark by name to
  // explain what changed and why, the same way founderBetaNav.test.ts's own comments reference "Watchlist".
  expect(!/>\s*Startup Intelligence\s*</.test(source), "TopNav must not render a separate \"Startup Intelligence\" wordmark -- exactly the two-products confusion this task removes");
  expect(!/>\s*SI\s*</.test(source), "TopNav must not render the old standalone \"SI\" logo mark");
  expect(/>VentureGPS</.test(source), "TopNav must render the unified VentureGPS wordmark");
  expect(/aria-label="VentureGPS home"/.test(source), "TopNav's home link must be labeled consistently with the rest of the app");
}

function test_top_nav_primary_navigation_is_unchanged(): void {
  // This task must not touch the existing Build/Analyze/My Startups/Learn destinations themselves -- only the
  // brand mark around them. tests/founderBetaNav.test.ts already covers this array's exact contents in detail;
  // this is a narrow confirmation the array itself still exists at the same export.
  const source = readSource("components/layout/TopNav.tsx");
  expect(/export const PRIMARY_NAVIGATION/.test(source), "PRIMARY_NAVIGATION must still be exported unchanged");
}

// --- PersonalMenu: no admin link without a trusted, server-verified admin signal ---

function test_personal_menu_does_not_expose_an_unguarded_admin_link(): void {
  // Correction to this task: "Evidence review" was briefly shown to every signed-in user, which advertised an
  // admin-only tool as if it belonged to any signed-in user. No trusted, server-verified admin capability is
  // exposed to the frontend to gate it on (ADMIN_USER_IDS is backend-only, app/auth.py), and inferring admin
  // status client-side (email, Clerk metadata, etc.) would duplicate the backend's authorization rule in a
  // second, unsynchronized place. So the link is removed rather than gated on a guess.
  const source = readSource("components/layout/PersonalMenu.tsx");
  expect(!/label="Evidence review"/.test(source), "PersonalMenu must not show an Evidence review link without a trusted admin signal to gate it on");
  expect(!/href="\/admin\/v2-review"/.test(source), "PersonalMenu must not link to /admin/v2-review while it cannot verify the viewer is an admin");
  expect(/label="Send feedback"/.test(source), "existing \"Send feedback\" must remain, unremoved");
}

const TESTS: [string, () => void][] = [
  ["test_public_nav_links_to_markets_search_and_analyze", test_public_nav_links_to_markets_search_and_analyze],
  ["test_public_nav_does_not_relabel_search_or_analyze_as_markets_data", test_public_nav_does_not_relabel_search_or_analyze_as_markets_data],
  ["test_public_nav_has_signed_out_and_signed_in_states", test_public_nav_has_signed_out_and_signed_in_states],
  ["test_admin_routes_get_the_unified_public_nav_chrome", test_admin_routes_get_the_unified_public_nav_chrome],
  ["test_homepage_bare_chrome_is_unchanged_no_homepage_redesign", test_homepage_bare_chrome_is_unchanged_no_homepage_redesign],
  ["test_admin_pages_still_call_the_real_auth_boundary", test_admin_pages_still_call_the_real_auth_boundary],
  ["test_top_nav_uses_ventures_gps_branding_not_a_second_product_identity", test_top_nav_uses_ventures_gps_branding_not_a_second_product_identity],
  ["test_top_nav_primary_navigation_is_unchanged", test_top_nav_primary_navigation_is_unchanged],
  ["test_personal_menu_does_not_expose_an_unguarded_admin_link", test_personal_menu_does_not_expose_an_unguarded_admin_link],
];

function main(): void {
  console.log("\nUnify Navigation tests");
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
