// Final UX correction -- Analyze Startup is ONE evidence-backed, website-
// only product whenever the server reports evidence-backed analysis
// enabled, and the unchanged multi-source form when it doesn't. Source-
// text checks (same technique as tests/evidenceV1.test.ts) because
// AnalyzeStartupForm.tsx imports next/navigation + @clerk/nextjs, which
// Node can't load outside the Next bundler. Server authority itself is
// proven backend-side in app/tests/test_evidence_v1_integration.py.
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

const FORM = "app/analyze/AnalyzeStartupForm.tsx";

function stripComments(source: string): string {
  return source.replace(/\{\/\*[\s\S]*?\*\/\}/g, "").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

// The JSX of the two form branches: `{isWebsiteOnly ? ( <website-only> ) : ( <standard> )}`.
function formBranches(): { websiteOnly: string; standard: string } {
  const source = readSource(FORM);
  const formStart = source.indexOf("<form onSubmit={handleSubmit}");
  const start = source.indexOf("{isWebsiteOnly ? (", formStart);
  const split = source.indexOf(") : (", start);
  const end = source.indexOf("Portfolio Release Task 3B", split);
  expect(formStart !== -1 && start !== -1 && split !== -1 && end !== -1, "could not locate the two form branches");
  return { websiteOnly: source.slice(start, split), standard: source.slice(split, end) };
}

// The website-only submit call: `isWebsiteOnly ? await analyzeMultiSource({...}) : ...`.
function websiteOnlySubmitCall(): string {
  const source = readSource(FORM);
  const start = source.indexOf("const response = isWebsiteOnly");
  const end = source.indexOf(": await analyzeMultiSource(", start);
  expect(start !== -1 && end !== -1, "could not locate the website-only submit call");
  return source.slice(start, end);
}

function standardSubmitCall(): string {
  const source = readSource(FORM);
  const start = source.indexOf(": await analyzeMultiSource(", source.indexOf("const response = isWebsiteOnly"));
  return source.slice(start, source.indexOf("});", start));
}

// --- FEATURE FLAG ON ----------------------------------------------------------

function test_flag_on_normal_website_submission_requests_evidence_backed_analysis(): void {
  const call = websiteOnlySubmitCall();
  expect(/engine: "evidence_v1"/.test(call), "the website-only submit must request the evidence-backed engine");
  expect(/websiteUrl: websiteUrl\.trim\(\)/.test(call) && /companyName: companyName\.trim\(\)/.test(call), "must send the website and company name");
  expect(!/pdfFile|companyText|startupId/.test(call), "website-only submit must never send a pitch deck, free-form text or startup_id");
}

function test_flag_on_mode_is_driven_by_the_server_flag_not_the_url(): void {
  const source = readSource(FORM);
  expect(/getVersion\(\)/.test(source), "mode must be read from GET /version");
  expect(/setServerMode\(info\.evidence_v1_enabled \? "evidence" : "standard"\)/.test(source), "website-only mode only when the server reports it enabled");
  expect(/const isWebsiteOnly = analysisMode === "evidence"/.test(source), "website-only must follow the server-derived mode");
  expect(!/searchParams\.get\("engine"\)/.test(source), "no ?engine= query parameter may be read or required");
}

function test_no_engine_selection_control_exists(): void {
  const code = stripComments(readSource(FORM));
  expect(!/type="checkbox"/.test(code), "no engine-selection checkbox may exist");
  expect(!/<select/.test(code), "no engine dropdown may exist");
  expect(!/useEvidenceV1|evidenceV1Available/.test(code), "the old opt-in state must be gone");
}

function test_flag_on_form_has_no_pitch_deck_or_additional_information_input(): void {
  const { websiteOnly } = formBranches();
  expect(/id="website-url"/.test(websiteOnly), "website-only form must have the website input");
  expect(/id="company-name"/.test(websiteOnly), "website-only form must have the company name input");
  expect(!/pitch-deck-file|type="file"|Pitch Deck/.test(websiteOnly), "website-only form must have no pitch-deck input");
  expect(!/company-text|<Textarea|Additional Company Information/.test(websiteOnly), "website-only form must have no additional-information input");
}

function test_flag_on_copy_describes_one_product_without_internal_terms(): void {
  const source = readSource(FORM);
  const { websiteOnly } = formBranches();
  const subtitle = source.slice(source.indexOf(": isWebsiteOnly\n"), source.indexOf("variant=\"glow\"", source.indexOf(": isWebsiteOnly\n")));
  const userFacing = stripComments(websiteOnly) + subtitle;
  expect(/researches public sources and builds an evidence-backed assessment/.test(userFacing), "subtitle must describe the evidence-backed website analysis");
  expect(/left unscored rather than guessed/.test(userFacing), "must explain unscored categories");
  for (const forbidden of [/legacy/i, /evidence_v1/, /engine/i, /beta/i, /methodology version/i, /migrat/i]) {
    expect(!forbidden.test(stripComments(userFacing).replace(/engine: "evidence_v1"/g, "")), `user-facing copy must not mention ${forbidden}`);
  }
}

function test_flag_on_uses_the_evidence_backed_loading_state(): void {
  const source = readSource(FORM);
  expect(/<AnalyzingState elapsedSeconds=\{elapsedSeconds\} isEvidenceV1=\{isWebsiteOnly\} \/>/.test(source), "the website-only flow must show the evidence-backed loading copy/stages");
  expect(/const stages = isEvidenceV1 \? EVIDENCE_V1_STAGES : STAGES/.test(source), "loading stages must switch on the same flag");
}

function test_flag_on_success_redirects_to_the_evidence_report(): void {
  const source = readSource(FORM);
  const check = source.indexOf("if (isEvidenceV1Response(response))");
  expect(check !== -1, "must narrow on the real response shape");
  expect(/router\.push\(`\/evidence\/\$\{encodeURIComponent\(response\.analysis_id\)\}`\)/.test(source.slice(check, check + 200)), "an evidence-backed response must redirect to /evidence/{analysis_id}");
}

function test_flag_on_requires_company_name_and_website_client_side(): void {
  const source = readSource(FORM);
  expect(/function validateWebsiteOnlyForm\(companyName: string, websiteUrl: string\)/.test(source), "website-only validation must exist");
  expect(/isWebsiteOnly\s*\?\s*validateWebsiteOnlyForm\(companyName, websiteUrl\)/.test(source), "website-only submit must use website-only validation");
}

// --- FEATURE FLAG OFF ---------------------------------------------------------

function test_flag_off_or_unreadable_falls_back_to_the_standard_form(): void {
  const source = readSource(FORM);
  const catchBlock = source.slice(source.indexOf(".catch(() => {", source.indexOf("getVersion()")), source.indexOf("return () => {", source.indexOf("getVersion()")));
  expect(/setServerMode\("standard"\)/.test(catchBlock), "an unreadable /version must fail closed to the standard form");
  const { standard } = formBranches();
  for (const id of ['id="website-url"', 'id="pitch-deck-file"', 'id="company-text"']) {
    expect(standard.includes(id), `standard form must keep ${id}`);
  }
}

function test_flag_off_standard_submit_never_requests_the_evidence_backed_engine(): void {
  const call = standardSubmitCall();
  expect(!/engine/.test(call), "the standard submit must not request any engine (server defaults to the standard analysis)");
  expect(/pdfFile/.test(call) && /companyText/.test(call) && /startupId/.test(call), "standard submit must keep its existing multi-source fields");
}

function test_page_never_renders_a_form_before_the_mode_is_known(): void {
  const source = readSource(FORM);
  expect(/useState<AnalysisMode>\("checking"\)/.test(source), "mode must start as checking");
  expect(/founderTarget\.status === "checking" \|\| analysisMode === "checking"/.test(source), "a skeleton (not the wrong form) must render while /version is loading");
}

function test_founder_reanalysis_keeps_its_existing_standard_flow(): void {
  const source = readSource(FORM);
  expect(/const analysisMode: AnalysisMode = requestedStartupId !== null \? "standard" : serverMode/.test(source), "?startup_id= re-analysis must keep the standard flow (evidence-backed engine doesn't support it)");
}

// --- SECURITY / AUTH ----------------------------------------------------------

function test_page_auth_gate_is_unchanged(): void {
  const page = readSource("app/analyze/page.tsx");
  expect(/await auth\.protect\(\)/.test(page), "/analyze must still be protected by auth.protect()");
  const form = readSource(FORM);
  expect(/const token = await getToken\(\);/.test(form) && /SESSION_EXPIRED_MESSAGE/.test(form), "submit must still require a fresh Clerk token");
}

function test_client_only_requests_never_authorizes_the_engine(): void {
  const client = readSource("lib/api/analyze.ts");
  expect(/formData\.append\("engine", engine\)/.test(client), "engine is only a plain request field -- the server decides");
}

// --- BACKWARDS COMPATIBILITY --------------------------------------------------

function test_legacy_report_route_and_redirect_still_exist(): void {
  const form = readSource(FORM);
  expect(/router\.push\(`\/startup\/\$\{encodeURIComponent\(profileName\)\}`\)/.test(form), "a standard response must still redirect to its /startup/{name} report");
  const legacyPage = readSource("app/startup/[id]/page.tsx");
  expect(/getStartupProfile\(/.test(legacyPage) && /await auth\.protect\(\)/.test(legacyPage), "legacy report route must still load stored analyses behind auth");
}

function test_my_analyses_still_routes_each_generation_to_its_own_report(): void {
  const view = readSource("app/my-analyses/MyAnalysesView.tsx");
  expect(/getMyAnalyses\(token\)/.test(view) && /getMyEvidenceV1Analyses\(token\)/.test(view), "My Analyses must still fetch both generations");
  expect(/\/evidence\/\$\{encodeURIComponent\(entry\.data\.analysis_id\)\}/.test(view), "evidence-backed entries must link to /evidence/{id}");
  expect(/\/startup\//.test(view), "historical entries must still link to /startup/{name}");
}

const TESTS: [string, () => void][] = [
  ["test_flag_on_normal_website_submission_requests_evidence_backed_analysis", test_flag_on_normal_website_submission_requests_evidence_backed_analysis],
  ["test_flag_on_mode_is_driven_by_the_server_flag_not_the_url", test_flag_on_mode_is_driven_by_the_server_flag_not_the_url],
  ["test_no_engine_selection_control_exists", test_no_engine_selection_control_exists],
  ["test_flag_on_form_has_no_pitch_deck_or_additional_information_input", test_flag_on_form_has_no_pitch_deck_or_additional_information_input],
  ["test_flag_on_copy_describes_one_product_without_internal_terms", test_flag_on_copy_describes_one_product_without_internal_terms],
  ["test_flag_on_uses_the_evidence_backed_loading_state", test_flag_on_uses_the_evidence_backed_loading_state],
  ["test_flag_on_success_redirects_to_the_evidence_report", test_flag_on_success_redirects_to_the_evidence_report],
  ["test_flag_on_requires_company_name_and_website_client_side", test_flag_on_requires_company_name_and_website_client_side],
  ["test_flag_off_or_unreadable_falls_back_to_the_standard_form", test_flag_off_or_unreadable_falls_back_to_the_standard_form],
  ["test_flag_off_standard_submit_never_requests_the_evidence_backed_engine", test_flag_off_standard_submit_never_requests_the_evidence_backed_engine],
  ["test_page_never_renders_a_form_before_the_mode_is_known", test_page_never_renders_a_form_before_the_mode_is_known],
  ["test_founder_reanalysis_keeps_its_existing_standard_flow", test_founder_reanalysis_keeps_its_existing_standard_flow],
  ["test_page_auth_gate_is_unchanged", test_page_auth_gate_is_unchanged],
  ["test_client_only_requests_never_authorizes_the_engine", test_client_only_requests_never_authorizes_the_engine],
  ["test_legacy_report_route_and_redirect_still_exist", test_legacy_report_route_and_redirect_still_exist],
  ["test_my_analyses_still_routes_each_generation_to_its_own_report", test_my_analyses_still_routes_each_generation_to_its_own_report],
];

function main(): void {
  console.log("\nAnalyze Startup (website-only evidence-backed flow) tests");
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
