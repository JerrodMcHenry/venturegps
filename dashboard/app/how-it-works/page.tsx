import type { Metadata } from "next";
import Link from "next/link";

import PageHeader from "@/components/layout/PageHeader";
import BaseCard from "@/components/ui/BaseCard";
import { absoluteUrl } from "@/lib/site.ts";

// Portfolio Release Task 7, Phase 3 -- Build the How VentureGPS Works
// page. Public (no auth.protect() -- this is explanatory content
// anyone, signed in or not, should be able to read before deciding to
// analyze a startup), reusing the same shared visual system every other
// route in this phase's scope already uses (PageHeader's "glow" variant,
// BaseCard's "glass" variant, the accent-to-secondary gradient) rather
// than a one-off design.
//
// Every stage described below is traced directly from the real
// production code, not aspirational copy:
//   1. app/workflows/due_diligence_workflow.py::run_due_diligence()
//   2. app/ai/research_enrichment.py::enrich_research()
//   3. app/ai/analyze_pillar.py::analyze_pillar() (evidence_extraction.py
//      + pillar_scoring.py, one call each, per pillar)
//   4. app/ai/scoring.py (finalize_pillar_score) + app/ai/
//      investment_score.py (calculate_base_score) + app/ai/
//      analyze_pillar.py's apply_deterministic_overrides()/
//      apply_confidence_score_cap()
//   5. app/workflows/sie_assembler.py::assemble_sie_analysis() +
//      StartupHeroV2.tsx/IntelligencePillars.tsx (the report itself)
// See Task 7 Phase 1's own architecture audit for the full trace this
// page's copy is built from.
export function generateMetadata(): Metadata {
  const url = absoluteUrl("/how-it-works");
  const description =
    "How VentureGPS actually works: AI-assisted research, AI-generated pillar assessments, and deterministic scoring -- explained plainly, with what each stage can and can't guarantee.";

  return {
    title: "How VentureGPS Works",
    description,
    alternates: { canonical: url },
    openGraph: { title: "How VentureGPS Works", description, url, type: "website", siteName: "VentureGPS" },
    twitter: { card: "summary_large_image", title: "How VentureGPS Works", description },
  };
}

type Stage = {
  number: string;
  title: string;
  kind: "input" | "probabilistic" | "deterministic" | "output";
  description: string;
  detail: string;
};

const STAGES: Stage[] = [
  {
    number: "1",
    title: "Startup information",
    kind: "input",
    description: "You provide a company website, a pitch deck, a plain-language description, or any combination.",
    detail:
      "This is the one part of the pipeline with no AI involved yet -- it's exactly what you submit, combined into one input for everything below.",
  },
  {
    number: "2",
    title: "AI-assisted research",
    kind: "probabilistic",
    description: "VentureGPS generates targeted search queries, retrieves public information, and synthesizes it into a research brief.",
    detail:
      "A language model writes the search queries and the brief; a real web search actually retrieves the pages. The brief is instructed to separate verified facts from assumptions and to say UNKNOWN rather than invent numbers -- but it is still an AI-written synthesis, not a verified fact-check.",
  },
  {
    number: "3",
    title: "AI-generated assessments",
    kind: "probabilistic",
    description: "Six Intelligence Pillars (Market, Team, Product, Execution, Traction, Financial Health) are each assessed in two steps: evidence extraction, then scoring.",
    detail:
      "For each pillar, one AI call reads your submission plus the research and decides, per dimension, whether it found direct evidence (Observed), an indirect signal (Inferred), or not enough to responsibly assess (Unavailable) -- never guessing a number for a dimension it can't support. A second AI call then judges a 0-10 score for whatever evidence was found.",
  },
  {
    number: "4",
    title: "Deterministic validation and scoring",
    kind: "deterministic",
    description: "Every score is then processed by fixed, non-AI rules -- the same rules, every time, for every analysis.",
    detail:
      "A confidence cap (a Low-confidence finding can't reach a 9 or 10, no matter what the AI judged). Rule-based overrides for a small set of dimensions where structured facts (like a two-point revenue series) exist -- those are computed in plain code, never an AI's number. A weighted average turns dimension scores into a pillar score, and pillar scores into the one overall VentureGPS Score, always excluding (never zeroing out) whatever couldn't be responsibly assessed.",
  },
  {
    number: "5",
    title: "VentureGPS Report",
    kind: "output",
    description: "One VentureGPS Score, six pillar breakdowns, evidence, confidence, strengths, weaknesses, and recommendations.",
    detail:
      "Everything above is what you're actually reading in a report -- including which specific findings come from real evidence, which are AI inferences, and which dimensions simply couldn't be assessed. Nothing in the report is added after the fact that wasn't already computed here.",
  },
];

