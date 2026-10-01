// Final UX correction -- insight-first Evidence-v1 report. Executes the
// PURE presentation module (lib/evidenceV1Presentation.ts) against the
// offline Notion fixture (tests/fixtures/evidenceV1NotionOffline.json --
// the engine's own offline Notion ledger run through the real
// assemble_full_analysis(); no live analysis), plus source checks on the
// report component for the layering/semantics rules.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import {
  availabilityGapLabel,
  buildReportPresentation,
  strongestFindings,
} from "../lib/evidenceV1Presentation.ts";

import type { EvidenceV1AnalysisDetail, EvidenceV1PillarResult } from "../types/evidenceV1.ts";

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

function loadFixture(): EvidenceV1AnalysisDetail {
  return JSON.parse(readSource("tests/fixtures/evidenceV1NotionOffline.json")) as EvidenceV1AnalysisDetail;
}

// --- 1. Derivation never changes or invents engine values ------------------

function test_presentation_does_not_mutate_the_artifact(): void {
  const analysis = loadFixture();
  const before = JSON.stringify(analysis);
  buildReportPresentation(analysis);
  expect(JSON.stringify(analysis) === before, "presentation derivation must never mutate the persisted artifact");
}

function test_published_pillars_come_first_canonical_order_preserved(): void {
  const analysis = loadFixture();
  const view = buildReportPresentation(analysis);
  expect(view.published.map((p) => p.pillar).join("|") === "Product & Technology", "Notion fixture: only Product & Technology is published");
  expect(view.withheld.length === 5, "the other five pillars are withheld");
  expect(
    view.canonical.map((p) => p.pillar).join("|") === analysis.result.pillar_results.map((p) => p.pillar).join("|"),
    "canonical methodology order must be kept untouched for the overview"
  );
  const withheldOrder = analysis.result.pillar_results.filter((p) => !p.publishable).map((p) => p.pillar);
  expect(view.withheld.map((p) => p.pillar).join("|") === withheldOrder.join("|"), "withheld group must keep canonical relative order");
}

function test_summary_reads_as_prose_from_the_artifact(): void {
  const text = buildReportPresentation(loadFixture()).summary.join(" ");
  expect(text.includes("Public evidence was sufficient to evaluate Product & Technology for Notion."), `summary must say what could be evaluated: ${text}`);
  expect(text.includes("technical depth signal (classified as substantial)"), "findings must use the persisted classification label verbatim");
  expect(text.includes("no qualifying public evidence was found for them"), "a shared persisted availability reason may be stated");
  expect(text.includes("Missing evidence is not negative evidence"), "summary must say missing evidence is not negative evidence");
  // Values already visible directly above/next to the summary are not
  // restated in the prose.
  expect(!/\d+ of \d+|Strength|confidence|\/ 10/.test(text), `summary must not restate count/Strength/Confidence/scores: ${text}`);
  expect(!/overall|grade|VentureGPS Score/i.test(text), "summary must never imply an overall company score");
}

function test_summary_handles_nothing_published(): void {
  const analysis = loadFixture();
  for (const pillar of analysis.result.pillar_results) pillar.publishable = false;
  const text = buildReportPresentation(analysis).summary.join(" ");
  expect(text.includes("was not sufficient to evaluate any area reliably"), `unexpected empty-state summary: ${text}`);
  expect(!/best-supported/.test(text), "no findings may be claimed when nothing published");
}

function test_gaps_lead_uses_product_language_not_threshold_math(): void {
  const view = buildReportPresentation(loadFixture());
  expect(
    view.gapsLead === "VentureGPS found enough evidence to assess Product & Technology. Five additional areas remain unscored because the available public evidence did not meet the required threshold.",
    `unexpected gaps lead: ${view.gapsLead}`
  );
  expect(!/floor|<|%/.test(view.gapsLead + view.summary.join(" ")), "primary copy must not contain gate/threshold math");
}

// --- 2. Findings never bypass the publication gate ---------------------------

function test_strongest_findings_only_from_published_pillars(): void {
  const withheldButScored: EvidenceV1PillarResult = {
    pillar: "Market Opportunity",
    strength: null,
    coverage_pct: 30,
    confidence: "Low",
    publishable: false,
    withhold_reasons: ["only 1 scored dimension(s) < floor 2"],
    dimension_results: [
      { dimension: "market_definition_size", category: "classified", weight: 0.3, score: 9.5, availability: "scorable", supporting_claim_ids: [], confidence: "Low", rationale: "", classification_label: "LARGE" },
    ],
  };
  const findings = strongestFindings([withheldButScored]);
  expect(findings.length === 0, "a scored dimension inside a withheld pillar must never be promoted to a headline finding");
}

function test_strongest_findings_sorted_by_persisted_score(): void {
  const findings = buildReportPresentation(loadFixture()).findings;
  expect(findings.length === 3, "top three findings expected");
  for (let i = 1; i < findings.length; i += 1) {
    expect(findings[i - 1].score >= findings[i].score, "findings must be ordered by the persisted dimension score");
  }
}

