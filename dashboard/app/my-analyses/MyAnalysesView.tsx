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

import { getMyAnalyses, getMyEvidenceV1Analyses } from "@/lib/api";

import type { EvidenceV1MyAnalysisEntry, MyAnalysisEntry } from "@/types";

// Portfolio Release Task 4 -- My Analyses, Phase 3. Client Component for
// the same reason RankingsView.tsx already is: real interactive loading/
// error state, a real Clerk token via useAuth().getToken() (this stays a
// Client Component rendered by page.tsx's own server-side auth.protect()
// wrapper). GET /me/analyses is strictly submitted_by_user_id = this
// caller -- no bookmark, no startup membership, and no admin bypass ever
// surfaces someone else's analysis here (see app/database/db.py's
// get_my_analyses() docstring), so this list is always safe to render in
// full without a second per-row authorization check.
//
// Task 31 item 18 -- extended to ALSO fetch GET /me/analyses/evidence-v1
// (ownership-scoped the same way) and merge the two lists by date. The
// two engines' rows are never rendered as the same kind of thing: a
// legacy row shows its overall score; an Evidence v1 row shows Coverage
// with its own distinct badge and links to /evidence/{id}, never
// /startup/{name} -- item 18's own explicit "do not compare Evidence-v1
// Coverage to legacy overall score as though they mean the same thing."
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

type CombinedEntry =
  | { kind: "legacy"; created_at: string; data: MyAnalysisEntry }
  | { kind: "evidence_v1"; created_at: string; data: EvidenceV1MyAnalysisEntry };

export default function MyAnalysesView() {
  const { getToken } = useAuth();
  const [legacyAnalyses, setLegacyAnalyses] = useState<MyAnalysisEntry[]>([]);
  const [evidenceV1Analyses, setEvidenceV1Analyses] = useState<EvidenceV1MyAnalysisEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      try {
        setIsLoading(true);
        setError(null);

        const token = await getToken();
        // Independent lists, independent failure modes -- a failure on
        // one must never hide the other (Evidence v1 is a newer, smaller
        // surface; a transient issue there shouldn't blank out a user's
        // entire legacy history, and vice versa).
        const [legacy, evidenceV1] = await Promise.all([
          getMyAnalyses(token),
          getMyEvidenceV1Analyses(token).catch((err) => {
            console.error("Failed to load Evidence v1 analyses:", err);
            return [] as EvidenceV1MyAnalysisEntry[];
          }),
        ]);

        if (isMounted) {
          setLegacyAnalyses(legacy);
          setEvidenceV1Analyses(evidenceV1);
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

  const combined: CombinedEntry[] = [
    ...legacyAnalyses.map((data): CombinedEntry => ({ kind: "legacy", created_at: data.created_at, data })),
    ...evidenceV1Analyses.map((data): CombinedEntry => ({ kind: "evidence_v1", created_at: data.created_at, data })),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

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
      ) : combined.length === 0 ? (
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
          {combined.map((entry) => {
            if (entry.kind === "legacy") {
              const href = entry.data.company_name
                ? `/startup/${encodeURIComponent(entry.data.company_name)}`
                : null;

              const card = (
                <BaseCard className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:border-primary/40">
                  <div className="min-w-0">
                    <p className="truncate text-base font-semibold text-text-primary">
                      {entry.data.company_name ?? "Untitled analysis"}
                    </p>
                    <p className="mt-0.5 text-sm text-text-secondary">{formatDate(entry.data.created_at)}</p>
                  </div>

                  <span
                    className={[
                      "inline-flex shrink-0 items-center rounded-full border px-3 py-1 text-sm font-bold",
                      scoreBadgeClasses(entry.data.overall_score),
                    ].join(" ")}
                  >
                    {formatScore(entry.data.overall_score)}
                  </span>
                </BaseCard>
              );

              return href ? (
                <Link key={`legacy-${entry.data.analysis_id}`} href={href} className="block">
                  {card}
                </Link>
              ) : (
                <div key={`legacy-${entry.data.analysis_id}`}>{card}</div>
              );
            }

            // Evidence v1: a distinct badge (Coverage %, never compared to
            // a legacy 0-100 score) and a distinct link target.
            return (
              <Link
                key={`evidence-v1-${entry.data.analysis_id}`}
                href={`/evidence/${encodeURIComponent(entry.data.analysis_id)}`}
                className="block"
              >
                <BaseCard className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:border-primary/40">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-base font-semibold text-text-primary">
                        {entry.data.company_name}
                      </p>
                      <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-primary">
                        Evidence v1
                      </span>
                    </div>
                    <p className="mt-0.5 text-sm text-text-secondary">{formatDate(entry.data.created_at)}</p>
                  </div>

                  <div className="flex shrink-0 flex-col items-end gap-0.5">
                    <span className="inline-flex items-center rounded-full border border-border bg-surface-subtle px-3 py-1 text-sm font-bold text-text-primary">
                      {entry.data.company_coverage_pct == null
                        ? "Coverage --"
                        : `Coverage ${entry.data.company_coverage_pct.toFixed(0)}%`}
                    </span>
                    <span className="text-xs text-text-tertiary">{entry.data.company_confidence ?? "Unknown"} confidence</span>
                  </div>
                </BaseCard>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
