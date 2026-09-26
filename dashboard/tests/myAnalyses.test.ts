// Portfolio Release Task 4 -- My Analyses, Phase 3 frontend coverage.
// Backend authorization coverage lives in app/tests/test_my_analyses.py
// (the authoritative source of truth for the actual scoping rule); this
// file only proves the FRONTEND side: the API client requires a token,
// the page calls the real Clerk auth boundary, the view fetches with a
// real token and reopens each entry via its own company_name, and the
// type shape matches the backend's MyAnalysisEntry. Same "read the file
// as source text" technique every other test in this directory uses for
// files that import next/navigation/@clerk/nextjs.
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

function test_api_client_requires_a_token(): void {
  const source = readSource("lib/api/myAnalyses.ts");
  expect(/getMyAnalyses\(token:\s*string\s*\|\s*null\)/.test(source), "getMyAnalyses() must take a required token parameter");
  expect(/"\/me\/analyses"/.test(source), "getMyAnalyses() must call the real GET /me/analyses endpoint");
}

function test_page_calls_the_real_auth_boundary(): void {
  const source = readSource("app/my-analyses/page.tsx");
  expect(/import\s*\{\s*auth\s*\}\s*from\s*"@clerk\/nextjs\/server"/.test(source), "app/my-analyses/page.tsx must import Clerk's real server-side auth()");
  expect(/await auth\.protect\(\)/.test(source), "app/my-analyses/page.tsx must call auth.protect()");
}

function test_view_uses_a_real_clerk_token(): void {
  const source = readSource("app/my-analyses/MyAnalysesView.tsx");
  expect(/import\s*\{\s*useAuth\s*\}\s*from\s*"@clerk\/nextjs"/.test(source), "MyAnalysesView must use Clerk's real useAuth()");
  expect(/await getToken\(\)/.test(source), "MyAnalysesView must call the real getToken()");
  expect(/getMyAnalyses\(token\)/.test(source), "MyAnalysesView must call getMyAnalyses() with the real token");
}

function test_view_reopens_each_entry_via_its_own_company_name(): void {
  // The regression this guards: an entry must link to the SAME authorized
  // report GET /startup/{company_name} already gates -- never a second,
  // separate read of analysis content embedded in the list itself.
  const source = readSource("app/my-analyses/MyAnalysesView.tsx");
  expect(/\/startup\/\$\{encodeURIComponent\(entry\.company_name\)\}/.test(source), "Each entry must link to /startup/{company_name} to reopen its own authorized report");
  expect(!/entry\.methodology/.test(source), "MyAnalysesView must never render analysis content inline -- it must link to the authorized /startup/{name} route instead");
}

function test_view_handles_the_empty_state_honestly(): void {
  const source = readSource("app/my-analyses/MyAnalysesView.tsx");
  expect(/analyses\.length === 0/.test(source), "MyAnalysesView must render a distinct empty state rather than an empty list with no explanation");
  expect(/href="\/analyze"/.test(source), "The empty state must offer a way to submit a first analysis");
}

function test_type_shape_matches_the_backend_model(): void {
  const source = readSource("types/startup.ts");
  const typeStart = source.indexOf("export type MyAnalysisEntry");
  expect(typeStart !== -1, "MyAnalysisEntry type not found in types/startup.ts");
  const typeEnd = source.indexOf("};", typeStart);
  const typeText = source.slice(typeStart, typeEnd);

  for (const field of ["analysis_id: number", "startup_id: number | null", "company_name: string | null", "overall_score: number | null", "created_at: string"]) {
    expect(typeText.includes(field), `MyAnalysisEntry must declare ${field}`);
  }
}

const TESTS: [string, () => void][] = [
  ["test_api_client_requires_a_token", test_api_client_requires_a_token],
  ["test_page_calls_the_real_auth_boundary", test_page_calls_the_real_auth_boundary],
  ["test_view_uses_a_real_clerk_token", test_view_uses_a_real_clerk_token],
  ["test_view_reopens_each_entry_via_its_own_company_name", test_view_reopens_each_entry_via_its_own_company_name],
  ["test_view_handles_the_empty_state_honestly", test_view_handles_the_empty_state_honestly],
  ["test_type_shape_matches_the_backend_model", test_type_shape_matches_the_backend_model],
];

function main(): void {
  console.log("\nMy Analyses (frontend) tests");
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
