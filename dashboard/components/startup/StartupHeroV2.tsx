import type { ReactNode } from "react";

import { SPSRing } from "@/components/sps";
import BaseCard from "@/components/ui/BaseCard";
import ClaimStartupButton from "./ClaimStartupButton";
import SaveStartupButton from "./SaveStartupButton";
import SPSV3ScoreSection from "./SPSV3ScoreSection";

import { CONFIDENCE_BADGE_CLASSES, PILLARS } from "./pillarMeta";
import { AlertIcon, SparkleIcon } from "./icons";

import type { ConfidenceLevel, SIEMethodologyAnalysis } from "@/types";

type StartupHeroV2Props = {
  methodology: SIEMethodologyAnalysis;
  createdAt: string;
  // Saved Startups (Watchlist Phase 1): the canonical Startup FK -- see
  // StartupProfileResponse's own comment. null for the rare historical
  // row that predates the write path, in which case the Save control is
  // omitted entirely rather than rendered against an id that doesn't
  // resolve to anything.
  startupId?: number | null;
};

const ANALYSIS_TYPE_LABELS: Record<string, string> = {
  public: "Public Analysis",
  pitch_deck: "Pitch Deck Analysis",
  founder: "Founder Analysis",
  investor: "Investor Analysis",
  data_room: "Data Room Analysis",
};

// analysis_context is intentionally typed `unknown` on the frontend (same
// reason as startup_scorecard below) — read defensively, no shape asserted.
function getAnalysisType(analysisContext: unknown): string | null {
  if (
    typeof analysisContext === "object" &&
    analysisContext !== null &&
    "analysis_type" in analysisContext
  ) {
    const value = (analysisContext as { analysis_type?: unknown }).analysis_type;

    if (typeof value === "string" && value.trim().length > 0) {
      return (
        ANALYSIS_TYPE_LABELS[value] ??
        value
          .split("_")
          .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
          .join(" ")
      );
    }
  }

  return null;
}

// Same defensive-read pattern as getAnalysisType above -- analysis_context
// is typed `unknown` on the frontend, so this asserts nothing about its
// shape beyond checking for the one field it needs. Exported: Founder
// Workspace (Phase 7.2) reuses this exact derivation rather than
// duplicating it, so the two surfaces can never disagree about which
// methodology version produced a given analysis.
export function getMethodologyVersion(analysisContext: unknown): string | null {
  if (
    typeof analysisContext === "object" &&
    analysisContext !== null &&
    "methodology_version" in analysisContext
  ) {
    const value = (analysisContext as { methodology_version?: unknown })
      .methodology_version;

    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
  }

  return null;
}

