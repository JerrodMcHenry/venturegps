// Portfolio Release Task 3B -- Secure Analysis Visibility, frontend
// regression tests. Backend authorization coverage lives in
// app/tests/test_analysis_visibility.py (the authoritative source of
// truth for the actual rule); this file only proves the FRONTEND side of
// the fix: the pages that used to be public now call auth.protect(), the
// API client functions that used to be tokenless now require a token,
// and the "private by default" disclosure exists where a submitting user
// would see it. Same "read the file as source text" technique every
// other test in this directory uses for files that import
// next/navigation/@clerk/nextjs (which plain Node can't resolve outside
// Next's own build) -- see tests/unifiedNav.test.ts's own docstring for
// the full rationale.
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

// --- Pages that were public now call the real auth boundary ----------------

function test_startup_profile_page_calls_auth_protect(): void {
  const source = readSource("app/startup/[id]/page.tsx");
  expect(/await auth\.protect\(\)/.test(source), "app/startup/[id]/page.tsx must call auth.protect()");
  expect(
    /import\s*\{\s*auth\s*\}\s*from\s*"@clerk\/nextjs\/server"/.test(source),
    "app/startup/[id]/page.tsx must import Clerk's real server-side auth()",
  );
}

function test_startup_profile_page_forwards_a_real_token() {
  const source = readSource("app/startup/[id]/page.tsx");
  expect(
    /const\s*\{\s*getToken\s*\}\s*=\s*await\s*auth\(\)/.test(source),
    "app/startup/[id]/page.tsx must obtain a real token via Clerk's server-side getToken()",
  );
  expect(
    /getStartupProfile\(id,\s*token\)/.test(source),
    "getStartupProfile must be called with the real token, not tokenless",
  );
  expect(
    /getSPSHistory\(id,\s*token\)/.test(source),
    "getSPSHistory must be called with the real token, not tokenless",
  );
}

function test_rankings_page_calls_auth_protect(): void {
  const source = readSource("app/rankings/page.tsx");
  expect(/await auth\.protect\(\)/.test(source), "app/rankings/page.tsx must call auth.protect()");
}

function test_search_page_calls_auth_protect(): void {
  const source = readSource("app/search/page.tsx");
  expect(/await auth\.protect\(\)/.test(source), "app/search/page.tsx must call auth.protect()");
}

function test_compare_page_calls_auth_protect(): void {
  const source = readSource("app/compare/page.tsx");
  expect(/await auth\.protect\(\)/.test(source), "app/compare/page.tsx must call auth.protect()");
}

// --- API client functions now require a token -------------------------------

function test_rankings_api_client_requires_token(): void {
  const source = readSource("lib/api/rankings.ts");
  expect(
    /getRankings\(token:\s*string\s*\|\s*null\)/.test(source),
    "getRankings() must take a required token parameter",
  );
}

function test_discovery_api_client_requires_token(): void {
  const source = readSource("lib/api/discovery.ts");
  expect(/token:\s*string\s*\|\s*null/.test(source), "discoverStartups()/getDiscoveryFilterOptions() must take a required token parameter");
}

function test_compare_api_client_requires_token(): void {
  const source = readSource("lib/api/compare.ts");
  expect(/token:\s*string\s*\|\s*null/.test(source), "compareStartups() must take a required token parameter");
}

function test_startups_api_client_requires_token(): void {
  const source = readSource("lib/api/startups.ts");
  expect(
    (source.match(/token:\s*string\s*\|\s*null/g) ?? []).length >= 2,
    "getStartupProfile()/getSPSHistory() must both take a required token parameter",
  );
}

// --- Client components thread a real Clerk token through --------------------

function test_rankings_view_uses_real_clerk_token(): void {
  const source = readSource("app/rankings/RankingsView.tsx");
  expect(/import\s*\{\s*useAuth\s*\}\s*from\s*"@clerk\/nextjs"/.test(source), "RankingsView must use Clerk's real useAuth()");
  expect(/await getToken\(\)/.test(source), "RankingsView must call the real getToken()");
}

