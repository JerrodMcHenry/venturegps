// Portfolio Release Task 4 -- Unified UX, Analysis Retrieval and
// Authentication, Phase 2 (Unify Navigation) + Phase 4 (Homepage
// Coherence). Supersedes this file's original "Milestone 1, Task 1"
// coverage -- TopNav.tsx and MobileTabBar.tsx (that task's own subjects)
// are deleted; PublicNav.tsx is now the ONE nav for both the homepage
// and the authenticated application. What that earlier task established
// (VentureGPS branding, no second "SI" identity, /admin on the unified
// chrome, PersonalMenu's admin-link guard) is re-asserted below against
// its new home; what changed under it (the primary destination list
// itself, the account menu's contents) is asserted fresh.
//
// Same hand-rolled expect()/PASS-FAIL/main() convention, and the same
// "read as source text" technique this file's own predecessor
// established for these exact files: PublicNav.tsx, PersonalMenu.tsx,
// AppShell.tsx, and VentureGpsHero.tsx are all "use client" (or import
// "use client" components) using next/link, next/navigation and
// @clerk/nextjs, none of which plain node can resolve outside Next's own
// build.
//
// Run with:
//   node tests/unifiedNav.test.ts
// or:
//   npm run test:unifiedNav
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

// --- One reusable nav system: TopNav/MobileTabBar are gone -------------------

function test_top_nav_and_mobile_tab_bar_are_deleted(): void {
  expect(
    !existsSync(path.join(DASHBOARD_ROOT, "components/layout/TopNav.tsx")),
    "TopNav.tsx must be deleted -- PublicNav.tsx is now the one nav for the whole app, not a second parallel system"
  );
  expect(
    !existsSync(path.join(DASHBOARD_ROOT, "components/layout/MobileTabBar.tsx")),
    "MobileTabBar.tsx must be deleted -- PublicNav's own responsive disclosure panel is the one mobile implementation now"
  );
}

function test_app_shell_no_longer_imports_the_deleted_components(): void {
  const source = readSource("components/layout/AppShell.tsx");
  expect(!/from\s+"\.\/TopNav"/.test(source), "AppShell must not import the deleted TopNav.tsx");
  expect(!/from\s+"\.\/MobileTabBar"/.test(source), "AppShell must not import the deleted MobileTabBar.tsx");
  expect(/from\s+"\.\/PublicNav"/.test(source), "AppShell must render PublicNav for the default (non-bare, non-dev-prototype) branch");
}

// --- PublicNav: signed-out row is branding + How It Works + Sign in + Get Started ---

function test_signed_out_navigation_matches_the_spec(): void {
  const source = readSource("components/layout/PublicNav.tsx");
  const arrayStart = source.indexOf("const SIGNED_OUT_NAVIGATION");
  const arrayEnd = source.indexOf("];", arrayStart);
  const arrayText = source.slice(arrayStart, arrayEnd);

  // Portfolio Release Task 7, Phase 3: repointed from the homepage's own
  // inline anchor to the full /how-it-works page -- a primary nav
  // destination should lead somewhere real from any page, not just
  // scroll an anchor that only exists on "/". See PublicNav.tsx's own
  // comment.
  expect(/label:\s*"How It Works"/.test(arrayText), "Signed-out nav must link to \"How It Works\"");
  expect(/href:\s*"\/how-it-works"/.test(arrayText), "\"How It Works\" must link to the full /how-it-works page");
}

function test_signed_out_row_has_sign_in_and_get_started(): void {
  const source = readSource("components/layout/PublicNav.tsx");
  expect(/<Show when="signed-out">/.test(source), "PublicNav must render signed-out affordances via Clerk's own <Show>");
  expect(/href="\/sign-in"/.test(source), "Signed-out visitors must see a Sign in link");
  expect(/Sign in/.test(source), "The sign-in affordance must be labeled \"Sign in\"");
  expect((source.match(/Get Started/g) ?? []).length >= 2, "\"Get Started\" must appear for both the desktop and mobile signed-out layouts");
  expect(
    (source.match(/href="\/analyze"/g) ?? []).length >= 2,
    "\"Get Started\" must link to /analyze (auth-gated by that route's own auth.protect()) in both layouts"
  );
}

// --- PublicNav: signed-in row is Analyze / My Analyses / Saved + account controls ---

