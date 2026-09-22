// Shapes a CapitalSignalResponse into the data CapitalChart.tsx renders. Pure and framework-free on purpose --
// testable without a DOM or a React renderer (see tests/v2ChartData.test.ts). Never invents a missing
// observation and never interpolates between windows: exactly 9 points (8 historical + 1 current) come out for
// every selectable series, always in the same chronological order the backend returned them in.

import { bigIntToChartNumber, parseMinorUnits } from "./money.ts";

import type { CapitalSignalResponse, ComponentMetric, ComponentSignalOut } from "@/types/v2/capital";

export type ChartPoint = {
  label: string; // a short, human date label for this window (e.g. "Aug '26")
  start: string; // ISO 8601 window start -- the exact, unrounded value a tooltip can use
  end: string;
  exactValue: string; // the exact decimal-string value for this point (a count or minor units) -- NEVER derived from chartValue
  chartValue: number; // an APPROXIMATE number for SVG positioning only -- see money.ts's bigIntToChartNumber
  isCurrent: boolean;
};

export type ChartSeries = {
  metric: ComponentMetric;
  currencyCode: string | null;
  points: ChartPoint[]; // exactly 9: 8 historical (oldest first) + 1 current, last
  direction: ComponentSignalOut["direction"];
  sufficientHistory: boolean; // false iff direction === "insufficient_data"
};

function shortWindowLabel(isoStart: string): string {
  const date = new Date(isoStart);
  if (Number.isNaN(date.getTime())) return isoStart;
  return date.toLocaleDateString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" });
}

function pointsFromComponent(signal: CapitalSignalResponse, component: ComponentSignalOut): ChartPoint[] {
  const windows = [...signal.historical_windows, signal.current_window];

  return component.historical_values
    .concat(component.current_value)
    .map((exactValue, index) => {
      const window = windows[index];
      return {
        label: shortWindowLabel(window.start),
        start: window.start,
        end: window.end,
        exactValue,
        chartValue: bigIntToChartNumber(parseMinorUnits(exactValue)),
        isCurrent: index === windows.length - 1,
      };
    });
}

// Financing Activity / Companies Funded: exactly one series, no currency.
export function buildCountSeries(signal: CapitalSignalResponse, metric: "financing_activity" | "companies_funded"): ChartSeries {
  const component = signal[metric];
  return {
    metric,
    currencyCode: null,
    points: pointsFromComponent(signal, component),
    direction: component.direction,
    sufficientHistory: component.direction !== "insufficient_data",
  };
}

// Verified Capital: one series PER CURRENCY -- never combined. Returns null if the requested currency has no
// component in this signal at all (distinct from "insufficient history", which still returns a series whose
// points are legitimate zeros).
export function buildCapitalDeployedSeries(signal: CapitalSignalResponse, currencyCode: string): ChartSeries | null {
  const component = signal.capital_deployed.find((entry) => entry.currency_code === currencyCode);
  if (!component) return null;

  return {
    metric: "capital_deployed",
    currencyCode,
    points: pointsFromComponent(signal, component),
    direction: component.direction,
    sufficientHistory: component.direction !== "insufficient_data",
  };
}

export function availableCapitalDeployedCurrencies(signal: CapitalSignalResponse): string[] {
  return signal.capital_deployed.map((entry) => entry.currency_code!).filter((code): code is string => Boolean(code));
}

// The largest chartValue across a series -- used to scale bar/line heights. Never zero (a chart with an
// all-zero series still needs a non-zero denominator to lay out); callers fall back to 1 when every point is 0.
export function seriesMax(series: ChartSeries): number {
  return Math.max(1, ...series.points.map((point) => point.chartValue));
}