// --- 3. Gap reasons are only ones the artifact supports ----------------------

function test_gap_reasons_map_directly_from_availability(): void {
  const view = buildReportPresentation(loadFixture());
  for (const gap of view.gaps) {
    expect(gap.reasons.length > 0, `${gap.pillar} must list at least one gap`);
    for (const { reason } of gap.reasons) {
      expect(reason === availabilityGapLabel("unscored_no_evidence"), `fixture only contains no-evidence gaps, got: ${reason}`);
    }
  }
}

// --- 4. Component layering / semantics ---------------------------------------

function test_component_has_no_score_ring_or_overall_score(): void {
  const source = readSource("components/evidence/EvidenceV1Report.tsx");
  expect(!/<SPSRing|from "@\/components\/sps"/.test(source), "the legacy circular score ring must not be reused");
  expect(!/overall_score|startup_intelligence_score/.test(source), "no overall score field may be referenced");
}

function test_component_states_coverage_is_not_performance(): void {
  const source = readSource("components/evidence/EvidenceV1Report.tsx");
  expect(/Evidence Coverage describes how much of the methodology could be evaluated\. It is not a company\s+performance score\./.test(source), "the required Coverage disclaimer must remain");
}

function test_raw_gate_reasons_only_under_methodology_disclosure(): void {
  const source = readSource("components/evidence/EvidenceV1Report.tsx");
  for (const field of ["pillar.withhold_reasons.map", "result.company_withhold_reasons.map"]) {
    const index = source.indexOf(field);
    expect(index !== -1, `${field} must still be rendered somewhere (transparency)`);
    const before = source.slice(Math.max(0, index - 1200), index);
    expect(/Methodology details/.test(before), `${field} must sit inside a "Methodology details" disclosure`);
  }
}

function test_withheld_pillar_is_a_compact_row_with_native_disclosure(): void {
  const source = readSource("components/evidence/EvidenceV1Report.tsx");
  const start = source.indexOf("function WithheldPillar");
  const body = source.slice(start, source.indexOf("export default", start));
  expect(/<details/.test(body) && /<summary/.test(body), "each withheld row must be a native <details>/<summary>");
  expect(/NEEDS_EVIDENCE_LABEL/.test(body), "the row must show the More evidence needed label");
  expect(!/Not enough qualifying public evidence/.test(body), "the lead paragraph explains why -- the row must not repeat it");
  expect(/const NEEDS_EVIDENCE_LABEL = "More evidence needed"/.test(source), "user-facing label must be More evidence needed");
  expect(!/bg-danger|text-danger/.test(source), "no failure styling anywhere in the evidence report");
}

function test_overview_uses_more_evidence_needed_and_keeps_technical_state_in_details(): void {
  const source = readSource("components/evidence/EvidenceV1Report.tsx");
  const overview = source.slice(source.indexOf("Assessment overview"), source.indexOf("Summary</SectionHeading>"));
  expect(/NEEDS_EVIDENCE_LABEL/.test(overview), "overview tiles must say More evidence needed for a withheld pillar");
  expect(!/Assessment withheld/.test(overview), "overview must not show the technical withheld label");
  const details = source.slice(source.indexOf("function PillarMethodologyDetails"), source.indexOf("function PublishedPillar"));
  expect(/"Assessment withheld"/.test(details), "the technical Assessment withheld state must remain in methodology details");
}

const TESTS: [string, () => void][] = [
  ["test_presentation_does_not_mutate_the_artifact", test_presentation_does_not_mutate_the_artifact],
  ["test_published_pillars_come_first_canonical_order_preserved", test_published_pillars_come_first_canonical_order_preserved],
  ["test_summary_reads_as_prose_from_the_artifact", test_summary_reads_as_prose_from_the_artifact],
  ["test_summary_handles_nothing_published", test_summary_handles_nothing_published],
  ["test_gaps_lead_uses_product_language_not_threshold_math", test_gaps_lead_uses_product_language_not_threshold_math],
  ["test_strongest_findings_only_from_published_pillars", test_strongest_findings_only_from_published_pillars],
  ["test_strongest_findings_sorted_by_persisted_score", test_strongest_findings_sorted_by_persisted_score],
  ["test_gap_reasons_map_directly_from_availability", test_gap_reasons_map_directly_from_availability],
  ["test_component_has_no_score_ring_or_overall_score", test_component_has_no_score_ring_or_overall_score],
  ["test_component_states_coverage_is_not_performance", test_component_states_coverage_is_not_performance],
  ["test_raw_gate_reasons_only_under_methodology_disclosure", test_raw_gate_reasons_only_under_methodology_disclosure],
  ["test_withheld_pillar_is_a_compact_row_with_native_disclosure", test_withheld_pillar_is_a_compact_row_with_native_disclosure],
  ["test_overview_uses_more_evidence_needed_and_keeps_technical_state_in_details", test_overview_uses_more_evidence_needed_and_keeps_technical_state_in_details],
];

function main(): void {
  console.log("\nEvidence-v1 report presentation tests");
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
