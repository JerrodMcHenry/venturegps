// Portfolio Release Task 7, Phase 3 -- Engine Transparency & Report
// Quality. Same "read the file as source text" technique this
// directory's other tests use for files that import next/navigation,
// @clerk/nextjs, or Next's own Metadata API.
//
// Run with:
//   node tests/engineTransparency.test.ts
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

function stripComments(source: string): string {
  const withoutBlockComments = source.replace(/\/\*[\s\S]*?\*\//g, "");
  return withoutBlockComments.split("\n").filter((line) => !line.trim().startsWith("//")).join("\n");
}

// --- 1. The How VentureGPS Works page ---------------------------------------

function test_how_it_works_page_exists_and_covers_the_five_real_stages(): void {
  expect(existsSync(path.join(DASHBOARD_ROOT, "app/how-it-works/page.tsx")), "app/how-it-works/page.tsx must exist");

  const source = readSource("app/how-it-works/page.tsx");
  for (const stage of ["Startup information", "AI-assisted research", "AI-generated assessments", "Deterministic validation and scoring", "VentureGPS Report"]) {
    expect(source.includes(stage), `The How It Works page must describe the "${stage}" stage`);
  }
}

function test_how_it_works_page_explains_probabilistic_vs_deterministic_with_a_limits_disclaimer(): void {
  const source = readSource("app/how-it-works/page.tsx");
  expect(/Probabilistic/i.test(source), "Must explain the probabilistic concept");
  expect(/Deterministic/i.test(source), "Must explain the deterministic concept");
  // The task's own explicit required disclosure: reproducible math !=
  // correct AI judgment.
  expect(/does not mean the[\s\S]*?judgments[\s\S]*?correct/i.test(source), "Must explicitly state that reproducible calculations do not guarantee correct AI judgments or claims");
}

function test_how_it_works_page_is_public_not_behind_auth(): void {
  // Checked against code with comments stripped -- this file's own
  // comment legitimately explains, by name, why auth.protect() is
  // absent.
  const source = stripComments(readSource("app/how-it-works/page.tsx"));
  expect(!/auth\.protect\(\)/.test(source), "The How It Works page must be public (no auth.protect()) -- explanatory content, not account-gated");
}

function test_how_it_works_is_linked_from_nav_homepage_and_report(): void {
  const navSource = stripComments(readSource("components/layout/PublicNav.tsx"));
  expect(/href:\s*"\/how-it-works"/.test(navSource), "Primary nav must link to /how-it-works");

  const homepageSectionSource = readSource("components/home/ventureGps/HowItWorksSection.tsx");
  expect(/href="\/how-it-works"/.test(homepageSectionSource), "The homepage's own How It Works section must link onward to the full page");

  const reportDisclosureSource = readSource("components/startup/HowThisAnalysisWasGenerated.tsx");
  expect(/href="\/how-it-works"/.test(reportDisclosureSource), "The report's own methodology disclosure must link to the full How It Works page");
}

// --- 2. Analytical integrity: Observed weakness / Information gap / Inferred risk ---

function test_key_risks_are_built_from_subscore_evidence_status_not_free_text(): void {
  const source = readSource("components/startup/StartupHeroV2.tsx");
  // The old, unreliable derivation (pillar.weaknesses[0], a free-text
  // string never tagged to an evidence_status) must be gone.
  expect(!/\.weaknesses\[0\]/.test(source), "Key Risks must no longer read the untagged pillar.weaknesses[0] free-text field");
  expect(/evidence_status/.test(source), "Key Risks must be built from Subscore.evidence_status, the real backend-verified signal");
  expect(/"observed_weakness"/.test(source) && /"information_gap"/.test(source) && /"inferred_risk"/.test(source), "Must define all three required kinds: observed weakness, information gap, inferred risk");
}

function test_information_gaps_are_never_labeled_as_demonstrated_weakness(): void {
  const source = readSource("components/startup/StartupHeroV2.tsx");
  // An Unavailable dimension must route to information_gap, never
  // observed_weakness/inferred_risk -- checked structurally: the
  // Unavailable branch must return before reaching the score-based
  // weakness/risk branches.
  const unavailableBranch = source.slice(source.indexOf('sub.evidence_status === "Unavailable"'), source.indexOf('if (sub.score === null'));
  expect(unavailableBranch.includes('"information_gap"'), "The Unavailable branch must classify as information_gap");
  expect(!unavailableBranch.includes('"observed_weakness"'), "The Unavailable branch must never classify as observed_weakness");
}

function test_key_risks_deduplicated_and_capped(): void {
  const source = readSource("components/startup/StartupHeroV2.tsx");
  expect(/seen\.has\(key\)/.test(source), "Key Risks must dedupe by text (Phase 3's own \"eliminate duplicate risks where practical\")");
  expect(/\.slice\(0,\s*5\)/.test(source), "Key Risks must stay a concise, capped summary");
}

function test_free_text_summary_has_a_conservative_disclaimer(): void {
  const source = readSource("components/startup/StartupHeroV2.tsx");
  expect(/not individually evidence-tagged/i.test(source), "The free-text Summary must disclose that it isn't individually evidence-tagged (the backend can't reliably classify it -- Phase 3's own 'use conservative wording' instruction)");
}

// --- 3. Evidence transparency -----------------------------------------------

function test_evidence_url_link_path_exists(): void {
  const source = readSource("components/startup/PillarWorkspace.tsx");
  expect(/item\.url/.test(source), "EvidenceList must still render a clickable link when an evidence item has a real url");
}

function test_evidence_section_discloses_the_unlinked_quote_gap(): void {
  const source = readSource("components/startup/PillarWorkspace.tsx");
  expect(/yet linked to a specific source/i.test(source), "The Evidence section must honestly disclose that quotes aren't individually linked to a source, rather than implying verification that doesn't exist");
}

function test_glossary_distinguishes_evidence_status_from_key_risk_labels(): void {
  const source = readSource("components/startup/HowThisAnalysisWasGenerated.tsx");
  expect(/How Key Risks labels map to these/.test(source), "The glossary must explain how Key Risks' friendly labels relate to the raw Observed/Inferred/Unavailable statuses -- they are related but not interchangeable");
}

const TESTS: [string, () => void][] = [
  ["test_how_it_works_page_exists_and_covers_the_five_real_stages", test_how_it_works_page_exists_and_covers_the_five_real_stages],
  ["test_how_it_works_page_explains_probabilistic_vs_deterministic_with_a_limits_disclaimer", test_how_it_works_page_explains_probabilistic_vs_deterministic_with_a_limits_disclaimer],
  ["test_how_it_works_page_is_public_not_behind_auth", test_how_it_works_page_is_public_not_behind_auth],
  ["test_how_it_works_is_linked_from_nav_homepage_and_report", test_how_it_works_is_linked_from_nav_homepage_and_report],
  ["test_key_risks_are_built_from_subscore_evidence_status_not_free_text", test_key_risks_are_built_from_subscore_evidence_status_not_free_text],
  ["test_information_gaps_are_never_labeled_as_demonstrated_weakness", test_information_gaps_are_never_labeled_as_demonstrated_weakness],
  ["test_key_risks_deduplicated_and_capped", test_key_risks_deduplicated_and_capped],
  ["test_free_text_summary_has_a_conservative_disclaimer", test_free_text_summary_has_a_conservative_disclaimer],
  ["test_evidence_url_link_path_exists", test_evidence_url_link_path_exists],
  ["test_evidence_section_discloses_the_unlinked_quote_gap", test_evidence_section_discloses_the_unlinked_quote_gap],
  ["test_glossary_distinguishes_evidence_status_from_key_risk_labels", test_glossary_distinguishes_evidence_status_from_key_risk_labels],
];

function main(): void {
  console.log("\nEngine Transparency & Report Quality tests");
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
