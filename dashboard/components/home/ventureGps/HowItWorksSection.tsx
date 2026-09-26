"use client";

import { useState } from "react";
import Link from "next/link";

// Portfolio Release Task 4 -- Homepage Coherence, Phase 4. A small,
// static explainer -- three steps, no data fetch, no new backend
// endpoint -- so PublicNav's "How It Works" link (an anchor into this
// section's own id, reachable from any page since it always renders
// after the hero on "/") has somewhere real to land, rather than a dead
// link.
//
// Task 5 -- Unified Visual Design (AI transparency addendum): the "How
// VentureGPS Uses AI" explanation lives INSIDE this same section, as a
// collapsed-by-default disclosure right below the three steps -- per
// this task's own explicit instruction ("integrated with the existing
// How It Works section rather than making the homepage longer"), not a
// second full section stretching the page. Same three-stage framing
// (research / AI pillar analysis / deterministic scoring) as the
// startup report's own "How this analysis was generated"
// (components/startup/HowThisAnalysisWasGenerated.tsx) -- this is the
// plain-language, no-specific-analysis version of the identical, real
// pipeline; the two are deliberately consistent rather than two
// different stories about how the product works.
const STEPS = [
  {
    number: "1",
    title: "Describe the startup",
    description: "Paste a pitch deck, a website, or a few paragraphs describing the company.",
  },
  {
    number: "2",
    title: "Get an evidence-backed analysis",
    description:
      "The Startup Intelligence Engine evaluates market, team, product, execution, traction and financial health -- citing evidence for every score, never a guess.",
  },
  {
    number: "3",
    title: "Act on a defensible score",
    description: "A clear Startup Intelligence Score you and others can revisit any time from My Analyses.",
  },
];

export default function HowItWorksSection() {
  const [aiExpanded, setAiExpanded] = useState(false);

  return (
    <section id="how-it-works" aria-labelledby="how-it-works-heading" className="bg-background py-16 sm:py-20">
      <div className="mx-auto w-full max-w-5xl px-4 sm:px-8">
        <h2 id="how-it-works-heading" className="text-2xl font-bold tracking-tight text-text-primary sm:text-3xl">
          How It Works
        </h2>
        <p className="mt-2 max-w-2xl text-base leading-7 text-text-secondary">
          Evidence-backed startup analysis, not a guess.
        </p>

        <div className="mt-10 grid gap-8 sm:grid-cols-3">
          {STEPS.map((step) => (
            <div key={step.number}>
              <span className="flex size-10 items-center justify-center rounded-full bg-primary-soft text-base font-bold text-primary">
                {step.number}
              </span>
              <h3 className="mt-4 text-lg font-semibold text-text-primary">{step.title}</h3>
              <p className="mt-2 text-sm leading-6 text-text-secondary">{step.description}</p>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-wrap items-center gap-4">
          <Link
            href="/analyze"
            className="inline-flex min-h-11 items-center justify-center rounded-full bg-gradient-to-r from-accent to-secondary px-6 text-sm font-bold text-white shadow-lg shadow-primary/30 transition-opacity hover:opacity-90"
          >
            Analyze a startup →
          </Link>

          <button
            type="button"
            onClick={() => setAiExpanded((previous) => !previous)}
            aria-expanded={aiExpanded}
            aria-controls="how-ai-is-used"
            className="text-sm font-semibold text-primary hover:underline"
          >
            {aiExpanded ? "Hide how VentureGPS uses AI ▴" : "How VentureGPS uses AI ▾"}
          </button>
        </div>

        {aiExpanded ? (
          <div
            id="how-ai-is-used"
            className="mt-6 rounded-2xl border border-primary/15 bg-surface/70 p-6 shadow-lg shadow-primary/5 backdrop-blur-xl supports-[backdrop-filter]:bg-surface/60 sm:p-8"
          >
            <h3 className="text-lg font-semibold text-text-primary">How VentureGPS uses AI</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
              Three distinct stages, not one black box -- and only one of them is deterministic.
            </p>

            <ol className="mt-6 grid gap-6 sm:grid-cols-3">
              <AiStage
                number={1}
                title="AI-assisted research"
                description="A web search gathers public information to supplement what you submit."
              />
              <AiStage
                number={2}
                title="AI-generated pillar analysis"
                description="A language model reads that material and writes an assessment per pillar -- and explicitly marks a dimension unavailable rather than guessing when there isn't enough evidence."
              />
              <AiStage
                number={3}
                title="Deterministic scoring"
                description="Your overall score is a fixed, weighted-average formula applied to the pillar scores -- not a number the AI itself chooses."
              />
            </ol>

            <p className="mt-6 text-sm leading-6 text-text-secondary">
              Every report shows its own evidence, confidence levels, and anything that couldn&rsquo;t be
              scored -- see &ldquo;How this analysis was generated&rdquo; on any startup&rsquo;s report.
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function AiStage({ number, title, description }: { number: number; title: string; description: string }) {
  return (
    <li>
      <span
        aria-hidden="true"
        className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-accent to-secondary text-xs font-bold text-white"
      >
        {number}
      </span>
      <p className="mt-3 text-sm font-semibold text-text-primary">{title}</p>
      <p className="mt-1 text-sm leading-6 text-text-secondary">{description}</p>
    </li>
  );
}
