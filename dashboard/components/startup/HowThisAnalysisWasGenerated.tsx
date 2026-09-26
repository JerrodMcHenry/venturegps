import CollapsibleSection from "@/components/ui/CollapsibleSection";
import { SparkleIcon } from "./icons";

import type { SIEAnalysisContext } from "@/types";

// Task 5 -- Unified Visual Design (AI transparency addendum). Every fact
// shown here reads directly from analysis_context (app/models/
// analysis_context.py) -- nothing is invented. Fields added by the SIE
// Scoring Reliability sprint (model_identifier, search_query,
// source_snapshot, scoring_version, etc.) default to an EMPTY string/list
// on the backend for any analysis produced before they existed; this
// component treats "empty" as "not recorded for this analysis" and says
// so plainly, rather than rendering a blank line or fabricating a value.
// See this file's own comment above SOURCE_STEPS for the one thing this
// component deliberately does NOT claim: a per-evidence-item source_type/
// verified distinction the frontend's own Evidence type
// (types/startup.ts, `{ source?, text?, title?, url? }`) does not carry
// end to end -- app/models/evidence.py's richer Evidence model (source_type,
// verified) is a different, not-yet-frontend-facing shape. Documented as a
// known limitation rather than invented here.
type HowThisAnalysisWasGeneratedProps = {
  analysisContext?: SIEAnalysisContext;
};

function isNonEmpty(value: string | undefined): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export default function HowThisAnalysisWasGenerated({
  analysisContext,
}: HowThisAnalysisWasGeneratedProps) {
  const context = analysisContext ?? {};
  const sources = context.source_snapshot?.filter((source) => isNonEmpty(source.url) || isNonEmpty(source.title)) ?? [];

  return (
    <CollapsibleSection
      title="How this analysis was generated"
      icon={<SparkleIcon className="h-3.5 w-3.5 text-primary" />}
    >
      {/* The three-stage explanation itself -- always shown, since it
          describes the pipeline every analysis goes through, not a
          per-analysis recorded fact. */}
      <ol className="space-y-3">
        <Stage
          number={1}
          title="AI-assisted research"
          description="A web search gathers public information about the company to supplement whatever was submitted (a pitch deck, website, or description)."
        />
        <Stage
          number={2}
          title="AI-generated pillar analysis"
          description="A language model reads the submitted material plus that research and writes an assessment for each of the six pillars (market, team, product, execution, traction, financial health) -- citing evidence, and explicitly marking a dimension as unavailable when there isn't enough to responsibly score it."
        />
        <Stage
          number={3}
          title="Deterministic scoring"
          description="The Startup Intelligence Score itself is not chosen by the AI -- it's a fixed, weighted-average formula applied to the pillar scores above. The same six pillar scores always produce the same overall score."
        />
      </ol>

      {/* Per-analysis recorded facts -- shown only when actually
          recorded; each row says so explicitly when it isn't, rather
          than being omitted (an omission reads as "nothing to know"
          rather than "not recorded for this older analysis"). */}
      <dl className="grid gap-x-6 gap-y-2 border-t border-border pt-3 text-sm sm:grid-cols-2">
        <Fact label="Methodology version" value={context.methodology_version} />
        <Fact label="AI model used for pillar analysis" value={context.model_identifier} />
        <Fact label="Research search query" value={context.search_query} />
        <Fact label="Analyzed" value={formatTimestamp(context.analyzed_at)} />
      </dl>

      {sources.length > 0 ? (
        <div className="border-t border-border pt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Public sources consulted during research
          </p>
          <ul className="mt-1.5 space-y-1">
            {sources.map((source, index) => (
              <li key={index} className="text-sm">
                {isNonEmpty(source.url) ? (
                  <a href={source.url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                    {source.title && source.title.trim().length > 0 ? source.title : source.url}
                  </a>
                ) : (
                  <span className="text-text-secondary">{source.title}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Plain-language glossary for the evidence/confidence labels shown
          throughout the report -- "wherever the existing data supports
          those distinctions" (Subscore.evidence_status,
          Subscore.confidence), not new backend fields. */}
      <div className="border-t border-border pt-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">What the labels on this report mean</p>
        <ul className="mt-1.5 space-y-1.5 text-sm leading-6 text-text-secondary">
          <li><span className="font-medium text-text-primary">Observed</span> — the analysis found direct evidence for this.</li>
          <li><span className="font-medium text-text-primary">Inferred</span> — the AI drew a reasonable conclusion from indirect signals, without direct evidence.</li>
          <li><span className="font-medium text-text-primary">Unavailable</span> — there wasn&rsquo;t enough information to responsibly score this; it is excluded from the score, never guessed.</li>
          <li><span className="font-medium text-text-primary">Confidence (Low / Medium / High)</span> — how much the AI itself trusts its own read of the available evidence for that dimension.</li>
        </ul>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          One distinction this report does not yet make: whether a piece of evidence came directly
          from the company (e.g. a pitch deck claim) versus an independent public source. Every
          quoted evidence item above is shown as-is, regardless of which it was.
        </p>
      </div>
    </CollapsibleSection>
  );
}

function Stage({ number, title, description }: { number: number; title: string; description: string }) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden="true"
        className="flex size-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent to-secondary text-xs font-bold text-white"
      >
        {number}
      </span>
      <div>
        <p className="text-sm font-semibold text-text-primary">{title}</p>
        <p className="mt-0.5 text-sm leading-6 text-text-secondary">{description}</p>
      </div>
    </li>
  );
}

function Fact({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">{label}</dt>
      <dd className="text-text-secondary">
        {isNonEmpty(value) ? value : <span className="italic text-text-muted">Not recorded for this analysis</span>}
      </dd>
    </div>
  );
}

function formatTimestamp(value: string | undefined): string | undefined {
  if (!isNonEmpty(value)) {
    return undefined;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return undefined;
  }

  return date.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
