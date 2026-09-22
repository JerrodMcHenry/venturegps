"use client";

// VentureGPS Increment 15, Part 3 -- the signature Capital visualization. One interactive chart, switchable
// between the three component metrics (Financing Activity / Companies Funded / Verified Capital, the last split
// further by currency). Built as real <button> elements rather than clickable SVG shapes: every bar is a proper
// 44px-tall touch target, keyboard-focusable, with its own accessible name -- accessibility Part 9 asks for this
// directly, and it sidesteps SVG's weaker interaction/focus story on mobile Safari.
//
// Every bar's height is an intentionally APPROXIMATE pixel proportion (chartValue, from chartData.ts's one
// documented lossy conversion). The exact value for whichever period is selected is always shown as text
// alongside it, in both a visible caption and each bar's aria-label -- a viewer (sighted or not) is never given
// only the rounded pixel height as the record of what happened.
import { useMemo, useState } from "react";

import Tabs from "@/components/ui/Tabs";
import EmptyState from "@/components/ui/EmptyState";
import DirectionBadge from "./DirectionBadge.tsx";

import {
  availableCapitalDeployedCurrencies,
  buildCapitalDeployedSeries,
  buildCountSeries,
  seriesMax,
  type ChartSeries,
} from "@/lib/api/v2/chartData.ts";
import { formatAbbreviatedAmount, formatExactAmount, formatRatioAsPercent } from "@/lib/api/v2/money.ts";
import {
  DIRECTION_EXPLANATION,
  DIRECTION_LABEL,
  DIRECTION_SYMBOL,
  DIRECTION_TONE,
  METRIC_EXPLANATION,
  METRIC_LABEL,
} from "@/lib/api/v2/signalLabels.ts";

import type { CapitalSignalResponse, ComponentMetric } from "@/types/v2/capital";

type CapitalChartProps = {
  signal: CapitalSignalResponse;
};

function pointDisplayValue(series: ChartSeries, exactValue: string): string {
  return series.currencyCode ? formatAbbreviatedAmount(exactValue, series.currencyCode) : Number(exactValue).toLocaleString();
}

function pointExactLabel(series: ChartSeries, exactValue: string): string {
  return series.currencyCode ? formatExactAmount(exactValue, series.currencyCode) : `${Number(exactValue).toLocaleString()} exactly`;
}

