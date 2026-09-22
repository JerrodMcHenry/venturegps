// VentureGPS Increment 15. One shared, reusable pill for a Capital Signal direction (or a Capital Concentration
// trend) -- the hero's overall status and every "how this compares historically" row in the Explore section all
// render through this, so the visual vocabulary (symbol, color, wording) can never drift between them.
//
// Deliberately NOT built on Badge.tsx: Badge's tones are a closed enum (success/warning/danger/...) that has no
// slot for "mixed" (a genuine disagreement between components, not a warning) or "unknown" (missing history, not
// a bad reading) without overloading an existing tone's meaning. This stays a small, purpose-built sibling
// instead, reusing Badge's pill shape/sizing conventions by hand.
import type { SignalTone } from "@/lib/api/v2/signalLabels.ts";

const TONE_CLASSES: Record<SignalTone, string> = {
  positive: "bg-success-soft text-success",
  negative: "bg-danger-soft text-danger",
  neutral: "bg-surface-muted text-text-secondary",
  mixed: "bg-info-soft text-info",
  unknown: "border border-dashed border-border bg-transparent text-text-muted",
};

type DirectionBadgeProps = {
  symbol: string;
  label: string;
  tone: SignalTone;
  size?: "sm" | "md";
  className?: string;
};

export default function DirectionBadge({ symbol, label, tone, size = "md", className = "" }: DirectionBadgeProps) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-full font-semibold",
        size === "md" ? "px-3 py-1.5 text-sm" : "px-2.5 py-1 text-sm",
        TONE_CLASSES[tone],
        className,
      ].join(" ")}
    >
      {/* the arrow/dash glyph is decorative -- the label text already carries the full meaning for screen
          readers, so the symbol is hidden from the accessibility tree rather than announced twice. */}
      <span aria-hidden="true">{symbol}</span>
      {label}
    </span>
  );
}
