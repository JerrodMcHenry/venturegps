import Link from "next/link";

// Portfolio Release Task 4 -- Homepage Coherence, Phase 4. A small,
// static explainer -- three steps, no data fetch, no new backend
// endpoint -- so PublicNav's "How It Works" link (an anchor into this
// section's own id, reachable from any page since it always renders
// after the hero on "/") has somewhere real to land, rather than a dead
// link. Deliberately minimal: this is orientation copy, not a second
// homepage redesign -- the cinematic hero above keeps its existing
// visual treatment untouched; only its own headline/CTA text changed
// (see VentureGpsHero.tsx's own comment).
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

        <Link
          href="/analyze"
          className="mt-10 inline-flex min-h-11 items-center justify-center rounded-full bg-primary px-6 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
        >
          Analyze a startup →
        </Link>
      </div>
    </section>
  );
}
