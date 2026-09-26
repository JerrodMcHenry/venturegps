import { Suspense } from "react";
import Link from "next/link";
import { auth } from "@clerk/nextjs/server";

import PageHeader from "@/components/layout/PageHeader";

import DiscoveryView from "./DiscoveryView";

// Startup Discovery V1: /search redesigned in place from a basic
// company-name lookup into the primary startup-discovery experience --
// same route, no new /discover page (per the product decision to keep
// Search and Rankings as the only two browse routes). DiscoveryView reads
// filter state from the URL via useSearchParams(), a Client Component
// hook -- Next's own docs recommend wrapping the component that calls it
// in <Suspense>, so a route that could otherwise be static isn't forced
// fully client-rendered up to the root.
//
// Portfolio Release Task 3B -- Secure Analysis Visibility: Discovery is no
// longer public (approved decision -- no public scores-only exception).
// auth.protect() is the same real, resource-based, server-side gate used
// throughout this app; GET /discover on the backend enforces its own auth
// independently either way.
export default async function SearchPage() {
  await auth.protect();

  return (
    <>
      <PageHeader
        title="Discover Startups"
        subtitle="Browse the canonical Startup Intelligence Engine universe -- filter by industry, stage, and VentureGPS Score to find companies worth a closer look."
        action={
          <Link
            href="/rankings"
            className="text-sm font-semibold text-primary hover:text-primary-hover"
          >
            View rankings →
          </Link>
        }
      />

      <Suspense
        fallback={
          <div className="h-96 animate-pulse rounded-2xl border border-border bg-surface" />
        }
      >
        <DiscoveryView />
      </Suspense>
    </>
  );
}