function test_signed_in_navigation_matches_the_spec(): void {
  const source = readSource("components/layout/PublicNav.tsx");
  const arrayStart = source.indexOf("export const PRIMARY_NAVIGATION");
  expect(arrayStart !== -1, "PRIMARY_NAVIGATION export not found -- has PublicNav.tsx been restructured?");
  const arrayEnd = source.indexOf("];", arrayStart);
  const arrayText = source.slice(arrayStart, arrayEnd);

  expect(/label:\s*"Analyze",\s*href:\s*"\/analyze"/.test(arrayText), "Signed-in nav must include \"Analyze\" -> /analyze");
  expect(/label:\s*"My Analyses",\s*href:\s*"\/my-analyses"/.test(arrayText), "Signed-in nav must include \"My Analyses\" -> /my-analyses");
  expect(/label:\s*"Saved",\s*href:\s*"\/saved"/.test(arrayText), "Signed-in nav must include \"Saved\" -> /saved");

  // The old primary destinations must NOT compete in this row anymore --
  // demoted to PersonalMenu (see test_demoted_destinations_are_reachable_from_account_menu
  // in tests/founderBetaNav.test.ts), not deleted.
  expect(!/label:\s*"Build"/.test(arrayText), "\"Build\" must no longer be a primary signed-in destination -- demoted to the account menu");
  expect(!/label:\s*"My Startups"/.test(arrayText), "\"My Startups\" must no longer be a primary signed-in destination -- demoted to the account menu");
  expect(!/label:\s*"Learn"/.test(arrayText), "\"Learn\" must no longer be a primary signed-in destination -- demoted to the account menu");
}

function test_signed_in_row_reuses_personal_menu_for_both_layouts(): void {
  const source = readSource("components/layout/PublicNav.tsx");
  expect(/import PersonalMenu from "\.\/PersonalMenu"/.test(source), "PublicNav must reuse the existing PersonalMenu component, not a second implementation");
  expect((source.match(/<PersonalMenu\s*\/>/g) ?? []).length >= 2, "PersonalMenu must be rendered for both the desktop and mobile layouts");
  expect(/<Show when="signed-in">/.test(source), "PublicNav must render the signed-in account affordance via Clerk's own <Show>");
}

// --- Single source of truth for desktop AND mobile (no duplicated nav logic) ---

function test_desktop_and_mobile_share_one_link_renderer(): void {
  // The actual regression this guards: a NavLinks(...)-style shared renderer
  // consuming PRIMARY_NAVIGATION/SIGNED_OUT_NAVIGATION, not two hand-authored
  // per-breakpoint link lists that could silently drift apart.
  const source = readSource("components/layout/PublicNav.tsx");
  const rendererMatches = source.match(/function NavLinks/g) ?? [];
  expect(rendererMatches.length === 1, "Exactly one shared link-rendering function must exist -- desktop and mobile must not each hand-roll their own");

  const usageMatches = source.match(/<NavLinks\b/g) ?? [];
  expect(usageMatches.length >= 4, "The shared NavLinks renderer must be reused for both signed-out/signed-in and desktop/mobile, not duplicated");
}

// --- AppShell: /admin and /markets get the unified chrome; homepage keeps its own ---

function test_admin_and_markets_fall_through_to_the_unified_chrome(): void {
  // There is no more separate REAL_PUBLIC_NAV_ROUTE_PREFIXES allowlist --
  // /admin and /markets simply aren't BARE or dev-prototype routes, so they
  // reach the same default branch (PublicNav header variant) as the rest
  // of the authenticated app.
  const source = readSource("components/layout/AppShell.tsx");
  // A comment may legitimately reference the old array's name by history
  // (same convention this codebase already uses for retired identifiers
  // elsewhere) -- what must actually be gone is the DECLARATION itself.
  expect(
    !/const\s+REAL_PUBLIC_NAV_ROUTE_PREFIXES\s*=/.test(source),
    "The old REAL_PUBLIC_NAV_ROUTE_PREFIXES allowlist must no longer be declared -- there is only one non-bare, non-dev-prototype branch now"
  );
}

function test_homepage_bare_chrome_is_unchanged(): void {
  const source = readSource("components/layout/AppShell.tsx");
  const arrayStart = source.indexOf("const BARE_ROUTE_PREFIXES");
  const arrayEnd = source.indexOf(";", arrayStart);
  const arrayText = source.slice(arrayStart, arrayEnd);

  expect(/"\/design\/cinematic-homepage"/.test(arrayText), "the cinematic homepage prototype's bare chrome must be unchanged");
  expect(/"\/"/.test(arrayText), "\"/\" must remain on bare chrome -- the homepage's own hero renders PublicNav itself (variant=\"overlay\")");
}

function test_admin_pages_still_call_the_real_auth_boundary(): void {
  for (const page of ["app/admin/v2-review/page.tsx", "app/admin/analytics/page.tsx"]) {
    const source = readSource(page);
    expect(/await auth\.protect\(\)/.test(source), `${page} must still call auth.protect() -- nav consolidation must never weaken this`);
  }
}

