"use client";

// VentureGPS Increment 16 -- the proposed "market card" visual language: a compact, tappable card built around
// a direction badge and a glimpse of shape (a tiny 9-bar sparkline echoing CapitalChart.tsx's real bar-chart
// language, at prototype scale) rather than a KPI-grid row of numbers -- the thing per Section 3's "avoid
// endless KPI cards" instruction. Reuses the REAL DirectionBadge component and the REAL signalLabels.ts
// vocabulary (tone/symbol/label) from the production market page -- only the underlying numbers are sample data.
import DirectionBadge from "@/components/markets/DirectionBadge.tsx";
import { DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";

import type { SampleMarketSignal } from "./sampleData";

type MarketSignalCardProps = {
  market: SampleMarketSignal;
  selected?: boolean;
  onSelect?: () => void;
  compact?: boolean;
};

function Sparkline({ values, isFlat }: { values: number[]; isFlat: boolean }) {
  const max = Math.max(...values, 0.05);
  return (
    <div className="flex h-10 items-end gap-[3px]" aria-hidden="true">
      {values.map((value, index) => {
        const isCurrent = index === values.length - 1;
        const heightPercent = isFlat ? 8 : Math.max((value / max) * 100, 8);
        return (
          <span
            key={index}
            style={{ height: `${heightPercent}%` }}
            className={["w-full rounded-t", isCurrent ? "bg-primary" : "bg-primary/25"].join(" ")}
          />
        );
      })}
    </div>
  );
}

export default function MarketSignalCard({ market, selected = false, onSelect, compact = false }: MarketSignalCardProps) {
  const tone = DIRECTION_TONE[market.direction];
  const isFlat = market.direction === "insufficient_data";

  const cardClassName = [
    "group flex w-full flex-col gap-3 rounded-2xl border bg-surface p-4 text-left transition-colors",
    selected ? "border-primary/50 bg-primary/5" : "border-border",
    compact ? "" : "shrink-0",
  ].join(" ");

  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-base font-semibold text-text-primary">{market.displayName}</p>
          <p className="truncate text-xs text-text-muted">{market.oneLiner}</p>
        </div>
        <span className="shrink-0 rounded-full border border-dashed border-border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
          Sample
        </span>
      </div>

      <Sparkline values={market.sparkline} isFlat={isFlat} />

      <div className="flex items-center justify-between gap-2">
        <DirectionBadge symbol={DIRECTION_SYMBOL[market.direction]} label={DIRECTION_LABEL[market.direction]} tone={tone} size="sm" />
        {market.verifiedCapitalLabel !== "—" ? (
          <span className="text-sm font-semibold text-text-primary">{market.verifiedCapitalLabel}</span>
        ) : null}
      </div>
    </>
  );

  // With no onSelect, this card is browse-only (ExploreMarketsSection's grid) -- rendered as a plain, non-
  // interactive div rather than a button that would do nothing when tapped. A control that LOOKS clickable but
  // has no effect is its own kind of "dead link disguised as functional" -- this avoids that even for a card,
  // not just a nav item.
  if (!onSelect) {
    return <div className={cardClassName} style={compact ? undefined : { width: "15.5rem" }}>{body}</div>;
  }

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={[cardClassName, "hover:border-primary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"].join(" ")}
      style={compact ? undefined : { width: "15.5rem" }}
    >
      {body}
    </button>
  );
}
