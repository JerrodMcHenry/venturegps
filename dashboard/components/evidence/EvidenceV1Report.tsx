import type { ReactNode } from "react";

import type { EvidenceV1AnalysisDetail, EvidenceV1Claim, EvidenceV1DimensionResult, EvidenceV1PillarResult } from "@/types";

import BaseCard from "@/components/ui/BaseCard";
import { CONFIDENCE_BADGE_CLASSES } from "@/components/startup/pillarMeta";
import { DocumentIcon, InfoIcon, LayersIcon, SparkleIcon } from "@/components/startup/icons";
import {
  buildReportPresentation,
  humanizeClassificationLabel,
  humanizeDimensionName,
  isScored,
  pillarAnchorId,
  pillarGap,
} from "@/lib/evidenceV1Presentation";

// Task 31/33 + final UX correction -- the evidence-first report, laid out
// insight-first in three layers:
//   1. Executive understanding -- company identity, areas assessed, a
//      deterministic plain-English summary (lib/evidenceV1Presentation.ts,
//      built only from the persisted artifact -- no LLM call).
//   2. Pillar assessments -- published pillars first and prominent;
//      withheld pillars compact, inside Information Gaps.
//   3. Evidence & methodology -- excerpts, sources, gating reasons, raw
//      coverage, all behind native <details> disclosure.
// Presentation only: every number is read from the artifact unchanged.
//
// Borrowed from the legacy report (StartupHeroV2/PillarWorkspace): the
// gradient company-name treatment, meta chips, icon-led section headings,
// confidence badge colors, a pillar-by-pillar overview. Deliberately NOT
// borrowed: the SPSRing / any overall score, letter grade or circular
// gauge -- this methodology has no company-level quality score, and
// Evidence Coverage must never read as one (no overall 0-100 score, no
// letter grade; Coverage is never turned into a large score-like gauge).
//
// Progressive disclosure is native <details>/<summary>: zero client JS,
// keyboard-accessible by default, works without JavaScript.
//
// Terminology: "More evidence needed" is the primary label for a withheld
// pillar; the technical "assessment available" / "assessment withheld"
// state appears inside methodology details. "Information unavailable"
// (never "Unscored") for a category, and
// "information unavailable" (never "Unscored") -- no internal names (a
// kind id, a routing status, "evidence_v1") reach the primary reading
// path; exact engine gating strings appear only under "Methodology
// details".

// User-facing label for a withheld pillar in the overview and Information
// Gaps rows. Display only -- the canonical state remains `publishable:
// false` ("Assessment withheld" in methodology details).
const NEEDS_EVIDENCE_LABEL = "More evidence needed";

const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";

function formatPct(value: number | null): string {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

// as_of is a calendar date ("2026-09-30"); parsed by parts so it never
// shifts a day through a UTC-midnight Date in a US timezone.
function formatAsOf(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) return isoDate;
  const [, y, m, d] = match;
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m) - 1];
  return month ? `${month} ${Number(d)}, ${y}` : isoDate;
}

// Translate internal source_type enum values into plain, user-facing
// labels rather than a mechanically de-snake-cased string.
const SOURCE_TYPE_LABELS: Record<string, string> = {
  independent_reporting: "News coverage",
  company_disclosure: "Company's own statement",
  product_documentation: "Product documentation",
  public_filing: "Public filing",
  aggregator_or_directory: "Industry directory",
  community_commentary: "Public commentary",
  other: "Other source",
};

function sourceTypeLabel(sourceType: string): string {
  return SOURCE_TYPE_LABELS[sourceType] ?? sourceType.replaceAll("_", " ");
}

function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={[
        "inline-flex items-center rounded-full px-3 py-1 text-xs font-medium",
        className ?? "border border-border text-text-secondary",
      ].join(" ")}
    >
      {children}
    </span>
  );
}

function ConfidenceChip({ confidence, prefix = "" }: { confidence: EvidenceV1PillarResult["confidence"] | null; prefix?: string }) {
  if (!confidence) return null;
  return <Chip className={CONFIDENCE_BADGE_CLASSES[confidence]}>{prefix}{confidence} confidence</Chip>;
}

function SectionHeading({ icon, children, id }: { icon: ReactNode; children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="flex items-center gap-2 text-xl font-semibold text-text-primary">
      {icon}
      {children}
    </h2>
  );
}