// Exported for the same reason as getMethodologyVersion above -- reused
// by Founder Workspace (Phase 7.2).
export function formatAnalysisDate(isoDate: string): string | null {
  const date = new Date(isoDate);

  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// Derived from the six real, already-scored pillar confidences (not a
// separate field — `confidence_score` on the methodology model is never
// populated by the backend, so treating it as real data would mean
// displaying a number that's always 0). Ties resolve toward the more
// conservative (lower) confidence level.
// Exported for the same reason as getMethodologyVersion above -- reused
// by Founder Workspace (Phase 7.2).
export function getOverallConfidence(methodology: SIEMethodologyAnalysis): ConfidenceLevel {
  const counts: Record<ConfidenceLevel, number> = { Low: 0, Medium: 0, High: 0 };

  for (const pillar of PILLARS) {
    counts[methodology[pillar.key].confidence] += 1;
  }

  let best: ConfidenceLevel = "Low";

  for (const level of ["Low", "Medium", "High"] as const) {
    if (counts[level] > counts[best]) {
      best = level;
    }
  }

  return best;
}

// startup_scorecard is intentionally typed `unknown` on the frontend (its
// shape isn't part of the canonical contract yet), so this reads it
// defensively rather than asserting a shape onto it.
function getRecommendation(startupScorecard: unknown): string | null {
  if (
    typeof startupScorecard === "object" &&
    startupScorecard !== null &&
    "recommendation" in startupScorecard
  ) {
    const value = (startupScorecard as { recommendation?: unknown }).recommendation;

    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
  }

  return null;
}

export default function StartupHeroV2({
  methodology,
  createdAt,
  startupId,
}: StartupHeroV2Props) {
  const overallConfidence = getOverallConfidence(methodology);
  const recommendation = getRecommendation(methodology.startup_scorecard);
  const analysisType = getAnalysisType(methodology.analysis_context);
  const analysisDate = formatAnalysisDate(createdAt);

  // Phase 31C-A -- Global Founder UX Acceptance, Part 1/6: this used to
  // also include "Methodology v2.1-spec-2026-08-29" (the raw internal
  // spec-version string, live-discovered on both this public profile and
  // Founder Workspace) -- exactly the kind of implementation detail
  // Part 1's "do not expose unnecessary system terminology" targets. A
  // founder/investor has no use for that string; the date it was
  // analyzed is the actually meaningful fact, kept below.
  // getMethodologyVersion() itself is untouched (still exported, still
  // computed the same way) in case a future internal-only surface needs
  // it -- this is a display-only removal, not a methodology change.
  const metaLineParts = [
    analysisType,
    analysisDate ? `Analyzed ${analysisDate}` : null,
  ].filter((part): part is string => Boolean(part));

  // Partial Structural Coverage (SIE Methodology v2, Part 9 item 6): a
  // purely additive, display-only signal that one or more whole pillars
  // had no scoreable evidence at all. Never touches the SPS shown above --
  // shown only when the backend actually flagged it, never inferred.
  // structural_coverage is absent/null on analyses stored before this
  // field existed, so the banner correctly never appears for those.
  const structuralCoverage = methodology.structural_coverage;
  const showPartialCoverageWarning = Boolean(
    structuralCoverage?.partial_structural_coverage
  );

  const { company_stage, industry, business_model, funding_stage } = methodology.context;

  // Company stage and funding stage frequently describe the same thing
  // (e.g. both "Series A") — don't show the same value twice.
  const showFundingStage =
    Boolean(funding_stage) &&
    funding_stage.trim().toLowerCase() !== company_stage.trim().toLowerCase();

  // Phase 10.11, Part 4/15: industry and business_model sometimes land on
  // the exact same extracted value (e.g. both "SaaS") -- shown as two
  // adjacent identical chips, that reads as a duplicate/glitch rather
  // than two distinct facts. Same "don't repeat a value" discipline as
  // showFundingStage above.
  const showBusinessModel =
    Boolean(business_model) &&
    business_model.trim().toLowerCase() !== industry.trim().toLowerCase();

  return (
    <BaseCard variant="glass" className="p-8">
      <div className="grid gap-10 lg:grid-cols-[320px_1fr] lg:items-center">
        <div className="flex justify-center">
          {/* Phase 10.9, Part 14: sps_v3 is additive and absent on every
              analysis produced while the backend's V3 feature flag is
              off (the default) -- that is the ONLY case handled below by
              the unchanged V2.1 ring, so today's production behavior is
              byte-for-byte identical to before this phase. */}
          {methodology.sps_v3 ? (
            <SPSV3ScoreSection sps={methodology.sps_v3} />
          ) : (
            <SPSRing
              score={methodology.startup_intelligence_score}
              confidence={overallConfidence}
              size="xl"
            />
          )}
        </div>

        <div>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <h1 className="bg-gradient-to-r from-accent via-primary to-secondary bg-clip-text text-4xl font-bold text-transparent">
              {methodology.context.company_name}
            </h1>

            {startupId != null ? (
              <div className="flex flex-col items-end gap-2">
                <ClaimStartupButton startupId={startupId} />
                <SaveStartupButton startupId={startupId} />
              </div>
            ) : null}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {company_stage ? <MetaChip>{company_stage}</MetaChip> : null}
            {showFundingStage ? <MetaChip>{funding_stage}</MetaChip> : null}
            {industry ? <MetaChip>{industry}</MetaChip> : null}
            {showBusinessModel ? <MetaChip>{business_model}</MetaChip> : null}

            {recommendation ? (
              <MetaChip className="bg-primary/10 text-primary">
                {recommendation}
              </MetaChip>
            ) : null}

            <MetaChip className={CONFIDENCE_BADGE_CLASSES[overallConfidence]}>
              {overallConfidence} confidence
            </MetaChip>
          </div>

          {metaLineParts.length > 0 ? (
            <p className="mt-2 text-xs text-text-muted">
              {metaLineParts.join(" · ")}
            </p>
          ) : null}

          {showPartialCoverageWarning ? (
            <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-warning/20 bg-warning/10 px-4 py-3 text-base">
              <AlertIcon className="mt-0.5 h-4 w-4 shrink-0 text-warning" />

              <div>
                <p className="font-medium text-warning">
                  Partial structural coverage
                </p>

                <p className="mt-1 leading-7 text-text-secondary">
                  {structuralCoverage?.pillars_unavailable_entirely &&
                  structuralCoverage.pillars_unavailable_entirely.length > 0
                    ? `No scoreable evidence was found for: ${structuralCoverage.pillars_unavailable_entirely.join(", ")}. `
                    : ""}
                  The Startup Power Score above reflects only the pillars
                  that could be responsibly scored -- it is not penalized
                  for the missing ones.
                </p>
              </div>
            </div>
          ) : null}

          <div className="mt-6 border-t border-border pt-6">
            <h2 className="flex items-center gap-1.5 text-xl font-semibold text-text-primary">
              <SparkleIcon className="h-4 w-4 text-primary" />
              Executive Coaching Summary
            </h2>

            <p className="mt-3 max-w-prose text-[17px] leading-8 text-text-secondary">
              {methodology.executive_coaching_summary}
            </p>
          </div>
        </div>
      </div>
    </BaseCard>
  );
}

function MetaChip({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={[
        "rounded-full px-3 py-1 text-xs font-medium",
        className ?? "border border-border text-text-secondary",
      ].join(" ")}
    >
      {children}
    </span>
  );
}