export default function CapitalChart({ signal }: CapitalChartProps) {
  const currencies = useMemo(() => availableCapitalDeployedCurrencies(signal), [signal]);
  const [metric, setMetric] = useState<ComponentMetric>("financing_activity");
  const [currency, setCurrency] = useState<string | null>(currencies[0] ?? null);
  const [selectedIndex, setSelectedIndex] = useState(8); // default to the current (last) window

  const series: ChartSeries | null =
    metric === "capital_deployed"
      ? currency
        ? buildCapitalDeployedSeries(signal, currency)
        : null
      : buildCountSeries(signal, metric as "financing_activity" | "companies_funded");

  const component = metric === "capital_deployed" ? null : signal[metric];

  const metricTabs: { id: string; label: string }[] = [
    { id: "financing_activity", label: METRIC_LABEL.financing_activity },
    { id: "companies_funded", label: METRIC_LABEL.companies_funded },
    { id: "capital_deployed", label: METRIC_LABEL.capital_deployed },
  ];

  function handleMetricChange(id: string) {
    setMetric(id as ComponentMetric);
    setSelectedIndex(8);
  }

  const selectedPoint = series?.points[Math.min(selectedIndex, series.points.length - 1)] ?? null;
  const max = series ? seriesMax(series) : 1;

  return (
    <section aria-labelledby="capital-chart-heading" className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <h2 id="capital-chart-heading" className="text-2xl font-bold text-text-primary">
        Capital activity over time
      </h2>

      <div className="mt-4">
        <Tabs tabs={metricTabs} activeId={metric} onChange={handleMetricChange} className="w-fit" />
      </div>

      <p className="mt-4 max-w-xl text-base leading-7 text-text-secondary">{METRIC_EXPLANATION[metric]}</p>

      {metric === "capital_deployed" && currencies.length > 1 ? (
        <div className="mt-4">
          <Tabs
            tabs={currencies.map((code) => ({ id: code, label: code }))}
            activeId={currency ?? currencies[0]}
            onChange={(id) => {
              setCurrency(id);
              setSelectedIndex(8);
            }}
            className="w-fit"
          />
        </div>
      ) : null}

      {!series ? (
        <EmptyState
          className="mt-6"
          title="No verified capital amounts yet"
          description="VentureGPS hasn't verified any financing amounts for this market yet. This reflects VentureGPS's current coverage -- it doesn't mean no capital was raised."
        />
      ) : (
        <div className="mt-6">
          {!series.sufficientHistory ? (
            <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-border bg-surface-subtle px-4 py-3">
              <DirectionBadge symbol={DIRECTION_SYMBOL.insufficient_data} label={DIRECTION_LABEL.insufficient_data} tone="unknown" size="sm" />
              <span className="text-sm text-text-muted">{DIRECTION_EXPLANATION.insufficient_data}</span>
            </div>
          ) : null}

          {/* The interactive chart. Each bar is a real button with its own accessible name (period + exact
              value) -- a screen reader user gets the full record from the button list alone, with no dependency
              on the visual bar heights. `motion-reduce:transition-none` honors prefers-reduced-motion (Part 9).
              Increment 15.1: bars and labels are two SEPARATE rows, not one button-per-bar containing both.
              Increment 15's original markup nested a percentage-height bar span inside a button whose own height
              was never set explicitly (`items-end` sizes flex children to their content, not the container) --
              a percentage height against an indefinite-height containing block computes to 0 per the CSS spec, so
              every bar silently rendered at ~0px regardless of its real value (the "nearly empty chart" bug).
              The fix: the track row below has the one definite, fixed height (`h-52`/`sm:h-64`), each button is
              `h-full` (a real, definite height to size the bar span's percentage against), and gets NOTHING else
              inside it -- period labels live in their own row underneath instead of sharing a button, so a
              short label's height can never eat into a tall bar's available space. */}
          <div
            role="group"
            aria-label={`${METRIC_LABEL[metric]}${series.currencyCode ? ` in ${series.currencyCode}` : ""} by period -- select a bar to see its exact value`}
            className="flex h-52 items-end gap-1.5 border-b border-border sm:h-64 sm:gap-2.5"
          >
            {series.points.map((point, index) => {
              const isSelected = index === selectedIndex;
              const isZero = point.chartValue <= 0;
              // A real, confirmed zero still renders as a small visible sliver (never 0px) -- indistinguishable
              // from "nothing rendered" is exactly the bug this fixes; a true zero must look deliberate.
              const heightPercent = isZero ? 3 : Math.max((point.chartValue / max) * 100, 6);

              return (
                <button
                  key={point.start}
                  type="button"
                  onClick={() => setSelectedIndex(index)}
                  aria-pressed={isSelected}
                  aria-label={`${point.label}${point.isCurrent ? " (current period)" : ""}: ${pointExactLabel(series, point.exactValue)}`}
                  className="group flex h-full min-w-0 flex-1 flex-col justify-end rounded-t focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
                >
                  {isZero ? (
                    <span
                      aria-hidden="true"
                      className={[
                        "mx-auto size-1.5 rounded-full ring-2 ring-offset-1",
                        point.isCurrent ? "bg-primary ring-primary/30" : "bg-text-muted ring-transparent",
                      ].join(" ")}
                    />
                  ) : (
                    <span
                      aria-hidden="true"
                      style={{ height: `${heightPercent}%` }}
                      className={[
                        "w-full rounded-t transition-[height] duration-300 motion-reduce:transition-none",
                        point.isCurrent ? "bg-primary" : isSelected ? "bg-primary/70" : "bg-primary/25 group-hover:bg-primary/45",
                      ].join(" ")}
                    />
                  )}
                </button>
              );
            })}
          </div>

          {/* Decorative label row, separate from the bar buttons above (see the comment on the track row) --
              every accessible period/value pairing already lives on the button's own aria-label, so this row is
              aria-hidden. Historical dates are hidden below `sm` (8 date labels don't fit legibly at 320-390px);
              "Now" always shows -- knowing which bar is the current period is core to reading the chart at all. */}
          <div aria-hidden="true" className="mt-1.5 flex gap-1.5 sm:gap-2.5">
            {series.points.map((point) => (
              <span
                key={point.start}
                className={[
                  "flex-1 truncate text-center text-[11px] font-medium",
                  point.isCurrent ? "font-semibold text-primary" : "hidden text-text-muted sm:block",
                ].join(" ")}
              >
                {point.isCurrent ? "Now" : point.label}
              </span>
            ))}
          </div>

          {/* The always-visible exact-value readout for whichever bar is selected -- never only the rounded
              pixel height. Defaults to the current period. */}
          {selectedPoint ? (
            <div className="mt-4 rounded-xl border border-border bg-surface-subtle px-4 py-3">
              <p className="text-sm font-semibold text-text-primary">
                {selectedPoint.isCurrent ? "Current period" : selectedPoint.label}
              </p>
              <p className="mt-1 text-2xl font-bold text-text-primary">{pointDisplayValue(series, selectedPoint.exactValue)}</p>
              <p className="mt-0.5 text-sm text-text-muted">Exact: {pointExactLabel(series, selectedPoint.exactValue)}</p>
            </div>
          ) : null}

          {component?.percentile_rank ? (
            <p className="mt-3 text-sm text-text-muted">
              The current period ranks at the {formatRatioAsPercent(component.percentile_rank.numerator, component.percentile_rank.denominator)}{" "}
              percentile of this market&rsquo;s last {signal.historical_windows.length} periods.
            </p>
          ) : null}

          <div className={["mt-3 inline-flex", series.sufficientHistory ? "" : "hidden"].join(" ")}>
            <DirectionBadge symbol={DIRECTION_SYMBOL[series.direction]} label={DIRECTION_LABEL[series.direction]} tone={DIRECTION_TONE[series.direction]} size="sm" />
          </div>
        </div>
      )}
    </section>
  );
}
