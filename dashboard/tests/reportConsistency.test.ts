// Portfolio Release Task 6 -- Simplify and Reconcile the Analysis
// Experience. Same "read the file as source text" technique this
// directory's other tests use for files that import next/navigation,
// @clerk/nextjs, or (here) @/components/sps -- none of which plain node
// can resolve outside Next's own build.
//
// Three things this file guards, matching the task's own three explicit
// regression categories:
//   1. Conflicting report data -- the hero must derive its PRIMARY score
//      from the same V2.1 pillars the detailed pillar workspace renders,
//      never swap to a different, stricter-methodology assessment (SPS
//      V3) that could silently disagree with the six pillar cards right
//      below it. V3, when present, is a secondary note only.
//   2. Insufficient-evidence states -- an analysis with zero scoreable
//      pillars must show an honest "not enough evidence" state, never a
//      fabricated 0.0 ring (V2.1's own calculate_base_score() returns a
//      bare 0.0 when nothing was scoreable -- this is the frontend-side
//      guard against exactly that).
//   3. Consistent terminology -- "Startup Power Score"/"Executive
//      Coaching Summary"/"V2.1"/bare "SIE" (as if it were the product
//      name) must not appear in the primary report/analyze UI; "SIE"
//      remains a legitimate internal engine name in code comments.
//
// Run with:
//   node tests/reportConsistency.test.ts
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

