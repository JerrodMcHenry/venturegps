import type { EvidenceV1AnalysisDetail, EvidenceV1Claim, EvidenceV1PillarResult } from "@/types";

import BaseCard from "@/components/ui/BaseCard";

// Task 31 item 12/13 -- the Evidence Engine v1 report. Deliberately does
// NOT reproduce the legacy scorecard (no overall 0-100 score, no letter
// grade) -- Coverage/Confidence/publication status are a different
// concept from a legacy "score" and are never presented as equivalent.
//
// Progressive disclosure via native <details>/<summary> (item 13):
// summary -> pillar -> dimension -> evidence, with zero client-side
// JavaScript required to expand/collapse -- works without JS, keyboard-
// and screen-reader-accessible by default, and avoids a second,
// client-only copy of this page's own state.

function formatPct(value: number | null): string {
  return value == null ? "—" : `${value.toFixed(1)}%`;
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
      <p className="text-sm leading-6 text-text-primary">
        {/* Untrusted, externally-retrieved text -- rendered as plain text
            only, never dangerouslySetInnerHTML, never interpreted as
            markup (item 20's own "untrusted evidence text never
            rendered as HTML"). React escapes this by default. */}
        &ldquo;{claim.excerpt ?? claim.claim_text}&rdquo;
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary">
        <span>{claim.source_publisher}</span>
        <span className="text-text-tertiary">·</span>
        <span className="capitalize">{claim.source_type.replaceAll("_", " ")}</span>
        {claim.published_at ? (
          <>
            <span className="text-text-tertiary">·</span>
            <span>{claim.published_at}</span>
          </>
        ) : null}
        {claim.source_url ? (
          <>
            <span className="text-text-tertiary">·</span>
            {/* A URL is shown for reference only -- it is never implied
                to mean "independently verified" (item 12's own explicit
                instruction); rel/noopener/noreferrer since this points
                to an external, untrusted domain. */}
            <a
              href={claim.source_url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="font-medium text-primary hover:text-primary-hover"
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
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-3 text-sm">
        <span className="font-medium text-text-primary">
          {dimension.dimension.replaceAll("_", " ")}
        </span>
        <span className="flex items-center gap-2">
          {isScored ? (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
              {dimension.score!.toFixed(1)} / 10
            </span>
          ) : (
            <span className="rounded-full bg-surface-subtle px-2 py-0.5 text-xs font-semibold text-text-secondary">
              Unscored
            </span>
          )}
          <span className="text-text-tertiary transition-transform group-open:rotate-90">›</span>
        </span>
      </summary>

      <div className="border-t border-border p-3">
        {/* Unknown must not look like poor performance (item 12's own
            explicit instruction): Unscored is presented as "the source
            material doesn't yet support a claim here," never as a low
            or negative result. */}
        <p className="text-sm leading-6 text-text-secondary">
          {isScored
            ? dimension.rationale
            : `Not yet assessed: ${dimension.rationale || "no admissible evidence is on record for this dimension yet — this is a gap in available information, not a negative finding."}`}
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
  return (
    <BaseCard className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-text-primary">{pillar.pillar}</h2>
          <p className="mt-1 text-sm text-text-secondary">
            {pillar.publishable ? "Published" : "Withheld"} · Coverage {formatPct(pillar.coverage_pct)}
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

      {!pillar.publishable && pillar.withhold_reasons.length > 0 ? (
        <div className="mt-3 rounded-lg bg-surface-subtle p-3 text-sm text-text-secondary">
          <p className="font-medium text-text-primary">Why this pillar is withheld:</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {pillar.withhold_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-text-tertiary">
            This reflects missing or insufficient evidence, not a negative assessment.
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

  return (
    <div className="space-y-6">
      {/* Header (item 12) */}
      <BaseCard variant="glass" className="p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-text-primary">{analysis.company_name}</h1>
            <a
              href={analysis.canonical_website}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="mt-1 inline-block text-sm text-primary hover:text-primary-hover"
            >
              {analysis.canonical_website}
            </a>
          </div>
          <div className="text-right text-xs text-text-tertiary">
            <p>Analyzed {result.as_of}</p>
            <p>Evidence Engine {analysis.methodology_version}</p>
          </div>
        </div>

        {/* Company-level state -- Coverage/Confidence/publication, no
            overall 0-100 score anywhere (item 12's own explicit
            instruction). */}
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-surface-subtle p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Coverage</p>
            <p className="mt-1 text-2xl font-bold text-text-primary">{formatPct(analysis.company_coverage_pct)}</p>
            <p className="mt-1 text-xs text-text-tertiary">Share of this methodology&apos;s dimensions with admissible evidence</p>
          </div>
          <div className="rounded-xl bg-surface-subtle p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Confidence</p>
            <p className="mt-1 text-2xl font-bold text-text-primary">{analysis.company_confidence ?? "—"}</p>
          </div>
          <div className="rounded-xl bg-surface-subtle p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-text-tertiary">Status</p>
            <p className="mt-1 text-2xl font-bold text-text-primary">
              {analysis.company_publishable ? "Publishable" : "Not yet publishable"}
            </p>
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

      {/* Six pillars, each with progressive disclosure into dimensions/evidence */}
      <div className="space-y-4">
        {result.pillar_results.map((pillar) => (
          <PillarSection key={pillar.pillar} pillar={pillar} claims={result.accepted_claims} />
        ))}
      </div>

      {/* Technical provenance -- collapsed by default, always inspectable (item 13) */}
      <BaseCard className="p-6">
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-text-primary">
            All evidence and technical detail ({result.accepted_claims.length} claims, {result.total_claims_in_ledger} total in ledger)
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