function Disclosure({ summary, children, className = "" }: { summary: ReactNode; children: ReactNode; className?: string }) {
  return (
    <details className={["group", className].join(" ")}>
      <summary
        className={`inline-flex cursor-pointer list-none items-center gap-1.5 rounded text-sm font-semibold text-primary hover:text-primary-hover [&::-webkit-details-marker]:hidden ${FOCUS_RING}`}
      >
        <span aria-hidden="true" className="inline-block transition-transform group-open:rotate-90">›</span>
        {summary}
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

// A per-dimension 0-10 bar. Only ever drawn for a dimension the engine
// actually scored -- never for a pillar total or the company.
function ScoreBar({ score, label }: { score: number; label: string }) {
  return (
    <div
      role="img"
      aria-label={label}
      className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-primary to-secondary"
        style={{ width: `${Math.max(0, Math.min(10, score)) * 10}%` }}
      />
    </div>
  );
}

function EvidenceExcerpt({ claim }: { claim: EvidenceV1Claim }) {
  return (
    <div className="rounded-lg border border-border bg-surface-subtle p-4">
      <p className="text-sm leading-6 break-words text-text-primary">
        {/* Untrusted, externally-retrieved text -- rendered as plain text
            only, never dangerouslySetInnerHTML, never interpreted as
            markup. React escapes this by default. */}
        &ldquo;{claim.excerpt ?? claim.claim_text}&rdquo;
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary">
        <span>{claim.source_publisher}</span>
        <span className="text-text-muted">·</span>
        <span>{sourceTypeLabel(claim.source_type)}</span>
        {claim.published_at ? (
          <>
            <span className="text-text-muted">·</span>
            <span>{claim.published_at}</span>
          </>
        ) : null}
        {claim.source_url ? (
          <>
            <span className="text-text-muted">·</span>
            {/* A URL is shown for reference only -- never implied to mean
                "independently verified"; rel hardened since this points
                to an external, untrusted domain. aria-label gives the link
                meaningful text on its own for screen-reader link lists. */}
            <a
              href={claim.source_url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              aria-label={`View source: ${claim.source_publisher}`}
              className={`font-medium text-primary hover:text-primary-hover ${FOCUS_RING}`}
            >
              View source ↗
            </a>
          </>
        ) : null}
      </div>
    </div>
  );
}

// Layer 3 detail for one dimension: the engine's own rationale and weight,
// verbatim. Kept out of the primary reading path.
function DimensionMethodology({ dimension }: { dimension: EvidenceV1DimensionResult }) {
  return (
    <p className="text-xs leading-5 text-text-muted">
      <span className="font-medium text-text-secondary">{humanizeDimensionName(dimension.dimension)}</span>
      {" · "}weight {Math.round(dimension.weight * 100)}%
      {dimension.rationale ? <> · {dimension.rationale}</> : null}
    </p>
  );
}

function ScoredDimension({ dimension, claims }: { dimension: EvidenceV1DimensionResult; claims: EvidenceV1Claim[] }) {
  const supporting = claims.filter((c) => dimension.supporting_claim_ids.includes(c.claim_id));
  const label = humanizeClassificationLabel(dimension.classification_label);
  const name = humanizeDimensionName(dimension.dimension);
  const score = dimension.score!;

  return (
    <li className="rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="min-w-0 font-semibold text-text-primary">{name}</p>
        <p className="shrink-0 text-sm font-semibold text-text-primary">
          {score.toFixed(1)} <span className="font-normal text-text-muted">/ 10</span>
        </p>
      </div>
      <div className="mt-2">
        <ScoreBar score={score} label={`${name}: ${score.toFixed(1)} out of 10`} />
      </div>
      {label ? (
        <p className="mt-2 text-sm text-text-secondary">
          Finding: <span className="font-medium text-text-primary">{label}</span>
        </p>
      ) : null}

      <Disclosure
        className="mt-3"
        summary={supporting.length > 0 ? `Evidence (${supporting.length} ${supporting.length === 1 ? "source" : "sources"})` : "Details"}
      >
        <div className="space-y-2">
          {supporting.map((claim) => (
            <EvidenceExcerpt key={claim.claim_id} claim={claim} />
          ))}
          <DimensionMethodology dimension={dimension} />
        </div>
      </Disclosure>
    </li>
  );
}

// The plain-language information gaps for one pillar, grouped by the
// persisted availability reason (lib/evidenceV1Presentation.ts).
function GapList({ pillar }: { pillar: EvidenceV1PillarResult }) {
  const { reasons } = pillarGap(pillar);
  if (reasons.length === 0) return null;
  return (
    <ul className="space-y-1.5 text-sm leading-6 text-text-secondary">
      {reasons.map(({ reason, dimensions }) => (
        <li key={reason} className="flex gap-2.5">
          <span aria-hidden="true" className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-text-muted" />
          <span>
            <span className="font-medium text-text-primary">{dimensions.join(", ")}</span>
            {" — "}Information unavailable: {reason}.
          </span>
        </li>
      ))}
    </ul>
  );
}

function PillarMethodologyDetails({ pillar }: { pillar: EvidenceV1PillarResult }) {
  const scoredCount = pillar.dimension_results.filter(isScored).length;
  return (
    <Disclosure summary="Methodology details">
      <div className="space-y-2 rounded-lg bg-surface-subtle p-3">
        <p className="text-xs leading-5 text-text-secondary">
          <span className="font-medium">{pillar.publishable ? "Assessment available" : "Assessment withheld"}</span>
          {" · "}Evidence Coverage {formatPct(pillar.coverage_pct)} · {scoredCount} of {pillar.dimension_results.length}{" "}
          categories assessed · {pillar.confidence} confidence in the evidence gathered
        </p>
        {pillar.withhold_reasons.length > 0 ? (
          <div>
            <p className="text-xs font-medium text-text-secondary">Publication gate result</p>
            <ul className="mt-1 list-inside list-disc space-y-0.5 font-mono text-xs text-text-muted">
              {pillar.withhold_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="space-y-1">
          {pillar.dimension_results.map((d) => (
            <DimensionMethodology key={d.dimension} dimension={d} />
          ))}
        </div>
        <p className="text-xs text-text-muted">
          Evidence Coverage describes how much of the methodology could be evaluated. It is not a company
          performance score.
        </p>
      </div>
    </Disclosure>
  );
}

function PublishedPillar({ pillar, claims }: { pillar: EvidenceV1PillarResult; claims: EvidenceV1Claim[] }) {
  const scored = pillar.dimension_results.filter(isScored);
  const unscored = pillar.dimension_results.filter((d) => !isScored(d));

  return (
    <BaseCard id={pillarAnchorId(pillar.pillar)} className="relative scroll-mt-24 overflow-hidden p-6 sm:p-7">
      <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-accent via-primary to-secondary opacity-70" />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-2xl font-bold text-text-primary">{pillar.pillar}</h3>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Chip className="bg-success/10 text-success">Assessment available</Chip>
            <ConfidenceChip confidence={pillar.confidence} />
          </div>
        </div>
        {pillar.strength != null ? (
          <div className="text-right">
            <p className="text-xs font-semibold uppercase tracking-wider text-text-muted">Strength</p>
            <p className="text-3xl font-bold text-text-primary">
              {pillar.strength.toFixed(1)}
              <span className="text-base font-medium text-text-muted"> / 10</span>
            </p>
          </div>
        ) : null}
      </div>

      <p className="mt-3 text-xs text-text-muted">
        Strength is this area&apos;s own result. VentureGPS does not combine areas into an overall company score.
      </p>

      {scored.length > 0 ? (
        <ul className="mt-5 grid gap-3 sm:grid-cols-2">
          {scored.map((d) => (
            <ScoredDimension key={d.dimension} dimension={d} claims={claims} />
          ))}
        </ul>
      ) : null}

      {unscored.length > 0 ? (
        <div className="mt-4 rounded-lg bg-surface-subtle p-3">
          <p className="text-sm font-medium text-text-primary">Not yet assessed within this area</p>
          <div className="mt-1.5">
            <GapList pillar={pillar} />
          </div>
        </div>
      ) : null}

      <div className="mt-4">
        <PillarMethodologyDetails pillar={pillar} />
      </div>
    </BaseCard>
  );
}

// One compact, expandable row per withheld pillar. The Information Gaps
// lead paragraph already explains WHY these areas are unassessed, so the
// row itself carries only the name and "More evidence needed" -- the
// specific gaps, any scored categories and the exact gate detail (where
// the technical "Assessment withheld" state is named) only on expansion.
// The pillar's publishable/withheld state itself is unchanged.
function WithheldPillar({ pillar, claims }: { pillar: EvidenceV1PillarResult; claims: EvidenceV1Claim[] }) {
  const scored = pillar.dimension_results.filter(isScored);

  return (
    <li id={pillarAnchorId(pillar.pillar)} className="scroll-mt-24">
      <details className="group">
        <summary
          className={`flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-4 py-3 hover:bg-surface-muted [&::-webkit-details-marker]:hidden ${FOCUS_RING}`}
        >
          <span className="min-w-0 font-semibold text-text-primary">{pillar.pillar}</span>
          <span className="flex shrink-0 items-center gap-2">
            <Chip>{NEEDS_EVIDENCE_LABEL}</Chip>
            <span aria-hidden="true" className="text-text-muted transition-transform group-open:rotate-90">›</span>
          </span>
        </summary>

        <div className="space-y-3 px-4 pb-4">
          <GapList pillar={pillar} />
          {scored.length > 0 ? (
            <div>
              <p className="text-sm font-medium text-text-primary">
                Categories with qualifying evidence (not enough on their own to assess this area)
              </p>
              <ul className="mt-2 grid gap-3 sm:grid-cols-2">
                {scored.map((d) => (
                  <ScoredDimension key={d.dimension} dimension={d} claims={claims} />
                ))}
              </ul>
            </div>
          ) : null}
          <p className="text-xs text-text-muted">
            This reflects missing or insufficient public evidence, not a negative assessment.
          </p>
          <PillarMethodologyDetails pillar={pillar} />
        </div>
      </details>
    </li>
  );
}

export default function EvidenceV1Report({ analysis }: { analysis: EvidenceV1AnalysisDetail }) {
  const { result } = analysis;
  const view = buildReportPresentation(analysis);
  const claims = result.accepted_claims;
  const showStage = Boolean(analysis.stage) && analysis.stage.toLowerCase() !== "undetermined";

  return (
    <div className="mx-auto max-w-4xl space-y-10">
      {/* ---- Layer 1: executive understanding ---- */}
      <BaseCard variant="glass" className="relative overflow-hidden p-6 sm:p-8">
        <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-accent via-primary to-secondary" />

        <p className="text-xs font-semibold uppercase tracking-wider text-text-muted">Evidence-based report</p>
        <h1 className="mt-1 bg-gradient-to-r from-accent via-primary to-secondary bg-clip-text text-4xl font-bold break-words text-transparent">
          {analysis.company_name}
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <a
            href={analysis.canonical_website}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className={`inline-flex max-w-full items-center truncate rounded-full border border-border px-3 py-1 text-xs font-medium text-primary hover:text-primary-hover ${FOCUS_RING}`}
          >
            {analysis.canonical_website.replace(/^https?:\/\//, "")} ↗
          </a>
          {showStage ? <Chip>{analysis.stage} stage</Chip> : null}
          <Chip>Analyzed {formatAsOf(result.as_of)}</Chip>
        </div>

        {/* Areas assessed: a COUNT of areas the methodology could publish,
            in canonical order -- not a quality measure. */}
        <section aria-labelledby="assessment-overview" className="mt-7">
          <h2 id="assessment-overview" className="text-xs font-semibold uppercase tracking-wider text-text-muted">
            Assessment overview
          </h2>
          <p className="mt-1.5 font-semibold text-text-primary">
            <span className="text-3xl font-bold">{view.published.length}</span>
            <span className="text-lg text-text-secondary"> of {view.canonical.length} areas assessed</span>
          </p>
          <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {view.canonical.map((pillar) => (
              <li key={pillar.pillar}>
                <a
                  href={`#${pillarAnchorId(pillar.pillar)}`}
                  className={[
                    "block h-full rounded-xl px-3 py-2.5 transition",
                    FOCUS_RING,
                    pillar.publishable
                      ? "border border-primary/30 bg-primary/10 hover:bg-primary/15"
                      : "border border-dashed border-border-strong hover:bg-surface-muted",
                  ].join(" ")}
                >
                  <span className="block text-sm font-semibold text-text-primary">{pillar.pillar}</span>
                  <span className={`mt-0.5 block text-xs ${pillar.publishable ? "text-primary" : "text-text-muted"}`}>
                    {pillar.publishable
                      ? pillar.strength != null
                        ? `Strength ${pillar.strength.toFixed(1)} / 10`
                        : "Assessed"
                      : NEEDS_EVIDENCE_LABEL}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-7 border-t border-border pt-6">
          <SectionHeading icon={<SparkleIcon className="h-4 w-4 text-primary" />}>Summary</SectionHeading>
          <div className="mt-3 max-w-prose space-y-3 text-base leading-7 text-text-secondary">
            {view.summary.map((sentence) => (
              <p key={sentence}>{sentence}</p>
            ))}
          </div>
          <p className="mt-2 text-xs text-text-muted">
            Composed directly from this report&apos;s published results — not an AI-written narrative.
          </p>
        </div>

        {/* Transparency metadata, deliberately small. */}
        <div className="mt-6 rounded-lg bg-surface-subtle px-4 py-3 text-xs leading-5 text-text-secondary">
          <p>
            <span className="font-medium text-text-primary">Evidence Coverage {formatPct(analysis.company_coverage_pct)}</span>
            {analysis.company_confidence ? (
              <>
                {" · "}
                <span className="font-medium text-text-primary">Evidence Confidence {analysis.company_confidence}</span>
              </>
            ) : null}
          </p>
          <p className="mt-1 text-text-muted">
            Evidence Coverage describes how much of the methodology could be evaluated. It is not a company
            performance score. Evidence Confidence describes the evidence gathered — not a prediction of whether
            this company will succeed.
          </p>
        </div>
      </BaseCard>

      {/* ---- Layer 2: pillar assessments (assessed areas first) ---- */}
      {view.published.length > 0 ? (
        <section aria-labelledby="assessed-areas" className="space-y-4">
          <SectionHeading id="assessed-areas" icon={<LayersIcon className="h-4 w-4 text-primary" />}>
            Assessed {view.published.length === 1 ? "area" : "areas"}
          </SectionHeading>
          {view.published.map((pillar) => (
            <PublishedPillar key={pillar.pillar} pillar={pillar} claims={claims} />
          ))}
        </section>
      ) : null}

      {view.withheld.length > 0 ? (
        <section aria-labelledby="information-gaps" className="space-y-4">
          <SectionHeading id="information-gaps" icon={<InfoIcon className="h-4 w-4 text-text-muted" />}>
            Information gaps
          </SectionHeading>
          <p className="max-w-prose text-base leading-7 text-text-secondary">{view.gapsLead}</p>
          <p className="max-w-prose text-sm text-text-muted">
            Missing evidence is not negative evidence — these areas are unknown, not weak.
          </p>
          <ul className="divide-y divide-border rounded-xl border border-dashed border-border-strong bg-surface">
            {view.withheld.map((pillar) => (
              <WithheldPillar key={pillar.pillar} pillar={pillar} claims={claims} />
            ))}
          </ul>
          {result.company_withhold_reasons.length > 0 ? (
            <Disclosure summary="Methodology details for the full report">
              <div className="rounded-lg bg-surface-subtle p-3 text-xs text-text-secondary">
                <p>
                  The report as a whole is marked not yet fully publishable. Exact publication gate results:
                </p>
                <ul className="mt-1 list-inside list-disc space-y-0.5 font-mono text-text-muted">
                  {result.company_withhold_reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            </Disclosure>
          ) : null}
        </section>
      ) : null}

      {/* ---- Layer 3: evidence & methodology ---- */}
      <section aria-labelledby="evidence-methodology" className="space-y-4">
        <SectionHeading id="evidence-methodology" icon={<DocumentIcon className="h-4 w-4 text-text-muted" />}>
          Evidence &amp; methodology
        </SectionHeading>

        <BaseCard className="p-5">
          <details className="group">
            <summary className={`flex cursor-pointer list-none items-center justify-between gap-3 rounded text-sm font-semibold text-text-primary [&::-webkit-details-marker]:hidden ${FOCUS_RING}`}>
              All evidence ({claims.length} {claims.length === 1 ? "source" : "sources"} reviewed)
              <span aria-hidden="true" className="text-text-muted transition-transform group-open:rotate-90">›</span>
            </summary>
            <div className="mt-4 space-y-2">
              {claims.map((claim) => (
                <EvidenceExcerpt key={claim.claim_id} claim={claim} />
              ))}
            </div>
          </details>
        </BaseCard>

        {/* High-level, non-technical. Never describes AI as
            independently deciding scores. */}
        <BaseCard className="p-5">
          <details className="group">
            <summary className={`flex cursor-pointer list-none items-center justify-between gap-3 rounded text-sm font-semibold text-text-primary [&::-webkit-details-marker]:hidden ${FOCUS_RING}`}>
              How this assessment works
              <span aria-hidden="true" className="text-text-muted transition-transform group-open:rotate-90">›</span>
            </summary>
            <ol className="mt-3 list-inside list-decimal space-y-1.5 text-sm leading-6 text-text-secondary">
              <li>VentureGPS researches public sources about the company.</li>
              <li>Each claim is tied to the specific source evidence it came from.</li>
              <li>That evidence is checked against a defined set of requirements before it can be used.</li>
              <li>A fixed, documented methodology — not an AI judgment call — evaluates the evidence that qualifies.</li>
              <li>
                Areas without enough qualifying evidence are withheld rather than guessed at. Missing evidence is
                not a negative finding.
              </li>
            </ol>
          </details>
        </BaseCard>
      </section>
    </div>
  );
}
