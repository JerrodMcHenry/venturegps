import Link from "next/link";

// VentureGPS Increment 16.1 -- the unmissable, first-thing-on-the-page prototype label, parameterized by
// direction name/letter so all three concepts (plus the comparison page) share identical wording and placement
// discipline rather than three hand-tuned banners drifting apart. Same reasoning as Increment 16's
// PrototypeBanner.tsx, generalized.
type PrototypeRibbonProps = {
  // Omit `letter` for a non-direction page (the comparison page itself) -- renders "Design prototype — <name>"
  // rather than the awkward "Direction —: Comparison" a placeholder letter would produce.
  letter?: string;
  name: string;
};

export default function PrototypeRibbon({ letter, name }: PrototypeRibbonProps) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-dashed border-warning/40 bg-warning-soft px-4 py-2.5 text-center text-sm font-medium text-warning sm:px-6">
      <span>
        Design prototype &mdash; {letter ? `Direction ${letter}: ${name}` : name} &middot; Not production &middot; Sample data throughout
      </span>
      <Link href="/design/directions" className="underline underline-offset-2 hover:text-warning/80">
        Compare all three concepts
      </Link>
    </div>
  );
}
