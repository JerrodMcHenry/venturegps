import { Skeleton, SkeletonLines } from "@/components/ui/Skeleton";

// Shown while the server component in page.tsx awaits its data (Next's loading.js file convention) -- perceived
// performance (Increment 15 Part 8) for a visitor arriving from a slow mobile connection off a video link.
export default function MarketPageLoading() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading market…</span>
      <Skeleton className="h-4 w-32" />
      <Skeleton className="mt-4 h-12 w-2/3" />
      <SkeletonLines count={2} className="mt-6 max-w-xl" />
      <Skeleton className="mt-8 h-56 w-full" />
      <SkeletonLines count={4} className="mt-8" />
    </div>
  );
}
