import type { EvidenceV1AnalysisDetail, EvidenceV1Claim, EvidenceV1PillarResult } from "@/types";

import BaseCard from "@/components/ui/BaseCard";

// Task 31/33 -- the evidence-first report. Deliberately does NOT
// reproduce the legacy scorecard (no overall 0-100 score, no letter
// grade) -- Evidence Coverage/Confidence/publication status are a
// different concept from a legacy "score" and are never presented as
// equivalent (item 5's own explicit "do not turn Coverage into a
// large score-like gauge that visually implies quality").
//
// Progressive disclosure via native <details>/<summary>: summary ->
// pillar -> dimension -> evidence, with zero client-side JavaScript
// required to expand/collapse -- works without JS, is keyboard-
// accessible by default (item 14), and avoids a second, client-only
// copy of this page's own state.
//
// Terminology (item 3): "assessment available" / "assessment withheld"
// (never "Published"/"Withheld" jargon to the reader), "information
// unavailable" (never "Unscored" to the reader -- the underlying data
// field name is unchanged, only the DISPLAY label here). No internal
// names (a kind id, a routing status, "evidence_v1") ever reach this
// component's own rendered text.

function formatPct(value: number | null): string {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

// item 8: translate internal source_type enum values into plain,
// user-facing labels rather than a mechanically de-snake-cased string.
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

function humanizeDimensionName(dimension: string): string {
  return dimension.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// A small, always-visible explanatory note rather than a hover-only
// tooltip (item 14: understandable without relying on hover/mouse
// precision; always present for assistive technology, never hidden
// behind an interaction).
function InfoNote({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs leading-5 text-text-tertiary">{children}</p>;
}

function ConfidenceBadge({ confidence }: { confidence: string | null }) {
  const label = confidence ?? "Unknown";
  const tone =
    confidence === "High"
      ? "bg-success/10 text-success"
      : confidence === "Medium"
        ? "bg-warning/10 text-warning"
        : "bg-surface-subtle text-text-secondary";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>
      Confidence: {label}
    </span>
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
        <span className="text-text-tertiary">·</span>
        <span>{sourceTypeLabel(claim.source_type)}</span>
        {claim.published_at ? (
          <>
            <span className="text-text-tertiary">·</span>
            <span>{claim.published_at}</span>
          </>
        ) : null}
        {claim.source_url ? (
          <>
            <span className="text-text-tertiary">·</span>
            {/* A URL is shown for reference only -- never implied to
                mean "independently verified" (item 8's own explicit
                instruction); rel/noopener/noreferrer since this points
                to an external, untrusted domain. aria-label gives the
                link meaningful text on its own (item 14), since
                "View source" alone would be ambiguous out of context
                for a screen-reader user navigating by links. */}
            <a
              href={claim.source_url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              aria-label={`View source: ${claim.source_publisher}`}
              className="font-medium text-primary hover:text-primary-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              View source ↗
            </a>
          </>
        ) : null}
      </div>
    </div>
  );
}

function DimensionRow({ dimension, claims }: { dimension: EvidenceV1PillarResult["dimension_results"][number]; claims: EvidenceV1Claim[] }) {
  const isScored = dimension.score != null;
  const supportingClaims = claims.filter((c) => dimension.supporting_claim_ids.includes(c.claim_id));

  return (
    <details className="group rounded-lg border border-border">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
        {/* min-w-0 + truncate: on a narrow mobile width, a long
            category name (e.g. "Differentiation Claim Corroboration")
            must never push the badge off-screen or force horizontal
            scroll -- it shrinks and truncates instead, since this
            element has no flex-wrap of its own. */}
        <span className="min-w-0 flex-1 truncate font-medium text-text-primary">
          {humanizeDimensionName(dimension.dimension)}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {isScored ? (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
              {dimension.score!.toFixed(1)} / 10
            </span>
          ) : (
            // item 7: never 0/10, never 0%, never red/failure styling for
            // a dimension merely lacking evidence -- same neutral,
            // informational tone as the Confidence badge's own "Unknown"
            // state.
            <span className="rounded-full bg-surface-subtle px-2 py-0.5 text-xs font-semibold text-text-secondary">
              Information unavailable
            </span>
          )}
          <span aria-hidden="true" className="text-text-tertiary transition-transform group-open:rotate-90">›</span>
        </span>
      </summary>

      <div className="border-t border-border p-3">
        {/* Unknown must not look like poor performance: this is framed
            as a gap in available information, never a negative finding. */}
        <p className="text-sm leading-6 text-text-secondary">
          {isScored
            ? dimension.rationale
            : (dimension.rationale
                ? dimension.rationale
                : "Not enough public evidence is available yet to assess this category. This is a gap in available information, not a negative finding.")}
        </p>

        {supportingClaims.length > 0 ? (
          <div className="mt-3 space-y-2">
            {supportingClaims.map((claim) => (
              <EvidenceExcerpt key={claim.claim_id} claim={claim} />
            ))}
          </div>
        ) : null}
      </div>
    </details>
  );
}

function PillarSection({ pillar, claims }: { pillar: EvidenceV1PillarResult; claims: EvidenceV1Claim[] }) {
  const scoredCount = pillar.dimension_results.filter((d) => d.score != null).length;
  const totalCount = pillar.dimension_results.length;

  return (
    <BaseCard className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xl font-bold text-text-primary">{pillar.pillar}</h3>
          <p className="mt-1 text-sm text-text-secondary">
            {pillar.publishable ? "Assessment available" : "Assessment withheld"} · Evidence Coverage{" "}
            {formatPct(pillar.coverage_pct)} · {scoredCount} of {totalCount} categories assessed
          </p>
        </div>
        <div className="flex items-center gap-2">
          {pillar.publishable && pillar.strength != null ? (
            <span className="rounded-full bg-primary/10 px-3 py-1 text-sm font-bold text-primary">
              Strength {pillar.strength.toFixed(1)}
            </span>
          ) : null}
          <ConfidenceBadge confidence={pillar.confidence} />
        </div>
      </div>

      {!pillar.publishable ? (
        <div className="mt-3 rounded-lg bg-surface-subtle p-3 text-sm text-text-secondary">
          <p className="font-medium text-text-primary">Assessment withheld</p>
          <p className="mt-1">
            Insufficient independent evidence was available to evaluate this pillar reliably.
          </p>
          {pillar.withhold_reasons.length > 0 ? (
            <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs text-text-tertiary">
              {pillar.withhold_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
          <p className="mt-2 text-xs text-text-tertiary">
            This reflects missing or insufficient public evidence, not a negative assessment.
          </p>
        </div>
      ) : null}

      <div className="mt-4 space-y-2">
        {pillar.dimension_results.map((dimension) => (
          <DimensionRow key={dimension.dimension} dimension={dimension} claims={claims} />
        ))}
      </div>
    </BaseCard>
  );
}

export default function EvidenceV1Report({ analysis }: { analysis: EvidenceV1AnalysisDetail }) {
  const { result } = analysis;
  const publishedPillars = result.pillar_results.filter((p) => p.publishable).length;
  const withheldPillars = result.pillar_results.length - publishedPillars;

  return (
    <div className="space-y-6">
      {/* Header */}
      <BaseCard variant="glass" className="p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-3xl font-bold text-text-primary">{analysis.company_name}</h1>
            <a
              href={analysis.canonical_website}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="mt-1 inline-block max-w-full truncate text-sm text-primary hover:text-primary-hover"
            >
              {analysis.canonical_website}
            </a>
          </div>
          <div className="text-right text-xs text-text-tertiary">
            <p>Analyzed {result.as_of}</p>
            <p>Evidence-based analysis</p>
          </div>
        </div>

        {/* Plain-English explanation (item 4) -- always visible, ahead
            of the metrics it explains. */}
        <p className="mt-4 max-w-prose text-sm leading-6 text-text-secondary">
          VentureGPS only assesses a category when enough public evidence is available. Missing evidence
          is not treated as poor performance — it means that category is not yet assessed.
        </p>

        {/* Assessment overview -- Evidence Coverage/Confidence/publication
            state, never an overall 0-100 score anywhere on this page
            (item 4/5). */}
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-surface-subtle p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Evidence Coverage</p>
            <p className="mt-1 text-2xl font-bold text-text-primary">{formatPct(analysis.company_coverage_pct)}</p>
            <InfoNote>
              How much of VentureGPS&apos;s methodology could be evaluated from available evidence.
              It is not a performance score.
            </InfoNote>
          </div>
          <div className="rounded-xl bg-surface-subtle p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Confidence</p>
            <p className="mt-1 text-2xl font-bold text-text-primary">{analysis.company_confidence ?? "—"}</p>
            <InfoNote>
              How confident VentureGPS is in the evidence gathered — not a prediction of whether this
              company will succeed.
            </InfoNote>
          </div>
          <div className="rounded-xl bg-surface-subtle p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Pillars assessed</p>
            <p className="mt-1 text-2xl font-bold text-text-primary">
              {publishedPillars} of {result.pillar_results.length}
            </p>
            <InfoNote>{withheldPillars} withheld for insufficient evidence, shown below.</InfoNote>
          </div>
        </div>

        {result.company_withhold_reasons.length > 0 ? (
          <div className="mt-4 rounded-lg bg-surface-subtle p-3 text-sm text-text-secondary">
            <p className="font-medium text-text-primary">Why this analysis is not yet fully publishable:</p>
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              {result.company_withhold_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </BaseCard>

      {/* Six pillars, each with progressive disclosure into categories/evidence */}
      <div className="space-y-4">
        <h2 className="sr-only">Pillar assessments</h2>
        {result.pillar_results.map((pillar) => (
          <PillarSection key={pillar.pillar} pillar={pillar} claims={result.accepted_claims} />
        ))}
      </div>

      {/* How this assessment works (item 9) -- high-level, non-technical,
          collapsed by default. Never describes AI as independently
          deciding scores. */}
      <BaseCard className="p-6">
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
            How this assessment works
          </summary>
          <ol className="mt-3 list-inside list-decimal space-y-1.5 text-sm leading-6 text-text-secondary">
            <li>VentureGPS researches public sources about the company.</li>
            <li>Each claim is tied to the specific source evidence it came from.</li>
            <li>That evidence is checked against a defined set of requirements before it can be used.</li>
            <li>A fixed, documented methodology — not an AI judgment call — evaluates the evidence that qualifies.</li>
            <li>Categories without enough qualifying evidence are withheld rather than guessed at.</li>
          </ol>
        </details>
      </BaseCard>

      {/* All evidence -- collapsed by default, always inspectable */}
      <BaseCard className="p-6">
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
            All evidence ({result.accepted_claims.length} sources reviewed)
          </summary>
          <div className="mt-4 space-y-2">
            {result.accepted_claims.map((claim) => (
              <EvidenceExcerpt key={claim.claim_id} claim={claim} />
            ))}
          </div>
        </details>
      </BaseCard>
    </div>
  );
}
