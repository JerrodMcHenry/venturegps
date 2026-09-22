// VentureGPS Increment 15 -- the editorial opening. Per the increment's Part 2, the first mobile viewport must
// answer, without scrolling: which market this is, what VentureGPS can tell about it, over what time period, and
// whether there's enough history for a historical read at all. Every sentence here is built directly from the
// CapitalSignalResponse that was actually returned -- nothing is invented, and nothing uses sensational language
// ("exploding", "crashing", "opportunity"); DIRECTION_EXPLANATION (signalLabels.ts) enforces that vocabulary.
//
// Increment 15.1 -- Consumer Experience Refinement, Part 2: rebuilt for compactness. The original hero stacked
// five full paragraphs (concept line, direction explanation, period sentence, full coverage note, share button)
// before any visual/chart appeared -- on a 390px phone that's 3-4 scrolls before a first-time visitor sees
// anything interactive. Now: name, ONE compact signal+period line, up to three real headline metric chips (read
// directly from `current_window.metrics` -- never hardcoded), a single-sentence coverage caveat (still always
// visible, per the instruction that caveats must never be hidden), and a scroll cue into the chart. The full
// direction explanation and the longer coverage note both still exist -- moved into a native <details> (zero
// extra JS, matches this repo's own Disclosure convention) so they're one tap away, not blocking the fold.
import DirectionBadge from "./DirectionBadge.tsx";
import ShareMarketButton from "./ShareMarketButton.tsx";

import { formatAbbreviatedAmount } from "@/lib/api/v2/money.ts";
import { DIRECTION_EXPLANATION, DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";

import type { CapitalSignalResponse } from "@/types/v2/capital";

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface-subtle px-3.5 py-2.5">
      <p className="text-xl font-bold leading-none text-text-primary">{value}</p>
      <p className="mt-1 text-xs font-medium text-text-muted">{label}</p>
    </div>
  );
}

type MarketHeroProps = {
  signal: CapitalSignalResponse;
  shareUrl: string;
};

export default function MarketHero({ signal, shareUrl }: MarketHeroProps) {
  const tone = DIRECTION_TONE[signal.overall];
  const metrics = signal.current_window.metrics;

  return (
    <header className="border-b border-border pb-6 pt-8 sm:pb-8 sm:pt-12">
      <div className="mx-auto max-w-3xl px-4 sm:px-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">VentureGPS Market</p>

        <h1 className="mt-1.5 text-4xl font-bold leading-tight tracking-tight text-text-primary sm:text-5xl">
          {signal.market.display_name}
        </h1>

        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <DirectionBadge symbol={DIRECTION_SYMBOL[signal.overall]} label={DIRECTION_LABEL[signal.overall]} tone={tone} />
          <span className="text-sm text-text-muted">
            Last 30 days vs. {signal.historical_windows.length} prior periods &middot; as of {formatDate(signal.as_of)}
          </span>
        </div>

        {/* Real headline numbers, straight from this response -- never hardcoded. Verified Capital only appears
            when at least one currency actually has verified capital this period (Part 2: "must not be
            hardcoded" / never coerce an absent metric to zero). */}
        <div className="mt-5 flex flex-wrap gap-2.5">
          <StatChip label="Financings" value={metrics.financing_activity.toLocaleString()} />
          <StatChip label="Companies funded" value={metrics.companies_funded.toLocaleString()} />
          {/* One chip per currency, up to two -- never one currency picked as "primary" and the other's amount
              hidden, and never a combined/converted total (currencies are never summed anywhere in this app). */}
          {metrics.capital_deployed.slice(0, 2).map((money) => (
            <StatChip
              key={money.currency_code}
              label={`Verified capital (${money.currency_code})`}
              value={formatAbbreviatedAmount(money.minor_units, money.currency_code)}
            />
          ))}
          {metrics.capital_deployed.length > 2 ? (
            <StatChip label="More currencies" value={`+${metrics.capital_deployed.length - 2}`} />
          ) : null}
        </div>

        <p className="mt-4 max-w-xl text-sm leading-6 text-text-muted">
          These are financings VentureGPS has verified and classified into this market -- not a full census of
          every financing that happened.
        </p>

        <details className="group mt-3">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-sm font-semibold text-primary marker:content-none">
            What does &ldquo;{DIRECTION_LABEL[signal.overall].toLowerCase()}&rdquo; mean?
            <span aria-hidden="true" className="text-text-muted transition-transform group-open:rotate-180">
              ▾
            </span>
          </summary>
          <p className="mt-2 max-w-xl text-sm leading-6 text-text-secondary">{DIRECTION_EXPLANATION[signal.overall]}</p>
          <p className="mt-2 max-w-xl text-sm leading-6 text-text-secondary">
            Compares {formatDate(signal.current_window.start)}&ndash;{formatDate(signal.current_window.end)} against{" "}
            {signal.historical_windows.length} prior 30-day periods back to{" "}
            {formatDate(signal.historical_windows[0]?.start ?? signal.current_window.start)}.
          </p>
        </details>

        <div className="mt-6 flex items-center gap-3">
          <ShareMarketButton url={shareUrl} title={`${signal.market.display_name} — VentureGPS`} />
        </div>
      </div>
    </header>
  );
}
