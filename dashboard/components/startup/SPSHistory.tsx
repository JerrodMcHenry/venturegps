"use client";

import { useId, useState } from "react";

import BaseCard from "@/components/ui/BaseCard";

import type { SPSHistoryPoint } from "@/types";

type SPSHistoryProps = {
  history: SPSHistoryPoint[];
};

const CHART_WIDTH = 640;
const CHART_HEIGHT = 200;
const PADDING_X = 32;
const PADDING_TOP = 20;
const PADDING_BOTTOM = 28;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

// Portfolio Release Task 6 -- Diagnose the Report / Standardize
// Terminology. This component used to take an `isLegacyLabel` prop,
// switching its own labels to "V2.1 Score (legacy)"/"V2.1 Score
// History" whenever the analysis also had an SPS V3 assessment -- a
// band-aid so this section's "Current Score" didn't read as a second
// number directly contradicting the hero above it (see
// StartupHeroV2.tsx's own comment on the actual fix). Now that the
// hero always shows this SAME startup_intelligence_score (V3, when
// present, is a clearly-labeled secondary/experimental note, never a
// competing "current" number), there is nothing left to disambiguate --
// this always says "Current Score"/"Score History", full stop. Removing
// the special case is the real fix; relabeling around a contradiction
// was only ever a symptom treatment.
export default function SPSHistory({ history }: SPSHistoryProps) {
  const gradientId = useId();

  if (history.length === 0) {
    return (
      <BaseCard className="p-6">
        <SectionHeading />
        <p className="mt-3 text-sm text-text-secondary">
          No historical analyses yet. Run another analysis for this company
          to start tracking its VentureGPS Score over time.
        </p>
      </BaseCard>
    );
  }

  const first = history[0];
  const latest = history[history.length - 1];

  if (history.length === 1) {
    return (
      <BaseCard className="p-6">
        <SectionHeading />

        <div className="mt-4 flex flex-wrap items-end gap-x-10 gap-y-4">
          <Stat
            label="Current Score"
            value={latest.startup_intelligence_score.toFixed(1)}
          />
          <Stat label="Historical analyses" value="1" />
          <Stat label="Last analysis" value={formatDate(latest.created_at)} />
        </div>

        <p className="mt-4 text-sm text-text-secondary">
          Only one canonical analysis exists for this company — a trend will appear once a second analysis is recorded.
        </p>
      </BaseCard>
    );
  }

  const change =
    latest.startup_intelligence_score - first.startup_intelligence_score;
  const changeTone = change > 0 ? "success" : change < 0 ? "danger" : "neutral";

  return (
    <BaseCard className="p-6">
      <SectionHeading />

      <div className="mt-4 flex flex-wrap items-end gap-x-10 gap-y-4">
        <Stat
          label="Current Score"
          value={latest.startup_intelligence_score.toFixed(1)}
        />

        <Stat
          label="Change from first"
          value={`${change > 0 ? "+" : ""}${change.toFixed(1)}`}
          tone={changeTone}
        />

        <Stat label="Historical analyses" value={String(history.length)} />
        <Stat label="Last analysis" value={formatDate(latest.created_at)} />
      </div>

      <div className="mt-6">
        <SPSLineChart history={history} gradientId={gradientId} />
      </div>
    </BaseCard>
  );
}

function SectionHeading() {
  return (
    <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
      Score History
    </h2>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "success" | "danger" | "neutral";
}) {
  const toneClass =
    tone === "success"
      ? "text-success"
      : tone === "danger"
      ? "text-danger"
      : "text-text-primary";

  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
        {label}
      </p>
      <p className={["mt-0.5 text-xl font-bold", toneClass].join(" ")}>
        {value}
      </p>
    </div>
  );
}