const STAGE_KIND_LABEL: Record<Stage["kind"], string> = {
  input: "Your input",
  probabilistic: "Probabilistic (AI judgment)",
  deterministic: "Deterministic (fixed rules)",
  output: "Output",
};

const STAGE_KIND_BADGE_CLASS: Record<Stage["kind"], string> = {
  input: "bg-surface-muted text-text-secondary",
  probabilistic: "bg-warning/10 text-warning",
  deterministic: "bg-success/10 text-success",
  output: "bg-primary/10 text-primary",
};

export default function HowItWorksPage() {
  return (
    <>
      <PageHeader
        title="How VentureGPS Works"
        subtitle="The actual production pipeline, stage by stage -- what's an AI judgment, what's a fixed calculation, and what neither one guarantees."
        variant="glow"
      />

      <BaseCard variant="glass" className="p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-text-primary">Probabilistic vs. deterministic, in plain English</h2>
        <div className="mt-4 grid gap-6 sm:grid-cols-2">
          <div>
            <span className="inline-flex items-center rounded-full bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">Probabilistic</span>
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              A language model reads text and makes a judgment call -- what the evidence says, how strong it is, what
              a fair score looks like. The same input usually produces a very similar result, but not a
              mathematically guaranteed identical one, and the judgment itself can be wrong even when the process
              was followed correctly.
            </p>
          </div>
          <div>
            <span className="inline-flex items-center rounded-full bg-success/10 px-3 py-1 text-xs font-semibold text-success">Deterministic</span>
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              Plain code applies a fixed formula to numbers that already exist -- a weighted average, a confidence
              cap, a rule-based override. The exact same inputs always produce the exact same output, every time,
              with no judgment involved at this step.
            </p>
          </div>
        </div>

        <div className="mt-6 rounded-xl border border-warning/20 bg-warning/10 p-4">
          <p className="text-sm font-semibold text-warning">This distinction has a real limit</p>
          <p className="mt-1 text-sm leading-6 text-text-secondary">
            A reproducible calculation only means the <em>math</em> is consistent -- it does not mean the
            AI-generated judgments or the underlying claims about the company are correct. A confidently-stated,
            perfectly-reproducible score can still be wrong if the evidence it was built from was incomplete,
            misleading, or simply mistaken. Always treat VentureGPS as one structured input to your own judgment,
            not a verified fact.
          </p>
        </div>
      </BaseCard>

      {/* Architecture diagram: a vertical flow of the five real stages, each labeled by kind
          (input / probabilistic / deterministic / output) so the probabilistic-vs-deterministic
          split is visible at a glance, not just explained in prose above. */}
      <div className="mt-8 space-y-4" aria-label="VentureGPS pipeline architecture diagram">
        {STAGES.map((stage, index) => (
          <div key={stage.number}>
            <BaseCard variant="glass" className="p-6">
              <div className="flex flex-wrap items-start gap-4">
                <span
                  aria-hidden="true"
                  className="flex size-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent to-secondary text-base font-bold text-white"
                >
                  {stage.number}
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-lg font-semibold text-text-primary">{stage.title}</h3>
                    <span className={["inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", STAGE_KIND_BADGE_CLASS[stage.kind]].join(" ")}>
                      {STAGE_KIND_LABEL[stage.kind]}
                    </span>
                  </div>
                  <p className="mt-1.5 text-base leading-7 text-text-secondary">{stage.description}</p>
                  <p className="mt-2 text-sm leading-6 text-text-muted">{stage.detail}</p>
                </div>
              </div>
            </BaseCard>

            {index < STAGES.length - 1 ? (
              <div aria-hidden="true" className="flex justify-center py-1">
                <span className="text-xl text-text-muted">↓</span>
              </div>
            ) : null}
          </div>
        ))}
      </div>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href="/analyze"
          className="inline-flex min-h-11 items-center justify-center rounded-full bg-gradient-to-r from-accent to-secondary px-6 text-sm font-bold text-white shadow-lg shadow-primary/30 transition-opacity hover:opacity-90"
        >
          Analyze a startup →
        </Link>
        <Link
          href="/#how-it-works"
          className="inline-flex min-h-11 items-center justify-center rounded-full border border-border px-6 text-sm font-semibold text-text-primary transition-colors hover:bg-surface-muted"
        >
          Back to the short version
        </Link>
      </div>
    </>
  );
}
