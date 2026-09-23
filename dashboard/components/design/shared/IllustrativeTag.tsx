// VentureGPS Increment 16.1 -- one shared "this is illustrative" chip, reused across all three visual
// directions so the data-honesty labeling never drifts in wording between them. Two variants: `default` (solid,
// for use on a light/neutral surface) and `inverted` (for use directly on a dark/cinematic full-bleed
// background, where the default surface-tinted treatment would be invisible).
type IllustrativeTagProps = {
  variant?: "default" | "inverted";
  children?: React.ReactNode;
};

export default function IllustrativeTag({ variant = "default", children = "Illustrative" }: IllustrativeTagProps) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        variant === "inverted" ? "border-white/30 bg-black/30 text-white/80 backdrop-blur-sm" : "border-dashed border-border text-text-muted",
      ].join(" ")}
    >
      <span aria-hidden="true" className={["size-1.5 rounded-full", variant === "inverted" ? "bg-white/60" : "bg-text-muted"].join(" ")} />
      {children}
    </span>
  );
}
