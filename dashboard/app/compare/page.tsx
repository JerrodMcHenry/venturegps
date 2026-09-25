import { Suspense } from "react";
import { auth } from "@clerk/nextjs/server";

import PageHeader from "@/components/layout/PageHeader";

import CompareView from "./CompareView";

// Portfolio Release Task 3B -- Secure Analysis Visibility supersedes this
// route's original "public, no auth gate" comment (approved decision --
// no public scores-only exception). auth.protect() is the same real,
// resource-based, server-side gate used throughout this app; GET /compare
// on the backend enforces its own auth AND resolves explicit startup_ids
// only if the caller is authorized for them, independently either way.
// CompareView reads comparison state from the URL via useSearchParams(),
// a Client Component hook -- same Suspense-boundary reasoning as
// app/search/page.tsx.
export default async function ComparePage() {
  await auth.protect();

  return (
    <>
      <PageHeader
        title="Compare Startups"
        subtitle="See how SIE's canonical intelligence differs across startups, pillar by pillar."
      />

      <Suspense
        fallback={
          <div className="h-96 animate-pulse rounded-2xl border border-border bg-surface" />
        }
      >
        <CompareView />
      </Suspense>
    </>
  );
}
