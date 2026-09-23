// VentureGPS Increment 16.1 -- every "cinematic image" and "video thumbnail" across all three directions is
// this: a layered CSS radial-gradient composition, never a real or stock photograph. No image asset exists in
// this repo appropriately licensed for a "cinematic robotics" look, and downloading unlicensed stock photography
// for a prototype would be exactly what the brief's "do not imply illustrative imagery depicts actual startups"
// warns against. Every instance carries a visible corner caption so it can never be mistaken for a real photo or
// a real company's imagery, satisfying Data Honesty without needing any image asset at all.
const PALETTES: Record<string, string> = {
  primary: "radial-gradient(120% 120% at 20% 20%, color-mix(in srgb, var(--primary) 55%, transparent), transparent 60%), radial-gradient(100% 100% at 85% 75%, color-mix(in srgb, var(--secondary) 45%, transparent), transparent 55%), var(--background)",
  success: "radial-gradient(120% 120% at 15% 15%, color-mix(in srgb, var(--success) 45%, transparent), transparent 60%), radial-gradient(100% 100% at 90% 80%, color-mix(in srgb, var(--primary) 45%, transparent), transparent 55%), var(--background)",
  accent: "radial-gradient(120% 120% at 80% 20%, color-mix(in srgb, var(--accent) 45%, transparent), transparent 60%), radial-gradient(100% 100% at 15% 85%, color-mix(in srgb, var(--secondary) 45%, transparent), transparent 55%), var(--background)",
};

type PlaceholderArtProps = {
  palette?: keyof typeof PALETTES;
  className?: string;
  caption?: string;
  children?: React.ReactNode;
};

export default function PlaceholderArt({ palette = "primary", className = "", caption = "Prototype placeholder art -- not real imagery", children }: PlaceholderArtProps) {
  return (
    <div
      className={["relative overflow-hidden", className].join(" ")}
      style={{ backgroundImage: PALETTES[palette] }}
    >
      <div className="absolute inset-0 bg-gradient-to-t from-background/40 via-transparent to-transparent" aria-hidden="true" />
      {children}
      <span className="absolute bottom-2 right-2 rounded-full border border-white/25 bg-black/35 px-2 py-0.5 text-[10px] font-medium text-white/80 backdrop-blur-sm">
        {caption}
      </span>
    </div>
  );
}
