"use client";

import { useState } from "react";
import type { ReactNode } from "react";

import { SPSRing } from "@/components/sps";
import BaseCard from "@/components/ui/BaseCard";
import CollapsibleSection from "@/components/ui/CollapsibleSection";

import { CONFIDENCE_BADGE_CLASSES } from "./pillarMeta";
import {
  AlertIcon,
  ArrowIcon,
  CheckIcon,
  DocumentIcon,
  GaugeIcon,
  LayersIcon,
} from "./icons";

import type {
  ConfidenceLevel,
  Evidence,
  PillarAnalysis,
  Subscore,
} from "@/types";

type PillarWorkspaceProps = {
  label: string;
  pillar: PillarAnalysis;
};

const EVIDENCE_STATUS_BADGE_CLASSES: Record<string, string> = {
  Observed: "bg-success/10 text-success",
  Inferred: "bg-warning/10 text-warning",
  Unavailable: "border border-border text-text-muted",
};

const SECTION_HEADING_CLASSES =
  "text-xs font-semibold uppercase tracking-wider text-text-secondary";

function formatWeight(weight: number): string {
  return `${Math.round(weight * 100)}%`;
}

export default function PillarWorkspace({
  label,
  pillar,
}: PillarWorkspaceProps) {
  const score = pillar.score;
  const breakdown = pillar.score_breakdown;
  const subscores = breakdown.subscores ?? [];
  const evidenceCoverage = breakdown.evidence_coverage ?? 0;

  return (
    <BaseCard className="p-6 lg:p-7">
      {/* Overall assessment — compact header: ring, title, score, confidence only. */}
      <div className="flex items-center gap-3 border-b border-border pb-3">
        {score !== null ? (
          <SPSRing
            score={score * 10}
            size="xs"
            showDetails={false}
            ariaLabel={`${label} pillar score: ${score.toFixed(1)} out of 10`}
          />
        ) : (
          <div
            role="img"
            aria-label="Score not yet available"
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-2 border-dashed border-border"
          >
            <span className="text-xs font-medium text-text-muted">
              N/A
            </span>
          </div>
        )}

        <div className="min-w-0 flex-1">
          <h3 className="truncate text-xl font-bold leading-tight text-text-primary">
            {label}
          </h3>

          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-semibold text-text-primary">
              {score !== null
                ? `Pillar Score ${score.toFixed(1)} / 10`
                : "Pillar Score — No score yet"}
            </span>

            <span aria-hidden="true" className="text-text-muted">
              ·
            </span>

            <span
              className={[
                "rounded-full px-2 py-0.5 text-xs font-medium",
                CONFIDENCE_BADGE_CLASSES[pillar.confidence],
              ].join(" ")}
            >
              {pillar.confidence} confidence
            </span>
          </div>
        </div>
      </div>

      <div className="mt-6 space-y-9">
        <Section title="Summary">
          <SummaryText summary={pillar.summary} />
        </Section>

        <div className="grid gap-6 sm:grid-cols-2">
          <Section title="Key Strengths" icon={<CheckIcon className="h-3.5 w-3.5 text-success" />}>
            <CappedList
              items={pillar.strengths}
              emptyLabel="None noted yet."
              dotClassName="bg-success"
            />
          </Section>

          <Section title="Key Weaknesses" icon={<AlertIcon className="h-3.5 w-3.5 text-danger" />}>
            <CappedList
              items={pillar.weaknesses}
              emptyLabel="None noted yet."
              dotClassName="bg-danger"
            />
          </Section>
        </div>

        <Section title="Recommendations" icon={<ArrowIcon className="h-3.5 w-3.5 text-primary" />}>
          <RecommendationsList items={pillar.recommendations} />
        </Section>

        <Section title="Evidence" icon={<DocumentIcon className="h-3.5 w-3.5 text-text-muted" />}>
          {/* Portfolio Release Task 7, Phase 3 -- Improve Evidence
              Transparency. Traced end to end: an evidence item CAN carry
              a real source URL (EvidenceList below already renders it as
              a clickable link when present -- see isEvidenceObject()),
              but the evidence-extraction prompt (app/ai/
              evidence_extraction.py) only ever asks for quoted/
              paraphrased text, never a per-quote source URL, so in
              practice every item here is an unlinked quote today. Stated
              plainly rather than silently -- the real research source
              URLs this analysis used are one section below ("How this
              analysis was generated"), just not yet tied to any specific
              quote. This is a known gap, not a fabricated link. */}
          <p className="mb-2 text-sm text-text-secondary">
            Direct quotes or paraphrases from the submitted material and research. Individual quotes
            aren&rsquo;t yet linked to a specific source — see &ldquo;How this analysis was
            generated&rdquo; below for the public sources this analysis consulted.
          </p>
          <EvidenceList items={pillar.evidence} />
        </Section>

        <Section title="Subscores" icon={<LayersIcon className="h-3.5 w-3.5 text-text-muted" />}>
          {subscores.length > 0 ? (
            <SubscoreTable subscores={subscores} />
          ) : (
            <p className="text-sm text-text-secondary">Not enough evidence.</p>
          )}
        </Section>

        <TechnicalDetails
          scoringSummary={breakdown.scoring_summary}
          evidenceCoverage={evidenceCoverage}
        />
      </div>
    </BaseCard>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section>
      <div className="flex items-center gap-1.5 border-b border-border pb-1.5">
        {icon}
        <h4 className={SECTION_HEADING_CLASSES}>{title}</h4>
      </div>
      <div className="mt-2.5">{children}</div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Summary — first ~250 characters, full text always preserved and one click
// away. Skips the affordance entirely when the summary is already short OR
// when truncating wouldn't actually hide a meaningful amount of content
// (e.g. a 260-character summary shouldn't force a click to reveal 10 more
// characters).
// ---------------------------------------------------------------------------

const SUMMARY_PREVIEW_CHARS = 250;
const SUMMARY_MIN_HIDDEN_CHARS = 80;

function getSummaryPreview(summary: string): string | null {
  if (summary.length <= SUMMARY_PREVIEW_CHARS) {
    return null;
  }

  const truncated = summary.slice(0, SUMMARY_PREVIEW_CHARS);
  const lastSpace = truncated.lastIndexOf(" ");
  const preview = lastSpace > 40 ? truncated.slice(0, lastSpace) : truncated;

  const hiddenChars = summary.length - preview.length;

  if (hiddenChars < SUMMARY_MIN_HIDDEN_CHARS) {
    return null;
  }

  return preview;
}

function SummaryText({ summary }: { summary: string }) {
  const [expanded, setExpanded] = useState(false);

  if (!summary) {
    return <p className="text-sm text-text-secondary">Not enough evidence.</p>;
  }

  const preview = getSummaryPreview(summary);

  if (preview === null) {
    return (
      <p className="max-w-prose text-[17px] leading-8 text-text-secondary">
        {summary}
      </p>
    );
  }

  if (expanded) {
    return (
      <div>
        <p className="max-w-prose text-[17px] leading-8 text-text-secondary">
          {summary}
        </p>
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="mt-1.5 text-sm font-semibold text-primary hover:underline"
        >
          Show less
        </button>
      </div>
    );
  }

  return (
    <div>
      <p className="max-w-prose text-[17px] leading-8 text-text-secondary">{preview}…</p>
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="mt-1.5 text-sm font-semibold text-primary hover:underline"
      >
        Read full summary
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Strengths / Weaknesses — capped at 3, inline expand for the rest.
// ---------------------------------------------------------------------------

function CappedList({
  items,
  emptyLabel,
  dotClassName,
  maxVisible = 3,
}: {
  items: string[];
  emptyLabel: string;
  dotClassName: string;
  maxVisible?: number;
}) {
  const [expanded, setExpanded] = useState(false);

  if (items.length === 0) {
    return <p className="text-sm text-text-secondary">{emptyLabel}</p>;
  }

  const visibleItems = expanded ? items : items.slice(0, maxVisible);
  const remaining = items.length - visibleItems.length;

  return (
    <div>
      <ul className="space-y-1.5">
        {visibleItems.map((item, index) => (
          <li key={index} className="flex gap-2.5 text-base leading-6 text-text-secondary">
            <span
              aria-hidden="true"
              className={["mt-2 h-1.5 w-1.5 shrink-0 rounded-full", dotClassName].join(" ")}
            />
            <span>{item}</span>
          </li>
        ))}
      </ul>

      {remaining > 0 ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-1.5 text-sm font-semibold text-primary hover:underline"
        >
          +{remaining} more
        </button>
      ) : expanded && items.length > maxVisible ? (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="mt-1.5 text-sm font-semibold text-text-secondary hover:underline"
        >
          Show less
        </button>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recommendations — stronger, actionable visual treatment. Same data as
// before, just not rendered as plain bullet text. Capped at 3 with inline
// expansion, matching Strengths/Weaknesses/Evidence.
// ---------------------------------------------------------------------------

const RECOMMENDATIONS_MAX_VISIBLE = 3;

function RecommendationsList({ items }: { items: string[] }) {
  const [expanded, setExpanded] = useState(false);

  if (items.length === 0) {
    return <p className="text-sm text-text-secondary">No recommendations yet.</p>;
  }

  const visibleItems = expanded
    ? items
    : items.slice(0, RECOMMENDATIONS_MAX_VISIBLE);
  const remaining = items.length - visibleItems.length;

  return (
    <div>
      <ul className="space-y-1.5">
        {visibleItems.map((item, index) => (
          <li
            key={index}
            className="flex items-start gap-2.5 rounded-lg bg-primary/5 px-3.5 py-2.5 text-base text-text-primary"
          >
            <span aria-hidden="true" className="mt-0.5 shrink-0 text-primary">
              →
            </span>
            <span className="max-w-prose leading-6">{item}</span>
          </li>
        ))}
      </ul>

      {remaining > 0 ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-1.5 text-sm font-semibold text-primary hover:underline"
        >
          +{remaining} more
        </button>
      ) : expanded && items.length > RECOMMENDATIONS_MAX_VISIBLE ? (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="mt-1.5 text-sm font-semibold text-text-secondary hover:underline"
        >
          Show less
        </button>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evidence — top 3, progressive disclosure for the rest. Kept visually quiet
// (small padding, muted card) so it doesn't dominate the page.
// ---------------------------------------------------------------------------

function isEvidenceObject(item: Evidence | string): item is Evidence {
  return typeof item === "object" && item !== null;
}

function EvidenceList({ items }: { items: Array<Evidence | string> }) {
  const [expanded, setExpanded] = useState(false);
  const visibleCount = 3;

  if (items.length === 0) {
    return <p className="text-sm text-text-secondary">Not enough evidence.</p>;
  }

  const visibleItems = expanded ? items : items.slice(0, visibleCount);
  const remaining = items.length - visibleItems.length;

  return (
    <div>
      <ul className="space-y-1.5">
        {visibleItems.map((item, index) => (
          <li
            key={index}
            className="rounded-md border border-border bg-surface-muted px-3 py-2 text-base text-text-secondary"
          >
            <div className="max-w-prose">
              {isEvidenceObject(item) ? (
                <>
                  {item.title ? (
                    <p className="font-medium text-text-primary">{item.title}</p>
                  ) : null}

                  {item.text ? <p className="mt-0.5">{item.text}</p> : null}

                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-0.5 inline-block text-xs font-medium text-primary hover:underline"
                    >
                      {item.source ?? item.url}
                    </a>
                  ) : item.source ? (
                    <p className="mt-0.5 text-xs text-text-muted">{item.source}</p>
                  ) : null}

                  {!item.title && !item.text && !item.url && !item.source ? (
                    <p className="text-text-muted">No details provided.</p>
                  ) : null}
                </>
              ) : (
                <p>{item}</p>
              )}
            </div>
          </li>
        ))}
      </ul>

      {remaining > 0 ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-1.5 text-sm font-semibold text-primary hover:underline"
        >
          Show {remaining} more evidence
        </button>
      ) : null}

      {expanded && items.length > visibleCount ? (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="mt-1.5 ml-4 text-sm font-semibold text-text-secondary hover:underline"
        >
          Show less
        </button>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subscores — column-aligned table. Collapsed rows show only name, score,
// weight, and evidence status; everything else expands.
// ---------------------------------------------------------------------------

const SUBSCORE_ROW_GRID =
  "grid grid-cols-[minmax(0,1fr)_2.5rem_2.75rem_5.5rem_1rem] items-center gap-3";

function SubscoreTable({ subscores }: { subscores: Subscore[] }) {
  return (
    <div className="space-y-1.5">
      <div className={[SUBSCORE_ROW_GRID, "px-3 text-xs font-semibold uppercase tracking-wide text-text-muted"].join(" ")}>
        <span>Dimension</span>
        <span className="text-right">Score</span>
        <span className="text-right">Weight</span>
        <span className="text-center">Status</span>
        <span />
      </div>

      <div className="space-y-1.5">
        {subscores.map((subscore) => (
          <SubscoreRow key={subscore.name} subscore={subscore} />
        ))}
      </div>
    </div>
  );
}

function MiniList({ heading, items }: { heading: string; items?: string[] }) {
  if (!items || items.length === 0) {
    return null;
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
        {heading}
      </p>

      <ul className="mt-1 space-y-1">
        {items.map((item, index) => (
          <li key={index} className="text-sm text-text-secondary">
            • {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SubscoreRow({ subscore }: { subscore: Subscore }) {
  const [expanded, setExpanded] = useState(false);

  const hasDetails =
    Boolean(subscore.rationale) ||
    (subscore.evidence?.length ?? 0) > 0 ||
    (subscore.recommendations?.length ?? 0) > 0 ||
    (subscore.missing_information?.length ?? 0) > 0;

  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setExpanded((previous) => !previous)}
        disabled={!hasDetails}
        aria-expanded={expanded}
        className={[SUBSCORE_ROW_GRID, "w-full px-3 py-2 text-left disabled:cursor-default"].join(" ")}
      >
        <span className="truncate text-[15px] font-medium text-text-primary">
          {subscore.name}
        </span>

        <span className="text-right text-[15px] font-semibold tabular-nums text-text-primary">
          {subscore.score !== null ? subscore.score.toFixed(1) : "—"}
        </span>

        <span className="text-right text-xs tabular-nums text-text-muted">
          {formatWeight(subscore.weight)}
        </span>

        <span
          className={[
            "justify-self-center rounded-full px-2 py-0.5 text-center text-xs font-medium",
            (subscore.evidence_status &&
              EVIDENCE_STATUS_BADGE_CLASSES[subscore.evidence_status]) ??
              "border border-border text-text-muted",
          ].join(" ")}
        >
          {subscore.evidence_status ?? "—"}
        </span>

        <span
          aria-hidden="true"
          className={[
            "justify-self-end text-text-muted transition-transform duration-200",
            expanded ? "rotate-90" : "",
          ].join(" ")}
        >
          {hasDetails ? "▸" : ""}
        </span>
      </button>

      {expanded && hasDetails ? (
        <div className="space-y-3 border-t border-border px-3 py-3">
          {subscore.confidence ? (
            <p className="text-xs text-text-muted">
              Confidence:{" "}
              <span
                className={[
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  CONFIDENCE_BADGE_CLASSES[subscore.confidence as ConfidenceLevel],
                ].join(" ")}
              >
                {subscore.confidence}
              </span>
            </p>
          ) : null}

          {subscore.rationale ? (
            <p className="max-w-prose text-base leading-7 text-text-secondary">
              {subscore.rationale}
            </p>
          ) : (
            <p className="text-sm text-text-secondary">No rationale provided.</p>
          )}

          <MiniList heading="Evidence" items={subscore.evidence} />
          <MiniList heading="Recommendations" items={subscore.recommendations} />
          <MiniList
            heading="Missing information"
            items={subscore.missing_information}
          />
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Technical Details — scoring methodology text + evidence coverage. Lower
// priority than the analysis above it, so it's grouped, visually quiet, and
// collapsed by default to cut scroll length.
// ---------------------------------------------------------------------------

function TechnicalDetails({
  scoringSummary,
  evidenceCoverage,
}: {
  scoringSummary?: string;
  evidenceCoverage: number;
}) {
  return (
    <CollapsibleSection title="Technical Details">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
          <GaugeIcon className="h-3.5 w-3.5" />
          Scoring summary
        </p>

        {scoringSummary ? (
          <p className="mt-1.5 max-w-prose text-base leading-7 text-text-secondary">
            {scoringSummary}
          </p>
        ) : (
          <p className="mt-1.5 text-sm text-text-secondary">Not enough evidence.</p>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between text-xs text-text-muted">
          <span>Evidence coverage</span>
          <span className="font-medium text-text-secondary">
            {evidenceCoverage}%
          </span>
        </div>

        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface">
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-500 motion-reduce:transition-none"
            style={{ width: `${evidenceCoverage}%` }}
          />
        </div>
      </div>
    </CollapsibleSection>
  );
}
