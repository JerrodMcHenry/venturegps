import Link from "next/link";

import BaseCard from "@/components/ui/BaseCard";

// VentureGPS Increment 15 -- handles an unknown slug gracefully (Part 1) and a service-unavailable response
// (Part 8) with two distinct, honest messages, following the existing /v/[publicId] precedent of an inline card
// rather than Next's generic notFound() boundary -- this route wants its own on-brand copy, not the app's
// default 404 page.
type MarketNotAvailableProps = {
  reason: "unknown" | "unavailable";
};

export default function MarketNotAvailable({ reason }: MarketNotAvailableProps) {
  return (
    <div className="mx-auto max-w-md px-4 py-20 sm:px-6">
      <BaseCard className="p-10 text-center">
        <h1 className="text-xl font-bold text-text-primary">
          {reason === "unknown" ? "This market isn't on VentureGPS" : "This market isn't available right now"}
        </h1>
        <p className="mt-3 text-sm leading-6 text-text-secondary">
          {reason === "unknown"
            ? "This link may be out of date, or the market may not have been added yet."
            : "VentureGPS couldn't reach the Capital Intelligence data for this market just now. Try again in a moment."}
        </p>
        <Link href="/" className="mt-6 inline-flex text-sm font-semibold text-primary hover:text-primary-hover">
          Go to VentureGPS →
        </Link>
      </BaseCard>
    </div>
  );
}
