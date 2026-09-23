import Link from "next/link";

// VentureGPS Increment 16.2 (hero refinement) -- replaces the shared PrototypeRibbon banner for THIS route
// only. The full-width yellow banner ate real vertical space at the very top of a hero whose entire point is
// "don't leave any of the first viewport looking like anything but the finished product" -- a small, fixed,
// corner-anchored disclaimer says the same thing without competing with the composition. PrototypeRibbon.tsx
// itself is untouched and still used by every other /design/* route (Increment 16/16.1's prototypes).
export default function CinematicPrototypeDisclaimer() {
  return (
    <div className="fixed bottom-3 left-3 z-50 flex items-center gap-2 rounded-full border border-white/15 bg-black/50 px-3 py-1.5 text-[11px] font-medium text-white/70 backdrop-blur-md">
      <span aria-hidden="true" className="size-1.5 rounded-full bg-warning" />
      Prototype &mdash; not production
      <Link href="/design/directions" className="underline underline-offset-2 hover:text-white">
        Compare concepts
      </Link>
    </div>
  );
}