function test_discovery_view_uses_real_clerk_token(): void {
  const source = readSource("app/search/DiscoveryView.tsx");
  expect(/import\s*\{\s*useAuth\s*\}\s*from\s*"@clerk\/nextjs"/.test(source), "DiscoveryView must use Clerk's real useAuth()");
  expect(/await getToken\(\)/.test(source), "DiscoveryView must call the real getToken()");
}

function test_compare_view_uses_real_clerk_token(): void {
  const source = readSource("app/compare/CompareView.tsx");
  expect(/import\s*\{\s*useAuth\s*\}\s*from\s*"@clerk\/nextjs"/.test(source), "CompareView must use Clerk's real useAuth()");
  expect(/await getToken\(\)/.test(source), "CompareView must call the real getToken()");
}

// --- Disclosure: private by default -----------------------------------------

function test_analyze_form_discloses_private_by_default(): void {
  const source = readSource("app/analyze/AnalyzeStartupForm.tsx");
  expect(
    /Private by default/.test(source),
    "AnalyzeStartupForm must clearly disclose that new analyses are private by default",
  );
}

// --- proxy.ts kept in sync (UX-only optimizer, not the real boundary) ------

function test_proxy_matcher_includes_newly_protected_routes(): void {
  const source = readSource("proxy.ts");
  const arrayStart = source.indexOf("createRouteMatcher([");
  const arrayEnd = source.indexOf("]);", arrayStart);
  const arrayText = source.slice(arrayStart, arrayEnd);

  for (const route of ["/startup(.*)", "/rankings(.*)", "/search(.*)", "/compare(.*)"]) {
    expect(arrayText.includes(`"${route}"`), `proxy.ts's route matcher must include ${route}`);
  }
}

// --- My Startups / Saved must not bypass report authorization --------------

function test_saved_startups_view_does_not_render_analysis_content_inline(): void {
  const source = readSource("app/saved/SavedStartupsView.tsx");
  expect(
    !/\.methodology\b/.test(source),
    "SavedStartupsView must never render methodology content inline -- it must link to the " +
      "authorized /startup/{name} route instead",
  );
}

function test_founder_home_does_not_render_analysis_content_inline(): void {
  const source = readSource("app/founder/FounderHome.tsx");
  expect(
    !/\.methodology\b/.test(source),
    "FounderHome must never render methodology content inline -- it must link to the authorized " +
      "workspace/report routes instead",
  );
}

const TESTS: [string, () => void][] = [
  ["test_startup_profile_page_calls_auth_protect", test_startup_profile_page_calls_auth_protect],
  ["test_startup_profile_page_forwards_a_real_token", test_startup_profile_page_forwards_a_real_token],
  ["test_rankings_page_calls_auth_protect", test_rankings_page_calls_auth_protect],
  ["test_search_page_calls_auth_protect", test_search_page_calls_auth_protect],
  ["test_compare_page_calls_auth_protect", test_compare_page_calls_auth_protect],
  ["test_rankings_api_client_requires_token", test_rankings_api_client_requires_token],
  ["test_discovery_api_client_requires_token", test_discovery_api_client_requires_token],
  ["test_compare_api_client_requires_token", test_compare_api_client_requires_token],
  ["test_startups_api_client_requires_token", test_startups_api_client_requires_token],
  ["test_rankings_view_uses_real_clerk_token", test_rankings_view_uses_real_clerk_token],
  ["test_discovery_view_uses_real_clerk_token", test_discovery_view_uses_real_clerk_token],
  ["test_compare_view_uses_real_clerk_token", test_compare_view_uses_real_clerk_token],
  ["test_analyze_form_discloses_private_by_default", test_analyze_form_discloses_private_by_default],
  ["test_proxy_matcher_includes_newly_protected_routes", test_proxy_matcher_includes_newly_protected_routes],
  ["test_saved_startups_view_does_not_render_analysis_content_inline", test_saved_startups_view_does_not_render_analysis_content_inline],
  ["test_founder_home_does_not_render_analysis_content_inline", test_founder_home_does_not_render_analysis_content_inline],
];

function main(): void {
  console.log("\nSecure Analysis Visibility (frontend) tests");
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