// --- Branding: unified VentureGPS identity, no second "Startup Intelligence" ---

function test_public_nav_uses_venturegps_branding_not_a_second_product_identity(): void {
  const source = readSource("components/layout/PublicNav.tsx");
  expect(!/>\s*Startup Intelligence\s*</.test(source), "PublicNav must not render a separate \"Startup Intelligence\" wordmark");
  expect(!/>\s*SI\s*</.test(source), "PublicNav must not render the old standalone \"SI\" logo mark");
  expect(/>VentureGPS</.test(source), "PublicNav must render the unified VentureGPS wordmark");
}

function test_personal_menu_does_not_expose_an_unguarded_admin_link(): void {
  const source = readSource("components/layout/PersonalMenu.tsx");
  expect(!/label="Evidence review"/.test(source), "PersonalMenu must not show an Evidence review link without a trusted admin signal to gate it on");
  expect(!/href="\/admin\/v2-review"/.test(source), "PersonalMenu must not link to /admin/v2-review while it cannot verify the viewer is an admin");
}

// --- Phase 3: My Analyses is wired into the nav and protected -----------------

function test_my_analyses_route_is_protected(): void {
  const source = readSource("proxy.ts");
  const arrayStart = source.indexOf("createRouteMatcher([");
  const arrayEnd = source.indexOf("]);", arrayStart);
  const arrayText = source.slice(arrayStart, arrayEnd);
  expect(arrayText.includes('"/my-analyses(.*)"'), "proxy.ts's route matcher must include /my-analyses(.*)");
}

function test_my_analyses_page_calls_the_real_auth_boundary(): void {
  const source = readSource("app/my-analyses/page.tsx");
  expect(/await auth\.protect\(\)/.test(source), "app/my-analyses/page.tsx must call auth.protect()");
}

// --- Phase 4: homepage headline/CTA aligned with evidence-backed analysis ----

function test_hero_headline_is_evidence_backed_analysis_not_markets_first(): void {
  const source = readSource("components/home/ventureGps/VentureGpsHero.tsx");
  expect(/Evidence-backed/.test(source), "The hero headline must reference evidence-backed analysis, not the earlier Markets-first framing");
  expect(!/Navigate<\/span> the/.test(source), "The old \"Navigate the Startup Economy\" headline text must be replaced");
}

function test_hero_has_a_primary_cta_into_analyze(): void {
  const source = readSource("components/home/ventureGps/VentureGpsHero.tsx");
  expect(/href="\/analyze"/.test(source), "The hero must have a primary CTA linking to /analyze");
}

