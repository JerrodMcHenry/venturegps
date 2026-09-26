// Task 5 -- Unified Visual Design and Homepage Simplification (+ AI
// transparency addendum). Same "read the file as source text" technique
// this directory's other tests already use for files that import
// next/navigation/@clerk/nextjs.
//
// Run with:
//   node tests/visualSystem.test.ts
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

// --- Shared primitives, not route-specific duplication ----------------------

function test_base_card_glass_variant_is_additive(): void {
  const source = readSource("components/ui/BaseCard.tsx");
  expect(/"default" \| "raised" \| "subtle" \| "glass"/.test(source), "BaseCardVariant must add \"glass\" without removing the existing three");
  expect(/glass:\s*\n?\s*"/.test(source), "A \"glass\" entry must exist in VARIANT_CLASSES");
  // The existing three variants' classes must be byte-for-byte unchanged
  // -- every existing BaseCard call site across the app must keep
  // rendering identically.
  expect(source.includes('default: "rounded-2xl border border-border bg-surface shadow-sm"'), "The existing \"default\" variant class string must be unchanged");
  expect(source.includes('raised: "rounded-2xl border border-border bg-surface-raised shadow-md"'), "The existing \"raised\" variant class string must be unchanged");
  expect(source.includes('subtle: "rounded-2xl border border-border bg-surface-subtle"'), "The existing \"subtle\" variant class string must be unchanged");
}

function test_button_gradient_variant_is_additive(): void {
  const source = readSource("components/ui/Button.tsx");
  expect(/"primary" \| "secondary" \| "subtle" \| "destructive" \| "gradient"/.test(source), "ButtonVariant must add \"gradient\" without removing the existing four");
  expect(/from-accent to-secondary/.test(source), "The gradient variant must reuse the existing accent/secondary tokens, not new colors");
}

function test_page_header_glow_variant_defaults_to_unchanged_behavior(): void {
  const source = readSource("components/layout/PageHeader.tsx");
  expect(/variant\?:\s*"default"\s*\|\s*"glow"/.test(source), "PageHeader must add an opt-in `variant` prop");
  expect(/variant = "default"/.test(source), "PageHeader's variant must default to \"default\" -- every existing call site (no `variant` prop) must render unchanged");
}

function test_collapsible_section_exists_and_is_reused(): void {
  expect(
    /export default function CollapsibleSection/.test(readSource("components/ui/CollapsibleSection.tsx")),
    "components/ui/CollapsibleSection.tsx must export a CollapsibleSection component"
  );

  // Reused by BOTH the pre-existing Technical Details AND the new AI-
  // transparency section -- not a second hand-rolled collapsible each.
  const pillarWorkspaceSource = readSource("components/startup/PillarWorkspace.tsx");
  expect(/import CollapsibleSection from "@\/components\/ui\/CollapsibleSection"/.test(pillarWorkspaceSource), "PillarWorkspace's TechnicalDetails must reuse the shared CollapsibleSection");

  const howGeneratedSource = readSource("components/startup/HowThisAnalysisWasGenerated.tsx");
  expect(/import CollapsibleSection from "@\/components\/ui\/CollapsibleSection"/.test(howGeneratedSource), "HowThisAnalysisWasGenerated must reuse the shared CollapsibleSection, not a second implementation");
}

function test_reduced_motion_is_respected_in_new_transitions(): void {
  const source = readSource("components/ui/CollapsibleSection.tsx");
  expect(/motion-reduce:transition-none/.test(source), "CollapsibleSection's chevron rotation must be gated behind motion-reduce:transition-none");
}

// --- Task 5 #4: shared visual system applied to the four named routes ------

function test_analyze_page_uses_the_glow_header_and_gradient_cta(): void {
  const source = readSource("app/analyze/AnalyzeStartupForm.tsx");
  expect((source.match(/variant="glow"/g) ?? []).length >= 4, "Every PageHeader render branch on the Analyze page must use variant=\"glow\"");
  expect(/<Button type="submit" variant="gradient">/.test(source), "The Analyze page's one prominent submit CTA must use Button's shared gradient variant");
}

