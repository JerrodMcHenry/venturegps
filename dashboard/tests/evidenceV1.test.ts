// Task 31 -- Evidence Engine v1 product integration, frontend coverage.
// Backend authorization/ownership coverage lives in
// app/tests/test_evidence_v1_integration.py (the authoritative source of
// truth for the actual scoping rule); this file proves the FRONTEND
// side. Same "read the file as source text" technique every other test
// in this directory uses for files that import next/navigation/
// @clerk/nextjs, or -- as here -- a relative import with no file
// extension (lib/api/analyze.ts's own `from "./client"`), which Node's
// native ESM loader cannot resolve outside a bundler (see
// tests/myAnalyses.test.ts's own comment on this exact constraint).
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

// --- 1. isEvidenceV1Response() ------------------------------------------

function test_isEvidenceV1Response_discriminates_on_the_engine_field(): void {
  const source = readSource("lib/api/analyze.ts");
  expect(/export function isEvidenceV1Response/.test(source), "isEvidenceV1Response must be exported for every caller (the form, future report code) to reuse");
  expect(/response as EvidenceV1AnalysisResponse\)\.engine === "evidence_v1"/.test(source), "must discriminate strictly on the real `engine` field, not guess from shape");
}

// --- 2. API client (importable directly -- no next/clerk dependency) -------