function SPSLineChart({
  history,
  gradientId,
}: {
  history: SPSHistoryPoint[];
  gradientId: string;
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const times = history.map((point) => new Date(point.created_at).getTime());
  const scores = history.map((point) => point.startup_intelligence_score);

  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const timeRange = maxTime - minTime || 1;

  const rawMin = Math.min(...scores);
  const rawMax = Math.max(...scores);
  const scorePadding = Math.max((rawMax - rawMin) * 0.15, 3);
  const yMin = Math.max(0, Math.floor(rawMin - scorePadding));
  const yMax = Math.min(100, Math.ceil(rawMax + scorePadding));
  const yRange = yMax - yMin || 1;

  const plotWidth = CHART_WIDTH - PADDING_X * 2;
  const plotHeight = CHART_HEIGHT - PADDING_TOP - PADDING_BOTTOM;
  const baselineY = PADDING_TOP + plotHeight;

  function xFor(time: number) {
    return PADDING_X + ((time - minTime) / timeRange) * plotWidth;
  }

  function yFor(score: number) {
    return PADDING_TOP + plotHeight - ((score - yMin) / yRange) * plotHeight;
  }

  const points = history.map((point, index) => ({
    x: xFor(new Date(point.created_at).getTime()),
    y: yFor(point.startup_intelligence_score),
    point,
    index,
  }));

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");

  const areaPath =
    `${linePath} ` +
    `L${points[points.length - 1].x.toFixed(1)},${baselineY.toFixed(1)} ` +
    `L${points[0].x.toFixed(1)},${baselineY.toFixed(1)} Z`;

  const maxLabels = 6;
  const labelStep = Math.max(1, Math.ceil(points.length / maxLabels));
  const active = activeIndex !== null ? points[activeIndex] : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        className="w-full"
        role="img"
        aria-label={`VentureGPS Score history chart, ${history.length} analyses, current score ${history[
          history.length - 1
        ].startup_intelligence_score.toFixed(1)}`}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--primary)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {[0, 0.5, 1].map((fraction) => {
          const y = PADDING_TOP + plotHeight * fraction;
          return (
            <line
              key={fraction}
              x1={PADDING_X}
              x2={CHART_WIDTH - PADDING_X}
              y1={y}
              y2={y}
              className="stroke-border"
              strokeWidth={1}
            />
          );
        })}

        {/* Global readability audit: bumped from 9px. These stay below
            the general 12px floor with a documented reason -- axis tick
            values inside a fixed 640x200 viewBox chart, where every extra
            unit competes for real space against up to 6 date labels and
            the plotted line itself. 11px is the largest size that doesn't
            crowd the y-axis values into the plotted area. */}
        <text x={2} y={PADDING_TOP + 3} className="fill-text-muted text-[11px]">
          {yMax}
        </text>
        <text x={2} y={baselineY + 3} className="fill-text-muted text-[11px]">
          {yMin}
        </text>

        <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />

        <path
          d={linePath}
          fill="none"
          className="stroke-primary"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {points
          .filter((p) => p.index % labelStep === 0 || p.index === points.length - 1)
          .map(({ x, point, index }) => (
            <text
              key={index}
              x={x}
              y={CHART_HEIGHT - 8}
              textAnchor="middle"
              className="fill-text-muted text-[11px]"
            >
              {formatShortDate(point.created_at)}
            </text>
          ))}

        {points.map(({ x, y, point, index }) => {
          const isLatest = index === points.length - 1;
          const isActive = activeIndex === index;

          return (
            <g key={point.analysis_id}>
              {isActive || isLatest ? (
                <circle cx={x} cy={y} r={isLatest ? 9 : 7} className="fill-primary/15" />
              ) : null}

              <circle
                cx={x}
                cy={y}
                r={isLatest ? 5 : 3.5}
                strokeWidth={isLatest ? 0 : 1.5}
                className={isLatest ? "fill-primary" : "fill-surface stroke-primary"}
              />

              <circle
                cx={x}
                cy={y}
                r={12}
                fill="transparent"
                tabIndex={0}
                role="img"
                aria-label={`${formatDate(point.created_at)}: VentureGPS Score ${point.startup_intelligence_score.toFixed(
                  1
                )}`}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseLeave={() => setActiveIndex(null)}
                onFocus={() => setActiveIndex(index)}
                onBlur={() => setActiveIndex(null)}
                className="cursor-pointer outline-none"
              />
            </g>
          );
        })}
      </svg>

      {active ? (
        <div
          className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-lg border border-border bg-surface-elevated px-2.5 py-1.5 text-xs whitespace-nowrap shadow-lg"
          style={{
            left: `${(active.x / CHART_WIDTH) * 100}%`,
            top: `${(active.y / CHART_HEIGHT) * 100}%`,
            marginTop: -8,
          }}
        >
          <p className="font-semibold text-text-primary">
            {active.point.startup_intelligence_score.toFixed(1)}
          </p>
          <p className="text-text-muted">{formatDate(active.point.created_at)}</p>
        </div>
      ) : null}
    </div>
  );
}
