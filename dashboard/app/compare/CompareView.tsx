"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import BaseCard from "@/components/ui/BaseCard";
import ComparisonHeader from "@/components/compare/ComparisonHeader";
import PillarComparisonTable from "@/components/compare/PillarComparisonTable";
import KeyDifferencesPanel from "@/components/compare/KeyDifferencesPanel";
import PillarDetailAccordion from "@/components/compare/PillarDetailAccordion";

import { compareStartups } from "@/lib/api";

import type { ComparisonStartup } from "@/types";

const MIN_COMPARE = 2;
const MAX_COMPARE = 4;

// Graceful URL parsing (Part 5): non-numeric tokens are dropped, not an
// error; duplicates are removed; anything past MAX_COMPARE is silently
// bounded, not rejected -- an old/shared link with too many ids still
// produces a usable comparison of the first four.
function parseStartupIds(raw: string | null): number[] {
  if (!raw) {
    return [];
  }

  const tokens = raw
    .split(",")
    .map((token) => token.trim())
    .filter(Boolean);

  const parsed: number[] = [];

  for (const token of tokens) {
    const value = Number(token);

    if (Number.isInteger(value) && value > 0 && !parsed.includes(value)) {
      parsed.push(value);
    }
  }

  return parsed.slice(0, MAX_COMPARE);
}

type LoadState = "loading" | "ready" | "error";

export default function CompareView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const requestedIds = parseStartupIds(searchParams.get("startups"));
  const requestedIdsKey = requestedIds.join(",");

  const [startups, setStartups] = useState<ComparisonStartup[]>([]);
  const [missingIds, setMissingIds] = useState<number[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  // Portfolio Release Task 3B -- Secure Analysis Visibility: GET /compare
  // now requires auth and resolves only startup_ids this caller is
  // authorized to see (approved decision -- explicit IDs must not bypass
  // authorization).
  const { getToken } = useAuth();

  useEffect(() => {
    let isMounted = true;

    async function loadComparison() {
      if (requestedIds.length < MIN_COMPARE) {
        if (isMounted) {
          setStartups([]);
          setMissingIds([]);
          setLoadState("ready");
        }
        return;
      }

      if (isMounted) {
        setLoadState("loading");
      }

      try {
        const token = await getToken();
        const response = await compareStartups(requestedIds, token);

        if (isMounted) {
          setStartups(response.startups);
          setMissingIds(response.missing_startup_ids);
          setLoadState("ready");
        }
      } catch (error) {
        console.error("Failed to load comparison:", error);

        if (isMounted) {
          setLoadState("error");
        }
      }
    }

    loadComparison();

    return () => {
      isMounted = false;
    };
    // requestedIdsKey is the real dependency (a stable string derived from
    // the URL); requestedIds itself is a fresh array every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedIdsKey, getToken]);

  function removeStartup(startupId: number) {
    const remaining = requestedIds.filter((id) => id !== startupId);

    router.push(
      remaining.length > 0
        ? `${pathname}?startups=${remaining.join(",")}`
        : pathname
    );
  }

  if (requestedIds.length < MIN_COMPARE) {
    return <SetupState />;
  }

  if (loadState === "loading") {
    return <LoadingState />;
  }

  if (loadState === "error") {
    return <ErrorState />;
  }

  if (startups.length < MIN_COMPARE) {
    return (
      <NotEnoughResolvedState
        resolvedCount={startups.length}
        requestedCount={requestedIds.length}
        missingIds={missingIds}
      />
    );
  }

  return (
    <div className="space-y-10">
      {missingIds.length > 0 ? (
        <div className="rounded-xl border border-warning/20 bg-warning-soft px-4 py-3 text-sm text-warning">
          {missingIds.length === 1
            ? `Startup #${missingIds[0]} couldn't be compared -- it has no canonical intelligence yet.`
            : `Startups ${missingIds.join(", ")} couldn't be compared -- they have no canonical intelligence yet.`}
        </div>
      ) : null}

      <ComparisonHeader startups={startups} onRemove={removeStartup} />
      <PillarComparisonTable startups={startups} />
      <KeyDifferencesPanel startups={startups} />
      <PillarDetailAccordion startups={startups} />
    </div>
  );
}

function SetupState() {
  return (
    <BaseCard className="p-10 text-center">
      <p className="text-lg font-semibold text-text-primary">
        Select 2–4 startups to compare
      </p>

      <p className="mx-auto mt-2 max-w-md text-base leading-7 text-text-secondary">
        Head to Discovery or your Saved Startups, check &ldquo;Compare&rdquo;
        on the companies you&rsquo;re weighing against each other, then come
        back here.
      </p>

      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/search"
          className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
        >
          Go to Discovery
        </Link>

        <Link
          href="/saved"
          className="rounded-xl border border-border px-4 py-2.5 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-primary"
        >
          Go to Saved Startups
        </Link>
      </div>
    </BaseCard>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="h-48 animate-pulse rounded-2xl border border-border bg-surface"
          />
        ))}
      </div>

      <div className="h-64 animate-pulse rounded-2xl border border-border bg-surface" />
    </div>
  );
}

function ErrorState() {
  return (
    <div className="rounded-xl border border-danger/20 bg-danger-soft p-6">
      <h2 className="font-semibold text-danger">Unable to load comparison</h2>

      <p className="mt-2 text-sm text-danger/80">
        Something went wrong loading these startups. Try refreshing the page.
      </p>
    </div>
  );
}

function NotEnoughResolvedState({
  resolvedCount,
  requestedCount,
  missingIds,
}: {
  resolvedCount: number;
  requestedCount: number;
  missingIds: number[];
}) {
  return (
    <BaseCard className="p-10 text-center">
      <p className="text-lg font-semibold text-text-primary">
        Not enough startups to compare
      </p>

      <p className="mx-auto mt-2 max-w-md text-base leading-7 text-text-secondary">
        {resolvedCount === 0
          ? `None of the ${requestedCount} requested startups have canonical intelligence yet.`
          : `Only ${resolvedCount} of ${requestedCount} requested startups have canonical intelligence -- at least 2 are needed to compare.`}
        {missingIds.length > 0 ? ` (IDs not found: ${missingIds.join(", ")}.)` : ""}
      </p>

      <Link
        href="/search"
        className="mt-6 inline-flex rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
      >
        Go to Discovery
      </Link>
    </BaseCard>
  );
}
