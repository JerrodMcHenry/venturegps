"use client";

// VentureGPS Increment 16.1 -- Direction B's signature interaction: markets as nodes in a spatial constellation
// around a center "focused" market, rather than a card grid or a linear rail (Increment 16's SignalsRail, or
// Direction A's vertical chapters). Tapping any outer node re-centers the constellation on it. Genuinely
// different navigational geometry from either sibling direction, not the same list with a different skin.
//
// Positions are computed deterministically (evenly spaced around a circle), not randomly -- so the layout is
// stable across renders/screenshots and reviewable. A square, percentage-based coordinate system
// (`aspect-square`, positions in %) means this scales correctly from 375px to desktop with no separate mobile
// layout needed; only the container's own size changes.
import { useState } from "react";

import DirectionBadge from "@/components/markets/DirectionBadge.tsx";
import { DIRECTION_EXPLANATION, DIRECTION_LABEL, DIRECTION_SYMBOL, DIRECTION_TONE } from "@/lib/api/v2/signalLabels.ts";

import type { SampleMarketSignal } from "@/components/design/discover/sampleData";

const TONE_NODE_CLASSES: Record<string, string> = {
  positive: "bg-success border-success/60",
  negative: "bg-danger border-danger/60",
  neutral: "bg-text-muted border-text-muted/60",
  mixed: "bg-info border-info/60",
  unknown: "bg-transparent border-dashed border-text-muted",
};

type MarketConstellationProps = {
  markets: SampleMarketSignal[];
};

export default function MarketConstellation({ markets }: MarketConstellationProps) {
  const [focusedSlug, setFocusedSlug] = useState(markets[0]?.slug ?? null);
  const focused = markets.find((m) => m.slug === focusedSlug) ?? markets[0];
  const orbit = markets.filter((m) => m.slug !== focused?.slug);

  const radius = 38; // percent of container
  const centerX = 50;
  const centerY = 50;

  return (
    <div className="mx-auto w-full max-w-xl">
      <div className="relative aspect-square w-full" role="group" aria-label="Market constellation -- select a market to bring it into focus">
        {/* Connecting lines -- purely decorative, echoing a "network"/"signal map" feel. Deliberately static, not
            rotating: the lines and the node buttons they connect to are separate elements, so animating only the
            lines would slowly drift them out of alignment with their own nodes -- a real bug, not a stylistic
            choice. The center node carries the "alive" motion instead (a self-contained pulse, see below). */}
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" aria-hidden="true">
          {orbit.map((market, index) => {
            const angle = (index / orbit.length) * 2 * Math.PI - Math.PI / 2;
            const x = centerX + radius * Math.cos(angle);
            const y = centerY + radius * Math.sin(angle);
            return (
              <line key={market.slug} x1={centerX} y1={centerY} x2={x} y2={y} stroke="var(--border)" strokeWidth="0.4" />
            );
          })}
        </svg>

        {/* Center: the focused market. A self-contained pulse ring (its own absolutely-positioned, identically-
            centered element) is the one piece of ambient motion in this composition -- confirms "this is the
            live, focused node" without needing to stay synchronized with anything else on screen. */}
        {focused ? (
          <>
            <span
              aria-hidden="true"
              className="absolute left-1/2 top-1/2 size-28 -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/40 motion-safe:animate-ping motion-reduce:hidden sm:size-36"
            />
            <div
              className="absolute left-1/2 top-1/2 flex size-28 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center rounded-full border-2 border-primary bg-surface p-2 text-center shadow-lg sm:size-36"
              aria-live="polite"
            >
              <p className="text-sm font-bold leading-tight text-text-primary sm:text-base">{focused.displayName}</p>
              <span aria-hidden="true" className="mt-1 text-lg">
                {DIRECTION_SYMBOL[focused.direction]}
              </span>
            </div>
          </>
        ) : null}

        {/* Orbit: every other market, tappable to re-center. Real buttons, min 44px touch target regardless of
            visual node size (padding, not just the visible dot, carries the tap area). */}
        {orbit.map((market, index) => {
          const angle = (index / orbit.length) * 2 * Math.PI - Math.PI / 2;
          const x = centerX + radius * Math.cos(angle);
          const y = centerY + radius * Math.sin(angle);
          const tone = DIRECTION_TONE[market.direction];

          return (
            <button
              key={market.slug}
              type="button"
              onClick={() => setFocusedSlug(market.slug)}
              aria-label={`Focus on ${market.displayName}: ${DIRECTION_LABEL[market.direction]}`}
              className="absolute flex min-h-11 min-w-11 -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1.5 rounded-full p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              style={{ left: `${x}%`, top: `${y}%` }}
            >
              <span className={["size-4 rounded-full border-2 sm:size-5", TONE_NODE_CLASSES[tone]].join(" ")} aria-hidden="true" />
              <span className="max-w-[5.5rem] truncate text-[11px] font-medium text-text-secondary">{market.displayName}</span>
            </button>
          );
        })}
      </div>

      {focused ? (
        <div className="mt-8 rounded-2xl border border-border bg-surface-subtle p-5">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-semibold text-text-primary">{focused.displayName}</p>
            <DirectionBadge symbol={DIRECTION_SYMBOL[focused.direction]} label={DIRECTION_LABEL[focused.direction]} tone={DIRECTION_TONE[focused.direction]} size="sm" />
          </div>
          <p className="mt-2 text-sm leading-6 text-text-secondary">{DIRECTION_EXPLANATION[focused.direction]}</p>
        </div>
      ) : null}
    </div>
  );
}
