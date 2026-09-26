"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import PageHeader from "@/components/layout/PageHeader";
import BaseCard from "@/components/ui/BaseCard";
import CompareToggle from "@/components/discovery/CompareToggle";
import CompareSelectionBar from "@/components/discovery/CompareSelectionBar";

import { getSavedStartups, unsaveStartup } from "@/lib/api";
import { useComparisonSelection } from "@/lib/hooks/useComparisonSelection";

import type { SavedStartupEntry } from "@/types";

function formatScore(value: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "--";
  }

  return Number.isInteger(value) ? value.toString() : value.toFixed(1);
}

function getScoreClasses(value: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "bg-surface-muted text-text-muted";
  }

  if (value >= 80) {
    return "bg-success-soft text-success";
  }

  if (value >= 65) {
    return "bg-primary-soft text-primary";
  }

  if (value >= 50) {
    return "bg-warning-soft text-warning";
  }

  return "bg-danger-soft text-danger";
}

// null here means the saved startup currently has no canonical
// (methodology-bearing) analysis at all -- see
// get_saved_startups_for_user()'s docstring. Distinct from a real date
// that merely fails to parse, though both render the same honest label
// rather than a blank cell or a fabricated date.
function formatAnalysisDate(iso: string | null): string {
  if (!iso) {
    return "Not yet analyzed";
  }

  const date = new Date(iso);

  if (Number.isNaN(date.getTime())) {
    return "Not yet analyzed";
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

type LoadState = "loading" | "ready" | "error";

// This page lives behind app/saved/page.tsx's server-side auth.protect(),
// so by the time this component mounts the visitor is already known to
// be signed in -- the isLoaded/isSignedIn checks below are a defensive
// guard for the brief client-side hydration window, not the real gate
// (matching AnalyzeStartupForm.tsx's own defensive re-check pattern).
export default function SavedStartupsView() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [entries, setEntries] = useState<SavedStartupEntry[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const compareSelection = useComparisonSelection();

  useEffect(() => {
    let isMounted = true;

    // Defined and invoked inside the effect (not via useCallback) so
    // every setState call below is reached only through this local
    // function, never as a bare statement in the effect body itself --
    // same pattern app/rankings/page.tsx's loadRankings() already uses
    // (react-hooks/set-state-in-effect).
    async function loadSavedStartups() {
      if (!isLoaded || !isSignedIn) {
        return;
      }

      if (isMounted) {
        setLoadState("loading");
      }

      try {
        const token = await getToken();

        if (!token) {
          if (isMounted) {
            setLoadState("error");
          }
          return;
        }

        const data = await getSavedStartups(token);

        if (isMounted) {
          setEntries(data);
          setLoadState("ready");
        }
      } catch (error) {
        console.error("Failed to load saved startups:", error);

        if (isMounted) {
          setLoadState("error");
        }
      }
    }

    loadSavedStartups();

    return () => {
      isMounted = false;
    };
  }, [isLoaded, isSignedIn, getToken]);

  // Removing here always waits for the backend to confirm before updating
  // the list -- never removes the row optimistically. On failure the row
  // stays exactly where it was, with a message explaining why.
  async function handleRemove(startupId: number) {
    setRemovingId(startupId);
    setRemoveError(null);

    try {
      const token = await getToken();

      if (!token) {
        setRemoveError(
          "Your session expired. Sign in again to remove startups."
        );
        return;
      }

      await unsaveStartup(startupId, token);

      setEntries((current) =>
        current.filter((entry) => entry.startup_id !== startupId)
      );
    } catch {
      setRemoveError("Couldn't remove this startup. Try again.");
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <>
      {/* Phase 10.10, Part 11: title now matches PersonalMenu's own
          "Watchlist" label -- route (/saved) and every internal
          reference are unchanged, presentation only. */}
      <PageHeader
        title="Watchlist"
        subtitle="Startups you're tracking, always shown with their latest Startup Power Score."
        variant="glow"
      />

      {loadState === "loading" ? (
        <div className="h-64 animate-pulse rounded-2xl border border-border bg-surface" />
      ) : loadState === "error" ? (
        <div className="rounded-xl border border-danger/20 bg-danger-soft p-6">
          <h2 className="font-semibold text-danger">
            Unable to load your saved startups
          </h2>

          <p className="mt-2 text-sm text-danger/80">
            Something went wrong loading your list. Try refreshing the page.
          </p>
        </div>
      ) : entries.length === 0 ? (
        <EmptyState />
      ) : (
        <BaseCard className="overflow-hidden">
          {removeError ? (
            <div className="border-b border-border bg-danger-soft px-6 py-3 text-sm text-danger">
              {removeError}
            </div>
          ) : null}

          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead className="bg-surface-muted">
                <tr className="border-b border-border text-left text-xs font-semibold uppercase tracking-wider text-text-muted">
                  <th scope="col" className="min-w-[240px] px-6 py-3.5">
                    Company
                  </th>

                  <th scope="col" className="min-w-[150px] px-6 py-3.5">
                    Industry
                  </th>

                  <th scope="col" className="px-6 py-3.5">
                    Stage
                  </th>

                  <th scope="col" className="px-6 py-3.5">
                    SPS
                  </th>

                  <th scope="col" className="px-6 py-3.5">
                    Latest analysis
                  </th>

                  <th scope="col" className="px-6 py-3.5">
                    <span className="sr-only">Compare</span>
                  </th>

                  <th scope="col" className="px-6 py-3.5 text-right">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-border">
                {entries.map((entry) => (
                  <tr
                    key={entry.startup_id}
                    className="transition-colors hover:bg-surface-muted"
                  >
                    <td className="px-6 py-4">
                      <Link
                        href={`/startup/${encodeURIComponent(entry.company_name)}`}
                        className="font-medium text-text-primary hover:text-primary"
                      >
                        {entry.company_name}
                      </Link>
                    </td>

                    <td className="whitespace-nowrap px-6 py-4 text-text-secondary">
                      {entry.industry || "Not specified"}
                    </td>

                    <td className="whitespace-nowrap px-6 py-4 text-text-secondary">
                      {entry.stage || "Not specified"}
                    </td>

                    <td className="whitespace-nowrap px-6 py-4">
                      <span
                        className={[
                          "inline-flex min-w-12 justify-center rounded-full px-2.5 py-1 text-xs font-semibold",
                          getScoreClasses(entry.overall_score),
                        ].join(" ")}
                      >
                        {formatScore(entry.overall_score)}
                      </span>
                    </td>

                    <td className="whitespace-nowrap px-6 py-4 text-text-secondary">
                      {formatAnalysisDate(entry.latest_analysis_at)}
                    </td>

                    <td className="whitespace-nowrap px-6 py-4">
                      <CompareToggle
                        selected={compareSelection.isSelected(entry.startup_id)}
                        disabled={compareSelection.atMax}
                        onToggle={() => compareSelection.toggle(entry.startup_id)}
                      />
                    </td>

                    <td className="whitespace-nowrap px-6 py-4 text-right">
                      <button
                        type="button"
                        disabled={removingId === entry.startup_id}
                        onClick={() => handleRemove(entry.startup_id)}
                        className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-secondary transition-colors hover:border-danger hover:text-danger disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {removingId === entry.startup_id
                          ? "Removing..."
                          : "Remove"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </BaseCard>
      )}

      <CompareSelectionBar
        selectedIds={compareSelection.selectedIds}
        onClear={compareSelection.clear}
      />
    </>
  );
}

function EmptyState() {
  return (
    <BaseCard className="p-10 text-center">
      <p className="text-lg font-semibold text-text-primary">
        No saved startups yet
      </p>

      <p className="mx-auto mt-2 max-w-md text-base leading-7 text-text-secondary">
        Save a startup from its Startup Profile to track it here — you&rsquo;ll
        always see its latest Startup Power Score, not a snapshot from when
        you saved it.
      </p>

      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/rankings"
          className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
        >
          Browse Rankings
        </Link>

        <Link
          href="/search"
          className="rounded-xl border border-border px-4 py-2.5 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-primary"
        >
          Search Startups
        </Link>
      </div>
    </BaseCard>
  );
}
