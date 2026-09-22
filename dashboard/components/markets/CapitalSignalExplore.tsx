// VentureGPS Increment 15, Part 4 -- progressive disclosure below the signature chart.
//
// Increment 15.1 -- Consumer Experience Refinement, Part 4: rebuilt from six equally-weighted, identical-looking
// Disclosure accordions (a visual "settings menu," per the review) into a tiered layout with real hierarchy:
// - "Financing snapshot" -- ALWAYS visible, Financing Activity + Companies Funded + Verified Capital combined
//   into one plain-language card (they're one story -- "what happened this period" -- not three separate menu
//   items); raw diagnostics counts (events excluded, missing dates, etc.) move into one small nested <details>
//   inside it, since that's genuinely secondary detail for the rare reader who wants it.
// - "Stage distribution" and "Capital concentration" -- ALWAYS visible, each its own small visual (a stacked
//   share bar), since both ARE inherently visual data, not settings to expand.
// - "How this compares historically" -- the one remaining Disclosure. Component-level Capital Signal direction
//   is the most technical content on the page (percentile ranks, the methodology's own limitations paragraph),
//   so it stays one tap away rather than always-on, matching "keep methodology details available on demand."
import Disclosure from "@/components/ui/Disclosure";
import BaseCard from "@/components/ui/BaseCard";
import DirectionBadge from "./DirectionBadge.tsx";
import CoverageNote from "./CoverageNote.tsx";

import { formatExactAmount, formatRatioAsPercent, ratioToPercentNumber } from "@/lib/api/v2/money.ts";
import {
  CONCENTRATION_EXPLANATION,
  CONCENTRATION_LABEL,
  DIRECTION_EXPLANATION,
  DIRECTION_LABEL,
  DIRECTION_SYMBOL,
  DIRECTION_TONE,
  METRIC_LABEL,
} from "@/lib/api/v2/signalLabels.ts";

import type { CapitalSignalResponse, ConcentrationTrend, StageKey } from "@/types/v2/capital";

// Concentration is its own vocabulary (ConcentrationTrend), so it gets its own symbol map rather than reusing
// CapitalDirection's -- "more concentrated" is not the same axis as "increased," and conflating their glyphs
// would visually imply a relationship the data doesn't support.
const CONCENTRATION_SYMBOL: Record<ConcentrationTrend, string> = {
  more_concentrated: "↑",
  less_concentrated: "↓",
  stable: "→",
  insufficient_data: "—",
};

const STAGE_LABELS: Record<StageKey, string> = {
  pre_seed: "Pre-seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  growth: "Growth",
  unknown: "Stage unknown",
};

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-base font-semibold text-text-primary">{children}</h3>;
}

type CapitalSignalExploreProps = {
  signal: CapitalSignalResponse;
};