function test_my_analyses_page_uses_the_glow_header(): void {
  const source = readSource("app/my-analyses/MyAnalysesView.tsx");
  expect(/variant="glow"/.test(source), "My Analyses' PageHeader must use variant=\"glow\"");
}

function test_saved_page_uses_the_glow_header(): void {
  const source = readSource("app/saved/SavedStartupsView.tsx");
  expect(/variant="glow"/.test(source), "Saved's PageHeader must use variant=\"glow\"");
}

function test_startup_report_hero_uses_the_glass_card_and_gradient_name(): void {
  const source = readSource("components/startup/StartupHeroV2.tsx");
  expect(/<BaseCard variant="glass"/.test(source), "StartupHeroV2 must use BaseCard's glass variant");
  const h1Match = source.match(/<h1 className="([^"]*)">/);
  expect(h1Match !== null, "StartupHeroV2 must render an <h1> with a className");
  const h1Classes = h1Match?.[1] ?? "";
  for (const fragment of ["from-accent", "via-primary", "to-secondary", "bg-clip-text", "text-transparent"]) {
    expect(h1Classes.includes(fragment), `The company name's <h1> must include ${fragment} (the shared gradient-text treatment)`);
  }
}

// --- AI transparency addendum -----------------------------------------------

function test_how_this_analysis_was_generated_exists_and_is_wired_in(): void {
  const componentSource = readSource("components/startup/HowThisAnalysisWasGenerated.tsx");
  expect(/export default function HowThisAnalysisWasGenerated/.test(componentSource), "HowThisAnalysisWasGenerated must exist");

  const pageSource = readSource("app/startup/[id]/page.tsx");
  expect(/import HowThisAnalysisWasGenerated from "@\/components\/startup\/HowThisAnalysisWasGenerated"/.test(pageSource), "The startup report page must import HowThisAnalysisWasGenerated");
  expect(/<HowThisAnalysisWasGenerated analysisContext={methodology\.analysis_context}\s*\/>/.test(pageSource), "The startup report page must render it with the real analysis_context");
}

function test_three_stage_explanation_matches_the_real_pipeline(): void {
  // The three stages must name the real distinction the task asks for --
  // AI-assisted research vs AI-generated pillar analyses vs deterministic
  // methodology-based scoring -- not vaguer marketing copy.
  const source = readSource("components/startup/HowThisAnalysisWasGenerated.tsx");
  expect(/AI-assisted research/.test(source), "Must name the AI-assisted-research stage explicitly");
  expect(/AI-generated pillar analysis/.test(source), "Must name the AI-generated-pillar-analysis stage explicitly");
  expect(/Deterministic scoring/.test(source), "Must name the deterministic-scoring stage explicitly");
}

function test_does_not_invent_unavailable_provenance(): void {
  // The task's own explicit constraint: never invent citations,
  // verification status, confidence measurements, or provenance
  // metadata the backend doesn't actually expose to the frontend.
  // types/startup.ts's own Evidence type has no source_type/verified
  // field (unlike the richer, not-yet-frontend-facing app/models/
  // evidence.py) -- this component must not claim that distinction.
  // Checks rendered JSX text content, not the file's own explanatory
  // comments -- this component's comments legitimately name "verified"/
  // "source_type" to document why they're deliberately absent from the
  // rendered output (same convention this codebase already uses
  // elsewhere for explaining an absence).
  const source = readSource("components/startup/HowThisAnalysisWasGenerated.tsx");
  const jsxOnly = source
    .split("\n")
    .filter((line) => !line.trim().startsWith("//") && !line.trim().startsWith("*"))
    .join("\n");
  expect(!/verified/i.test(jsxOnly), "Must not claim a per-evidence \"verified\" status the frontend's Evidence type doesn't carry");
  expect(!/source_type/.test(jsxOnly), "Must not reference source_type -- not part of the frontend's Evidence contract");
  // Must explicitly document the one real limitation instead of silently
  // omitting it.
  expect(/does not yet make/.test(source), "Must explicitly document the company-claim-vs-independent-source limitation, not silently omit it");
}

