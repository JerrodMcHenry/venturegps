"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import PageHeader from "@/components/layout/PageHeader";
import BaseCard from "@/components/ui/BaseCard";
import EmptyState from "@/components/ui/EmptyState";
import ErrorMessage from "@/components/ui/ErrorMessage";
import Skeleton from "@/components/ui/Skeleton";
import { getSPSMetadata } from "@/components/sps/utils/scoreMetadata";

import { getMyAnalyses } from "@/lib/api";

import type { MyAnalysisEntry } from "@/types";

// Portfolio Release Task 4 -- My Analyses, Phase 3. Client Component for
// the same reason RankingsView.tsx already is: real interactive loading/
// error state, a real Clerk token via useAuth().getToken() (this stays a
// Client Component rendered by page.tsx's own server-side auth.protect()
// wrapper). GET /me/analyses is strictly submitted_by_user_id = this
// caller -- no bookmark, no startup membership, and no admin bypass ever
// surfaces someone else's analysis here (see app/database/db.py's
// get_my_analyses() docstring), so this list is always safe to render in
// full without a second per-row authorization check.
function formatScore(value: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "--";
  }

  return Number.isInteger(value) ? value.toString() : value.toFixed(1);
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function scoreBadgeClasses(score: number | null): string {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return "border-border bg-surface-muted text-text-muted";
  }

  const metadata = getSPSMetadata(score);
  return `border-transparent ${metadata.backgroundClass} ${metadata.textClass}`;
}

export default function MyAnalysesView() {
  const { getToken } = useAuth();
  const [analyses, setAnalyses] = useState<MyAnalysisEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      try {
        setIsLoading(true);
        setError(null);

        const token = await getToken();
        const data = await getMyAnalyses(token);

        if (isMounted) {
          setAnalyses(data);
        }
      } catch (err) {
        console.error("Failed to load My Analyses:", err);

        if (isMounted) {
          setError("Your analyses could not be loaded.");
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    load();

    return () => {
      isMounted = false;
    };
  }, [getToken]);

  return (
    <>
      <PageHeader
        title="My Analyses"
        subtitle="Every startup you've submitted for evidence-backed analysis, newest first."
        variant="glow"
      />

      {isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : error ? (
        <ErrorMessage>
          <h2 className="font-semibold text-danger">Unable to load your analyses</h2>
          <p className="mt-2 text-sm text-danger/80">{error}</p>
        </ErrorMessage>
      ) : analyses.length === 0 ? (
        <EmptyState
          title="You haven't analyzed a startup yet"
          description="Submit a company's pitch deck, website, or a plain description and get a defensible, evidence-backed analysis in minutes."
          action={
            <Link
              href="/analyze"
              className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
            >
              Analyze a startup
            </Link>
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          {analyses.map((entry) => {
            const href = entry.company_name ? `/startup/${encodeURIComponent(entry.company_name)}` : null;

            const card = (
              <BaseCard className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:border-primary/40">
                <div className="min-w-0">
                  <p className="truncate text-base font-semibold text-text-primary">
                    {entry.company_name ?? "Untitled analysis"}
                  </p>
                  <p className="mt-0.5 text-sm text-text-secondary">{formatDate(entry.created_at)}</p>
                </div>

                <span
                  className={[
                    "inline-flex shrink-0 items-center rounded-full border px-3 py-1 text-sm font-bold",
                    scoreBadgeClasses(entry.overall_score),
                  ].join(" ")}
                >
                  {formatScore(entry.overall_score)}
                </span>
              </BaseCard>
            );

            return href ? (
              <Link key={entry.analysis_id} href={href} className="block">
                {card}
              </Link>
            ) : (
              <div key={entry.analysis_id}>{card}</div>
            );
          })}
        </div>
      )}
    </>
  );
}