export default function CapitalSignalExplore({ signal }: CapitalSignalExploreProps) {
  const metrics = signal.current_window.metrics;
  const stageTotal = Object.values(metrics.stage_distribution).reduce((sum, count) => sum + count, 0);

  return (
    <section aria-labelledby="explore-heading" className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <h2 id="explore-heading" className="text-2xl font-bold text-text-primary">
        Explore this market
      </h2>
      <p className="mt-2 text-base leading-7 text-text-secondary">
        A closer look at the current 30-day period, and how this market compares to its own recent history.
      </p>

      <div className="mt-6 space-y-5">
        {/* Financing snapshot -- Financing Activity + Companies Funded + Verified Capital as one story. */}
        <BaseCard className="p-5">
          <SectionHeading>Financing snapshot</SectionHeading>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            VentureGPS verified <span className="font-semibold text-text-primary">{metrics.financing_activity.toLocaleString()}</span>{" "}
            {metrics.financing_activity === 1 ? "financing" : "distinct financings"} this period, across{" "}
            <span className="font-semibold text-text-primary">{metrics.companies_funded.toLocaleString()}</span>{" "}
            {metrics.companies_funded === 1 ? "company" : "companies"}
            {metrics.companies_funded > 0 && metrics.companies_funded !== metrics.financing_activity ? " (a company with multiple rounds still counts once)" : ""}.
          </p>

          {metrics.capital_deployed.length === 0 ? (
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              No verified financing amounts for this period -- a coverage gap, not necessarily zero capital raised.
            </p>
          ) : (
            <ul className="mt-2 space-y-1">
              {metrics.capital_deployed.map((money) => (
                <li key={money.currency_code} className="text-sm leading-6 text-text-secondary">
                  <span className="font-semibold text-text-primary">{formatExactAmount(money.minor_units, money.currency_code)}</span>{" "}
                  verified this period
                </li>
              ))}
            </ul>
          )}
          {metrics.capital_deployed.length > 1 ? (
            <p className="mt-1 text-xs text-text-muted">Currencies are never converted or combined.</p>
          ) : null}

          <details className="group mt-3 border-t border-border pt-3">
            <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-sm font-medium text-text-muted marker:content-none">
              Coverage &amp; diagnostics
              <span aria-hidden="true" className="transition-transform group-open:rotate-180">
                ▾
              </span>
            </summary>
            <CoverageNote diagnostics={metrics.diagnostics} className="mt-2" />
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs text-text-muted">
              <dt>Events considered</dt>
              <dd className="text-right text-text-secondary">{metrics.diagnostics.events_considered.toLocaleString()}</dd>
              <dt>Events included</dt>
              <dd className="text-right text-text-secondary">{metrics.diagnostics.events_included.toLocaleString()}</dd>
              <dt>Missing a usable date</dt>
              <dd className="text-right text-text-secondary">{metrics.diagnostics.events_excluded_missing_date.toLocaleString()}</dd>
              <dt>Outside this period</dt>
              <dd className="text-right text-text-secondary">{metrics.diagnostics.events_excluded_outside_period.toLocaleString()}</dd>
              <dt>No verified amount</dt>
              <dd className="text-right text-text-secondary">{metrics.diagnostics.events_without_verified_amount.toLocaleString()}</dd>
              <dt>No known stage</dt>
              <dd className="text-right text-text-secondary">{metrics.diagnostics.events_without_known_stage.toLocaleString()}</dd>
            </dl>
          </details>
        </BaseCard>

        {/* Stage distribution -- always visible; this IS a visual, not a setting to expand. */}
        <BaseCard className="p-5">
          <SectionHeading>Stage distribution</SectionHeading>
          {stageTotal === 0 ? (
            <p className="mt-2 text-sm leading-6 text-text-secondary">No financings with a known stage this period.</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {(Object.keys(STAGE_LABELS) as StageKey[]).map((stage) => {
                const count = metrics.stage_distribution[stage];
                if (count === 0) return null;
                const share = Math.round((count / stageTotal) * 100);
                return (
                  <li key={stage} className="flex items-center gap-3 text-sm">
                    <span className="w-24 shrink-0 text-text-secondary">{STAGE_LABELS[stage]}</span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-muted">
                      <span className="block h-full rounded-full bg-primary" style={{ width: `${share}%` }} />
                    </span>
                    <span className="w-16 shrink-0 text-right font-medium text-text-primary">
                      {count.toLocaleString()} ({share}%)
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </BaseCard>

        {/* Capital concentration -- always visible; a small share bar per currency, plain-language, never a
            judgement (largest-round share, computed from the two exact integers the API already gave us --
            not a new calculation, the same reuse formatRatioAsPercent already gets for percentile rank). */}
        <BaseCard className="p-5">
          <SectionHeading>Capital concentration</SectionHeading>
          {metrics.capital_concentration.length === 0 ? (
            <p className="mt-2 text-sm leading-6 text-text-secondary">No verified capital this period to measure concentration.</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {metrics.capital_concentration.map((entry) => {
                const percent = formatRatioAsPercent(entry.largest_minor_units, entry.total_minor_units);
                const shareNumber = ratioToPercentNumber(entry.largest_minor_units, entry.total_minor_units);
                return (
                  <li key={entry.currency_code}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span className="text-text-secondary">Largest financing ({entry.currency_code})</span>
                      <span className="font-semibold text-text-primary">{percent} of total</span>
                    </div>
                    <span className="mt-1.5 block h-2 overflow-hidden rounded-full bg-surface-muted">
                      <span className="block h-full rounded-full bg-secondary" style={{ width: `${Math.max(shareNumber, 2)}%` }} />
                    </span>
                    <p className="mt-1.5 text-xs text-text-muted">
                      {formatExactAmount(entry.largest_minor_units, entry.currency_code)} of{" "}
                      {formatExactAmount(entry.total_minor_units, entry.currency_code)} total verified capital.
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-3 text-xs leading-5 text-text-muted">
            A description of how concentrated capital was in the largest round -- not a judgement about whether
            that&rsquo;s good or bad for this market.
          </p>
        </BaseCard>

        {/* The one remaining Disclosure -- the most technical content (percentile ranks, methodology
            limitations), kept available on demand rather than always-on. */}
        <Disclosure summary="How this compares historically">
          <div className="space-y-4">
            {(["financing_activity", "companies_funded"] as const).map((key) => {
              const component = signal[key];
              return (
                <div key={key}>
                  <p className="text-sm font-semibold text-text-primary">{METRIC_LABEL[key]}</p>
                  <div className="mt-1.5">
                    <DirectionBadge
                      symbol={DIRECTION_SYMBOL[component.direction]}
                      label={DIRECTION_LABEL[component.direction]}
                      tone={DIRECTION_TONE[component.direction]}
                      size="sm"
                    />
                  </div>
                  <p className="mt-1.5 text-sm leading-6 text-text-secondary">{DIRECTION_EXPLANATION[component.direction]}</p>
                </div>
              );
            })}

            {signal.capital_deployed.map((component) => (
              <div key={component.currency_code}>
                <p className="text-sm font-semibold text-text-primary">
                  {METRIC_LABEL.capital_deployed} ({component.currency_code})
                </p>
                <div className="mt-1.5">
                  <DirectionBadge
                    symbol={DIRECTION_SYMBOL[component.direction]}
                    label={DIRECTION_LABEL[component.direction]}
                    tone={DIRECTION_TONE[component.direction]}
                    size="sm"
                  />
                </div>
                <p className="mt-1.5 text-sm leading-6 text-text-secondary">{DIRECTION_EXPLANATION[component.direction]}</p>
              </div>
            ))}

            {signal.capital_concentration.map((concentration) => (
              <div key={concentration.currency_code}>
                <p className="text-sm font-semibold text-text-primary">Capital concentration ({concentration.currency_code})</p>
                <div className="mt-1.5">
                  <DirectionBadge
                    symbol={CONCENTRATION_SYMBOL[concentration.trend]}
                    label={CONCENTRATION_LABEL[concentration.trend]}
                    tone={concentration.trend === "insufficient_data" ? "unknown" : "neutral"}
                    size="sm"
                  />
                </div>
                <p className="mt-1.5 text-sm leading-6 text-text-secondary">{CONCENTRATION_EXPLANATION[concentration.trend]}</p>
              </div>
            ))}

            <p className="border-t border-border pt-3 text-sm leading-6 text-text-muted">{signal.methodology.limitations}</p>
          </div>
        </Disclosure>
      </div>
    </section>
  );
}