function test_getEvidenceV1Analysis_requires_a_token_and_calls_the_real_endpoint(): void {
  const source = readSource("lib/api/evidenceV1.ts");
  expect(/getEvidenceV1Analysis\(\s*analysisId:\s*string,\s*token:\s*string\s*\|\s*null/.test(source), "getEvidenceV1Analysis() must take a required token parameter");
  expect(/`\/evidence-v1\/analyses\/\$\{encodeURIComponent\(analysisId\)\}`/.test(source), "must call the real, encoded GET /evidence-v1/analyses/{id} endpoint");
}

function test_getMyEvidenceV1Analyses_calls_the_separate_evidence_v1_list_endpoint(): void {
  const source = readSource("lib/api/evidenceV1.ts");
  expect(/"\/me\/analyses\/evidence-v1"/.test(source), "must call the real, SEPARATE GET /me/analyses/evidence-v1 endpoint (never the legacy /me/analyses)");
}

function test_analyze_client_sends_engine_as_a_request_not_an_authorization(): void {
  const source = readSource("lib/api/analyze.ts");
  expect(/engine\?:\s*"evidence_v1"/.test(source), "the client type must make clear `engine` only ever REQUESTS evidence_v1");
  expect(/formData\.append\("engine", engine\)/.test(source), "engine must be sent as a plain form field, like every other optional field");
}

// --- 3. Ownership: the report page fetches by analysis id, never company name

function test_evidence_report_page_uses_the_real_auth_boundary(): void {
  const source = readSource("app/evidence/[analysisId]/page.tsx");
  expect(/import\s*\{\s*auth\s*\}\s*from\s*"@clerk\/nextjs\/server"/.test(source), "must import Clerk's real server-side auth()");
  expect(/await auth\.protect\(\)/.test(source), "must call auth.protect()");
}

function test_evidence_report_page_fetches_by_analysis_id_never_company_name(): void {
  const source = readSource("app/evidence/[analysisId]/page.tsx");
  expect(/params:\s*Promise<\{\s*analysisId:\s*string;?\s*\}>/.test(source), "the route must key on analysisId, not a company-name segment");
  expect(/getEvidenceV1Analysis\(analysisId, token\)/.test(source), "must fetch by the real analysisId + real token");
  expect(!/company_name.*params/.test(source), "must never resolve identity from a company-name path parameter");
}

function test_evidence_report_page_handles_not_found_without_leaking_existence(): void {
  const source = readSource("app/evidence/[analysisId]/page.tsx");
  expect(/isNotFoundError/.test(source), "must handle the backend's non-leaking 404 explicitly");
  expect(/Analysis not found/.test(source), "must render a generic not-found state, never a distinguishing message");
}

// --- 4. Untrusted evidence text is never rendered as HTML (item 20) --------

function test_report_component_never_uses_dangerously_set_inner_html(): void {
  const source = readSource("components/evidence/EvidenceV1Report.tsx");
  // Checks actual USAGE (the JSX attribute), not the module's own
  // doc-comment that happens to name the attribute while explaining why
  // it's avoided -- a plain string search would false-positive on that
  // comment.
  expect(!/dangerouslySetInnerHTML\s*=/.test(source), "evidence text (claim_text/excerpt, untrusted retrieved content) must never be rendered via dangerouslySetInnerHTML");
}

function test_report_component_external_links_are_hardened(): void {
  const source = readSource("components/evidence/EvidenceV1Report.tsx");
  const hrefMatches = source.match(/target="_blank"[\s\S]{0,80}?rel="[^"]*"/g) ?? [];
  expect(hrefMatches.length > 0, "expected at least one external (_blank) link");
  for (const match of hrefMatches) {
    expect(/noopener/.test(match), `every target="_blank" link must set rel="noopener": ${match}`);
    expect(/noreferrer/.test(match), `every target="_blank" link must set rel="noreferrer": ${match}`);
  }
}

function test_report_component_never_renders_an_overall_score(): void {
  // item 12's own explicit "do not create an overall 0-100 company score".
  const source = readSource("components/evidence/EvidenceV1Report.tsx");
  expect(!/overall_score/.test(source), "the Evidence v1 report must never reference an overall score field");
}

function test_report_component_distinguishes_unscored_from_a_negative_result(): void {
  const source = readSource("components/evidence/EvidenceV1Report.tsx");
  expect(/Unscored/.test(source), "an unscored dimension must be labeled as such, not silently omitted");
  expect(/not a negative finding|not a negative assessment/.test(source), "the copy must explicitly say unknown is not the same as poor performance");
}

// --- 5. My Analyses: merges both engines, links each to its own report ----

function test_my_analyses_view_fetches_both_engines_independently(): void {
  const source = readSource("app/my-analyses/MyAnalysesView.tsx");
  expect(/getMyAnalyses\(token\)/.test(source), "must still fetch the legacy list");
  expect(/getMyEvidenceV1Analyses\(token\)/.test(source), "must also fetch the Evidence v1 list");
  expect(/\.catch\(/.test(source), "a failure fetching one list must not be allowed to blank out the other");
}

function test_my_analyses_view_links_evidence_v1_entries_to_their_own_report_route(): void {
  const source = readSource("app/my-analyses/MyAnalysesView.tsx");
  expect(/\/evidence\/\$\{encodeURIComponent\(entry\.data\.analysis_id\)\}/.test(source), "an Evidence v1 entry must link to /evidence/{id}, never /startup/{name}");
}

function test_my_analyses_view_never_compares_coverage_to_the_legacy_score_badge(): void {
  const source = readSource("app/my-analyses/MyAnalysesView.tsx");
  // The regression this guards: Coverage must render through its OWN
  // badge/copy, never scoreBadgeClasses()/formatScore() (the legacy
  // 0-100-score-tiered styling), which would visually imply the two are
  // the same kind of number.
  const badgeMatch = source.match(/>\s*Evidence v1\s*</);
  expect(badgeMatch !== null, "Evidence v1 badge not found");
  const evidenceBlockStart = badgeMatch!.index!;
  const evidenceBlock = source.slice(evidenceBlockStart, source.indexOf("})", evidenceBlockStart));
  expect(!/scoreBadgeClasses/.test(evidenceBlock), "Coverage must not be styled via the legacy score-tier badge classes");
}

// --- 6. Submission form: evidence_v1 is opt-in, never the default ---------

function test_form_only_requests_evidence_v1_via_an_explicit_query_param(): void {
  const source = readSource("app/analyze/AnalyzeStartupForm.tsx");
  expect(/searchParams\.get\("engine"\) === "evidence_v1"/.test(source), "evidence_v1 must be gated behind an explicit ?engine=evidence_v1, never a default-on toggle");
}

function test_form_redirects_evidence_v1_responses_to_the_new_report_route(): void {
  const source = readSource("app/analyze/AnalyzeStartupForm.tsx");
  expect(/isEvidenceV1Response\(response\)/.test(source), "must check the real response shape before deciding where to navigate");
  expect(/\/evidence\/\$\{encodeURIComponent\(response\.analysis_id\)\}/.test(source), "an evidence_v1 response must redirect to /evidence/{id}");
}

function test_form_loading_state_uses_honest_non_fabricated_language(): void {
  const source = readSource("app/analyze/AnalyzeStartupForm.tsx");
  expect(/EVIDENCE_V1_STAGES/.test(source), "Evidence v1 must have its own honest stage-language list");
  expect(!/\d{1,3}%\s*complete/i.test(source), "loading copy must never fabricate a percentage-complete figure");
}

// --- 7. Type shape matches the backend model --------------------------------

function test_type_shape_matches_the_backend_response_model(): void {
  const source = readSource("types/evidenceV1.ts");
  const typeStart = source.indexOf("export interface EvidenceV1AnalysisResponse");
  expect(typeStart !== -1, "EvidenceV1AnalysisResponse type not found");
  const typeEnd = source.indexOf("}", typeStart);
  const typeText = source.slice(typeStart, typeEnd);

  for (const field of ["analysis_id: string", 'engine: "evidence_v1"', "methodology_version: string", "company_coverage_pct: number | null"]) {
    expect(typeText.includes(field), `EvidenceV1AnalysisResponse must declare ${field}`);
  }
}

const TESTS: [string, () => void][] = [
  ["test_isEvidenceV1Response_discriminates_on_the_engine_field", test_isEvidenceV1Response_discriminates_on_the_engine_field],
  ["test_getEvidenceV1Analysis_requires_a_token_and_calls_the_real_endpoint", test_getEvidenceV1Analysis_requires_a_token_and_calls_the_real_endpoint],
  ["test_getMyEvidenceV1Analyses_calls_the_separate_evidence_v1_list_endpoint", test_getMyEvidenceV1Analyses_calls_the_separate_evidence_v1_list_endpoint],
  ["test_analyze_client_sends_engine_as_a_request_not_an_authorization", test_analyze_client_sends_engine_as_a_request_not_an_authorization],
  ["test_evidence_report_page_uses_the_real_auth_boundary", test_evidence_report_page_uses_the_real_auth_boundary],
  ["test_evidence_report_page_fetches_by_analysis_id_never_company_name", test_evidence_report_page_fetches_by_analysis_id_never_company_name],
  ["test_evidence_report_page_handles_not_found_without_leaking_existence", test_evidence_report_page_handles_not_found_without_leaking_existence],
  ["test_report_component_never_uses_dangerously_set_inner_html", test_report_component_never_uses_dangerously_set_inner_html],
  ["test_report_component_external_links_are_hardened", test_report_component_external_links_are_hardened],
  ["test_report_component_never_renders_an_overall_score", test_report_component_never_renders_an_overall_score],
  ["test_report_component_distinguishes_unscored_from_a_negative_result", test_report_component_distinguishes_unscored_from_a_negative_result],
  ["test_my_analyses_view_fetches_both_engines_independently", test_my_analyses_view_fetches_both_engines_independently],
  ["test_my_analyses_view_links_evidence_v1_entries_to_their_own_report_route", test_my_analyses_view_links_evidence_v1_entries_to_their_own_report_route],
  ["test_my_analyses_view_never_compares_coverage_to_the_legacy_score_badge", test_my_analyses_view_never_compares_coverage_to_the_legacy_score_badge],
  ["test_form_only_requests_evidence_v1_via_an_explicit_query_param", test_form_only_requests_evidence_v1_via_an_explicit_query_param],
  ["test_form_redirects_evidence_v1_responses_to_the_new_report_route", test_form_redirects_evidence_v1_responses_to_the_new_report_route],
  ["test_form_loading_state_uses_honest_non_fabricated_language", test_form_loading_state_uses_honest_non_fabricated_language],
  ["test_type_shape_matches_the_backend_response_model", test_type_shape_matches_the_backend_response_model],
];

function main(): void {
  console.log("\nEvidence Engine v1 (frontend) tests");
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