// Strips // line comments and /* ... */ / {/* ... */} block comments
// (tracking state across lines, not just a per-line prefix check) so
// terminology checks assert against rendered/user-facing text, not this
// codebase's own convention of explaining a removed/renamed term by name
// in a comment.
function stripComments(source: string): string {
  // Block comments first (handles both /* */ and JSX's {/* */}, since
  // the latter is just /* */ wrapped in one extra brace on each side).
  const withoutBlockComments = source.replace(/\/\*[\s\S]*?\*\//g, "");
  return withoutBlockComments
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
}

// --- 1. Conflicting report data: one consistent primary score ---------------

function test_hero_always_derives_primary_score_from_v2_1(): void {
  const source = readSource("components/startup/StartupHeroV2.tsx");
  // The old behavior (methodology.sps_v3 ? <SPSV3ScoreSection> : <SPSRing>)
  // must be gone -- SPSV3ScoreSection must no longer be imported/rendered
  // as the primary display at all. (Checked against code with comments
  // stripped -- this file's own comment legitimately names the removed
  // component to explain the fix.)
  expect(!/SPSV3ScoreSection/.test(stripComments(source)), "StartupHeroV2 must no longer import or render SPSV3ScoreSection as the primary score display");
  expect(/<SPSRing\s/.test(source), "StartupHeroV2 must render SPSRing for its primary score");
  expect(/score=\{methodology\.startup_intelligence_score\}/.test(source), "The primary ring must be driven by startup_intelligence_score (V2.1) -- the same source the pillar workspace below uses -- not a conditional swap");
}

function test_v3_shown_as_a_secondary_note_not_hidden(): void {
  // The task's own explicit instruction: "Do not hide the discrepancy
  // with CSS." V3 must still be shown somewhere, just demoted -- never
  // silently dropped.
  const source = readSource("components/startup/StartupHeroV2.tsx");
  expect(/methodology\.sps_v3/.test(source), "StartupHeroV2 must still reference methodology.sps_v3 -- V3 data must not be silently dropped");
  expect(/experimental/i.test(source), "V3 must be clearly labeled as a separate/experimental assessment, not presented as equivalent to the primary score");
}

function test_sps_history_no_longer_relabels_around_the_conflict(): void {
  // The real fix removes the need for a "legacy"/"V2.1" disambiguating
  // label at all -- SPSHistory always says "Current Score"/"Score
  // History" now that the hero agrees with it.
  const source = stripComments(readSource("components/startup/SPSHistory.tsx"));
  expect(!/isLegacyLabel/.test(source), "SPSHistory must no longer take an isLegacyLabel prop -- there is nothing left to disambiguate");

  const pageSource = stripComments(readSource("app/startup/[id]/page.tsx"));
  expect(!/isLegacyLabel/.test(pageSource), "The startup report page must no longer pass isLegacyLabel to SPSHistory");
}

// --- 2. Insufficient-evidence states: never a fabricated score --------------

function test_hero_never_shows_a_fabricated_score_when_evidence_is_insufficient(): void {
  const source = readSource("components/startup/StartupHeroV2.tsx");
  expect(/function isFullyInsufficientEvidence/.test(source), "StartupHeroV2 must define a guard for the all-pillars-unavailable case");
  expect(/pillars_unavailable_entirely/.test(source), "The guard must use the real structural_coverage.pillars_unavailable_entirely signal, not a new invented field");
  expect(/insufficientEvidence/.test(source), "The insufficient-evidence guard must actually be used in the render output");
  expect(/Not enough evidence yet/.test(stripComments(source)), "An honest \"not enough evidence\" message must render in the insufficient-evidence case");
}

// --- 3. Consistent terminology -----------------------------------------------

const REPORT_AND_ANALYZE_FILES = [
  "components/startup/StartupHeroV2.tsx",
  "components/startup/SPSHistory.tsx",
  "components/startup/SPSV3ScoreSection.tsx",
  "components/startup/IntelligencePillars.tsx",
  "components/sps/RingCenter.tsx",
  "components/sps/SPSRing.tsx",
  "app/startup/[id]/page.tsx",
  "app/analyze/AnalyzeStartupForm.tsx",
  "app/my-analyses/MyAnalysesView.tsx",
  "app/saved/SavedStartupsView.tsx",
];

function test_no_startup_power_score_in_primary_report_ui(): void {
  for (const file of REPORT_AND_ANALYZE_FILES) {
    const rendered = stripComments(readSource(file));
    expect(!/Startup Power Score/.test(rendered), `${file} must not render "Startup Power Score" -- the standard term is "VentureGPS Score"`);
  }
}

function test_no_executive_coaching_summary_in_primary_ui(): void {
  const rendered = stripComments(readSource("components/startup/StartupHeroV2.tsx"));
  expect(!/Executive Coaching Summary/.test(rendered), "StartupHeroV2 must not render \"Executive Coaching Summary\" -- the standard term is \"Summary\"");
  expect(/>\s*Summary\s*</.test(readSource("components/startup/StartupHeroV2.tsx")), "StartupHeroV2 must render a plain \"Summary\" heading");
}

function test_no_v2_1_or_legacy_label_in_primary_report_ui(): void {
  for (const file of ["components/startup/SPSHistory.tsx", "components/startup/StartupHeroV2.tsx", "app/startup/[id]/page.tsx"]) {
    const rendered = stripComments(readSource(file));
    expect(!/V2\.1/.test(rendered), `${file} must not render "V2.1" in user-facing text`);
    expect(!/\blegacy\b/i.test(rendered), `${file} must not render "legacy" in user-facing text`);
  }
}

function test_no_bare_sie_as_product_name_in_primary_ui(): void {
  // "SIE" remains a legitimate internal engine name in comments (see
  // stripComments) -- this only checks rendered JSX/string literals,
  // where the product must be called "VentureGPS".
  for (const file of ["app/analyze/AnalyzeStartupForm.tsx", "app/startup/[id]/page.tsx"]) {
    const rendered = stripComments(readSource(file));
    expect(!/\bSIE\b/.test(rendered), `${file} must not refer to the product as "SIE" in rendered text -- SIE is an internal engine name only`);
  }
}

function test_score_ring_uses_venturegps_score(): void {
  const ringCenterSource = readSource("components/sps/RingCenter.tsx");
  expect((stripComments(ringCenterSource).match(/VentureGPS Score/g) ?? []).length >= 2, "RingCenter must render \"VentureGPS Score\" in both the unavailable and real-score branches");

  const spsRingSource = readSource("components/sps/SPSRing.tsx");
  expect(/VentureGPS Score/.test(spsRingSource), "SPSRing's aria-labels must say \"VentureGPS Score\"");
}

function test_intelligence_pillars_section_uses_the_standard_term(): void {
  const source = readSource("components/startup/IntelligencePillars.tsx");
  expect(/Intelligence Pillars/.test(source), "The pillar section must use the standard \"Intelligence Pillars\" term");
}

function test_site_wide_default_title_is_venturegps(): void {
  const source = readSource("app/layout.tsx");
  expect(!/default:\s*"Startup Intelligence Engine"/.test(source), "The site-wide default title must no longer be \"Startup Intelligence Engine\"");
  expect(/default:\s*"VentureGPS"/.test(source), "The site-wide default title must be \"VentureGPS\"");
}

const TESTS: [string, () => void][] = [
  ["test_hero_always_derives_primary_score_from_v2_1", test_hero_always_derives_primary_score_from_v2_1],
  ["test_v3_shown_as_a_secondary_note_not_hidden", test_v3_shown_as_a_secondary_note_not_hidden],
  ["test_sps_history_no_longer_relabels_around_the_conflict", test_sps_history_no_longer_relabels_around_the_conflict],
  ["test_hero_never_shows_a_fabricated_score_when_evidence_is_insufficient", test_hero_never_shows_a_fabricated_score_when_evidence_is_insufficient],
  ["test_no_startup_power_score_in_primary_report_ui", test_no_startup_power_score_in_primary_report_ui],
  ["test_no_executive_coaching_summary_in_primary_ui", test_no_executive_coaching_summary_in_primary_ui],
  ["test_no_v2_1_or_legacy_label_in_primary_report_ui", test_no_v2_1_or_legacy_label_in_primary_report_ui],
  ["test_no_bare_sie_as_product_name_in_primary_ui", test_no_bare_sie_as_product_name_in_primary_ui],
  ["test_score_ring_uses_venturegps_score", test_score_ring_uses_venturegps_score],
  ["test_intelligence_pillars_section_uses_the_standard_term", test_intelligence_pillars_section_uses_the_standard_term],
  ["test_site_wide_default_title_is_venturegps", test_site_wide_default_title_is_venturegps],
];

function main(): void {
  console.log("\nReport Consistency + Terminology tests");
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
