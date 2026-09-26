import type { ReactNode } from "react";

import Badge from "./Badge";

// Design System V2 (Phase 10.4), Part 7. A shared presentation shape for
// the number-driven scores that AREN'T the canonical Startup Power Score
// (SPS keeps its own purpose-built SPSRing -- this does not replace or
// wrap it). VPSResultPanel and FundraisingReadinessView each already hand-
// roll a near-identical "label above a big number, status pill, one line
// of explanation" layout; this generalizes that shape so future phases
// don't invent a fourth version of it.
//
// This is PURE PRESENTATION. It accepts whatever score/label/delta values
// its caller already computed and renders them -- it does not compute,
// validate, round, or reinterpret a score, and adopting it changes no
// scoring behavior. VPSResultPanel/FundraisingReadinessView are NOT
// migrated onto this in this phase (Part 12: limited migration only,
// and neither was named as a migration candidate) -- both keep working
// exactly as they do today; this is the foundation for 10.5+ to build on.
//
// `modeled` is the one non-negotiable prop: when true, the modeled/
// assumption-based caption is ALWAYS rendered and cannot be omitted by a
// caller -- VPS must never be presentable without it (Part 7).
export type ScoreDelta = {
  value: number;
  direction: "positive" | "negative" | "neutral";
};

type ScoreDisplayProps = {
  label: string;
  score: number | null;
  scoreSuffix?: string;
  statusLabel?: string;
  statusTone?: "success" | "warning" | "danger" | "neutral" | "primary";
  delta?: ScoreDelta;
  explanation?: ReactNode;
  modeled?: boolean;
  unavailableText?: string;
  className?: string;
};

const DELTA_CLASSES: Record<ScoreDelta["direction"], string> = {
  positive: "text-movement-positive",
  negative: "text-movement-negative",
  neutral: "text-movement-neutral",
};

const DELTA_ARROW: Record<ScoreDelta["direction"], string> = {
  positive: "▲",
  negative: "▼",
  neutral: "—",
};

export default function ScoreDisplay({
  label,
  score,
  scoreSuffix,
  statusLabel,
  statusTone = "neutral",
  delta,
  explanation,
  modeled = false,
  unavailableText = "Not enough information yet to calculate this score.",
  className = "",
}: ScoreDisplayProps) {
  return (
    <div className={["text-center", className].join(" ")}>
      <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{label}</p>

      {score === null ? (
        <p className="mt-3 text-base font-medium text-text-secondary">{unavailableText}</p>
      ) : (
        <>
          <div className="mt-1 flex items-baseline justify-center gap-2">
            <span className="text-5xl font-bold tracking-tight text-text-primary">
              {score.toFixed(1)}
            </span>
            {scoreSuffix ? (
              <span className="text-sm font-medium text-text-secondary">{scoreSuffix}</span>
            ) : null}
          </div>

          <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
            {statusLabel ? <Badge tone={statusTone}>{statusLabel}</Badge> : null}

            {delta ? (
              <span className={["text-xs font-semibold", DELTA_CLASSES[delta.direction]].join(" ")}>
                {DELTA_ARROW[delta.direction]} {Math.abs(delta.value).toFixed(1)}
              </span>
            ) : null}
          </div>
        </>
      )}

      {/* Phase 31C-B, Part 3/13: a shared primitive feeding VPSResultPanel
          (and any future caller) -- both lines are real one-line score
          explanations a founder needs to read, not metadata, so bumped
          here once rather than at each call site. */}
      {explanation ? <p className="mt-2 text-base leading-7 text-text-secondary">{explanation}</p> : null}

      {modeled ? (
        <p className="mt-2 text-base leading-7 text-text-secondary">
          Based on modeled assumptions — not observed evidence, and not comparable to a real
          company&rsquo;s VentureGPS Score.
        </p>
      ) : null}
    </div>
  );
}