function test_honest_when_provenance_fields_are_not_recorded(): void {
  const source = readSource("components/startup/HowThisAnalysisWasGenerated.tsx");
  expect(/Not recorded for this analysis/.test(source), "Must show an honest \"not recorded\" fallback for older analyses missing these fields, never a blank or fabricated value");
}

function test_analysis_context_type_mirrors_the_real_backend_model(): void {
  const source = readSource("types/startup.ts");
  expect(/export type SIEAnalysisContext/.test(source), "A real SIEAnalysisContext type must exist (replacing analysis_context?: unknown)");
  for (const field of ["methodology_version", "model_identifier", "search_query", "source_snapshot", "analyzed_at"]) {
    expect(source.includes(`${field}?:`), `SIEAnalysisContext must declare ${field}`);
  }
  expect(/analysis_context\?:\s*SIEAnalysisContext/.test(source), "SIEMethodologyAnalysis.analysis_context must be typed as SIEAnalysisContext, not unknown");
}

function test_homepage_ai_explainer_is_integrated_not_a_new_section(): void {
  // The addendum's own explicit instruction: integrated with the
  // existing How It Works section, not a new section that makes the
  // homepage longer -- collapsed by default, inside the same <section>.
  const source = readSource("components/home/ventureGps/HowItWorksSection.tsx");
  expect(/How VentureGPS uses AI/i.test(source), "The How It Works section must explain how VentureGPS uses AI");
  expect(/useState\(false\)/.test(source), "The AI explanation must be collapsed by default, not always-expanded page-length content");
  // Must be inside THIS section (one <section> element), not a sibling
  // section appended after it.
  const sectionCount = (source.match(/<section\b/g) ?? []).length;
  expect(sectionCount === 1, "The AI explanation must live inside the one How It Works <section>, not a second section");
}

const TESTS: [string, () => void][] = [
  ["test_base_card_glass_variant_is_additive", test_base_card_glass_variant_is_additive],
  ["test_button_gradient_variant_is_additive", test_button_gradient_variant_is_additive],
  ["test_page_header_glow_variant_defaults_to_unchanged_behavior", test_page_header_glow_variant_defaults_to_unchanged_behavior],
  ["test_collapsible_section_exists_and_is_reused", test_collapsible_section_exists_and_is_reused],
  ["test_reduced_motion_is_respected_in_new_transitions", test_reduced_motion_is_respected_in_new_transitions],
  ["test_analyze_page_uses_the_glow_header_and_gradient_cta", test_analyze_page_uses_the_glow_header_and_gradient_cta],
  ["test_my_analyses_page_uses_the_glow_header", test_my_analyses_page_uses_the_glow_header],
  ["test_saved_page_uses_the_glow_header", test_saved_page_uses_the_glow_header],
  ["test_startup_report_hero_uses_the_glass_card_and_gradient_name", test_startup_report_hero_uses_the_glass_card_and_gradient_name],
  ["test_how_this_analysis_was_generated_exists_and_is_wired_in", test_how_this_analysis_was_generated_exists_and_is_wired_in],
  ["test_three_stage_explanation_matches_the_real_pipeline", test_three_stage_explanation_matches_the_real_pipeline],
  ["test_does_not_invent_unavailable_provenance", test_does_not_invent_unavailable_provenance],
  ["test_honest_when_provenance_fields_are_not_recorded", test_honest_when_provenance_fields_are_not_recorded],
  ["test_analysis_context_type_mirrors_the_real_backend_model", test_analysis_context_type_mirrors_the_real_backend_model],
  ["test_homepage_ai_explainer_is_integrated_not_a_new_section", test_homepage_ai_explainer_is_integrated_not_a_new_section],
];

function main(): void {
  console.log("\nUnified Visual Design + AI Transparency tests");
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