function test_how_it_works_section_exists_and_is_wired_into_the_homepage(): void {
  expect(
    existsSync(path.join(DASHBOARD_ROOT, "components/home/ventureGps/HowItWorksSection.tsx")),
    "components/home/ventureGps/HowItWorksSection.tsx must exist"
  );

  const sectionSource = readSource("components/home/ventureGps/HowItWorksSection.tsx");
  expect(/id="how-it-works"/.test(sectionSource), "The How It Works section must expose the id PublicNav's anchor links to");

  const pageSource = readSource("app/page.tsx");
  expect(/from\s+"@\/components\/home\/ventureGps\/HowItWorksSection/.test(pageSource), "app/page.tsx must import HowItWorksSection");
  expect(/<HowItWorksSection\s*\/>/.test(pageSource), "app/page.tsx must render <HowItWorksSection />");
}

function test_homepage_does_not_expand_markets_explore_v2_or_founder_investor_features(): void {
  // Task 4 Phase 4's own boundary was "don't grow Markets/Explore/V2" --
  // Task 5 (Unified Visual Design and Homepage Simplification) went
  // further and explicitly REMOVED MarketDiscoverySection/the featured-
  // market widget from the homepage entirely (its own instruction: "Remove
  // homepage featured-market widgets... Discover/Explore the Markets
  // sections and all redundant Explore the Market buttons. Do not delete
  // underlying market routes, backend functionality or data."). This test
  // now asserts THAT boundary: the component is gone from "/" but the
  // file, the /markets route, and homepageData.ts are untouched on disk.
  const pageSource = readSource("app/page.tsx");
  // Checks actual import/JSX usage, not prose -- this file's own comments
  // legitimately reference "MarketDiscoverySection" by name to explain
  // what changed and why (same convention this codebase already uses
  // elsewhere for retired identifiers).
  expect(!/from\s+"@\/components\/home\/ventureGps\/MarketDiscoverySection/.test(pageSource), "app/page.tsx must no longer import MarketDiscoverySection (Task 5: homepage simplification)");
  expect(!/<MarketDiscoverySection\b/.test(pageSource), "app/page.tsx must no longer render <MarketDiscoverySection />");
  expect(!/from\s+"@\/components\/home\/ventureGps\/homepageData/.test(pageSource), "app/page.tsx must no longer import loadHomepageMarkets -- nothing on the simplified homepage needs it");
  expect(!/loadHomepageMarkets\(\)/.test(pageSource), "app/page.tsx must no longer call loadHomepageMarkets()");

  expect(existsSync(path.join(DASHBOARD_ROOT, "components/home/ventureGps/MarketDiscoverySection.tsx")), "MarketDiscoverySection.tsx must still exist on disk -- removed from the homepage's render, not deleted");
  expect(existsSync(path.join(DASHBOARD_ROOT, "components/home/ventureGps/homepageData.ts")), "homepageData.ts must still exist on disk -- the underlying market data fetch is untouched, just no longer called from the homepage");
  expect(existsSync(path.join(DASHBOARD_ROOT, "app/markets/page.tsx")), "The real /markets route must still exist and be unaffected");
}

function test_hero_no_longer_renders_a_featured_market_widget(): void {
  const source = readSource("components/home/ventureGps/VentureGpsHero.tsx");
  // Checks actual function/prop/JSX declarations, not prose -- this
  // file's own comment legitimately references "FeaturedMarketCard" by
  // name to explain what was removed and why.
  expect(!/function FeaturedMarketCard/.test(source), "VentureGpsHero must no longer define a FeaturedMarketCard component");
  expect(!/<FeaturedMarketCard\b/.test(source), "VentureGpsHero must no longer render <FeaturedMarketCard />");
  expect(!/Explore the market/.test(source), "VentureGpsHero must not contain a redundant \"Explore the Market\" button");
  expect(!/VentureGpsHeroProps/.test(source), "VentureGpsHero must no longer take any props at all (the `featured` market prop is gone)");
}

const TESTS: [string, () => void][] = [
  ["test_top_nav_and_mobile_tab_bar_are_deleted", test_top_nav_and_mobile_tab_bar_are_deleted],
  ["test_app_shell_no_longer_imports_the_deleted_components", test_app_shell_no_longer_imports_the_deleted_components],
  ["test_signed_out_navigation_matches_the_spec", test_signed_out_navigation_matches_the_spec],
  ["test_signed_out_row_has_sign_in_and_get_started", test_signed_out_row_has_sign_in_and_get_started],
  ["test_signed_in_navigation_matches_the_spec", test_signed_in_navigation_matches_the_spec],
  ["test_signed_in_row_reuses_personal_menu_for_both_layouts", test_signed_in_row_reuses_personal_menu_for_both_layouts],
  ["test_desktop_and_mobile_share_one_link_renderer", test_desktop_and_mobile_share_one_link_renderer],
  ["test_admin_and_markets_fall_through_to_the_unified_chrome", test_admin_and_markets_fall_through_to_the_unified_chrome],
  ["test_homepage_bare_chrome_is_unchanged", test_homepage_bare_chrome_is_unchanged],
  ["test_admin_pages_still_call_the_real_auth_boundary", test_admin_pages_still_call_the_real_auth_boundary],
  ["test_public_nav_uses_venturegps_branding_not_a_second_product_identity", test_public_nav_uses_venturegps_branding_not_a_second_product_identity],
  ["test_personal_menu_does_not_expose_an_unguarded_admin_link", test_personal_menu_does_not_expose_an_unguarded_admin_link],
  ["test_my_analyses_route_is_protected", test_my_analyses_route_is_protected],
  ["test_my_analyses_page_calls_the_real_auth_boundary", test_my_analyses_page_calls_the_real_auth_boundary],
  ["test_hero_headline_is_evidence_backed_analysis_not_markets_first", test_hero_headline_is_evidence_backed_analysis_not_markets_first],
  ["test_hero_has_a_primary_cta_into_analyze", test_hero_has_a_primary_cta_into_analyze],
  ["test_how_it_works_section_exists_and_is_wired_into_the_homepage", test_how_it_works_section_exists_and_is_wired_into_the_homepage],
  ["test_homepage_does_not_expand_markets_explore_v2_or_founder_investor_features", test_homepage_does_not_expand_markets_explore_v2_or_founder_investor_features],
  ["test_hero_no_longer_renders_a_featured_market_widget", test_hero_no_longer_renders_a_featured_market_widget],
];

function main(): void {
  console.log("\nUnified Navigation + Homepage Coherence tests");
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
