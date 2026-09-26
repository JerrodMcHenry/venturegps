type RingCenterProps = {
  // Phase 10.9, Part 15: null renders "—" (never "0.0") plus
  // unavailableLabel underneath -- an unavailable score must be visually
  // unmistakable from a real, low, legitimately-scored one.
  score: number | null;
  unavailableLabel?: string;
  label?: string;
  grade?: string;
  compact?: boolean;
};

export default function RingCenter({
  score,
  unavailableLabel,
  label,
  grade,
  compact = false,
}: RingCenterProps) {
  if (score === null) {
    if (compact) {
      return (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-bold tracking-tight text-text-muted">—</span>
        </div>
      );
    }

    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-4">
        <span className="text-5xl font-bold tracking-tight text-text-muted">—</span>
        {/* Phase 31C-A -- Global Founder UX Acceptance, Part 1/6:
            live-discovered on the founder workspace and public profile --
            "SPS" appeared bare, with no expansion anywhere near the ring
            itself, unlike VPS's own "VENTURE POTENTIAL SCORE" eyebrow
            treatment elsewhere in the product. Spelled out (at a
            deliberately smaller size to still fit the ring's fixed
            diameter -- Part 8's own "constrained UI label" exception) so
            a first-time founder never has to already know the acronym.
            Portfolio Release Task 6 -- Standardize User-Facing
            Terminology: "Startup Power Score" -> "VentureGPS Score"
            (the one canonical name for this number everywhere it's
            shown -- Rankings, Compare, the startup report). SIE remains
            the internal engine name; this is the product's own score. */}
        <span className="mt-1 max-w-[7rem] text-xs font-medium leading-tight text-text-secondary">
          VentureGPS Score
        </span>
        {unavailableLabel ? (
          <span className="mt-2 text-xs text-text-muted">{unavailableLabel}</span>
        ) : null}
      </div>
    );
  }

  if (compact) {
    return (
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-sm font-bold tracking-tight text-text-primary">
          {score.toFixed(1)}
        </span>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
      <span className="text-5xl font-bold tracking-tight text-text-primary">
        {score.toFixed(1)}
      </span>

      {/* Phase 31C-A -- Global Founder UX Acceptance, Part 1/6: see the
          matching comment in the Unavailable branch above for the full
          reasoning -- "SPS" spelled out, sized to still fit the ring.
          Portfolio Release Task 6: "Startup Power Score" -> "VentureGPS
          Score" (see that same comment for the full rationale). */}
      <span className="mt-1 max-w-[7rem] text-xs font-medium leading-tight text-text-secondary">
        VentureGPS Score
      </span>

      {grade ? (
        <span className="mt-2 text-sm font-semibold text-text-primary">
          {grade}
        </span>
      ) : null}

      {label ? (
        <span className="mt-1 text-xs text-text-muted">{label}</span>
      ) : null}
    </div>
  );
}
