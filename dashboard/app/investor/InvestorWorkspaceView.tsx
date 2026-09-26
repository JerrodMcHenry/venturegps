"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import PageHeader from "@/components/layout/PageHeader";
import BaseCard from "@/components/ui/BaseCard";
import { SPSRing } from "@/components/sps";
import CompareToggle from "@/components/discovery/CompareToggle";
import CompareSelectionBar from "@/components/discovery/CompareSelectionBar";

import { getInvestorWorkspace, unsaveStartup } from "@/lib/api";
import { useComparisonSelection } from "@/lib/hooks/useComparisonSelection";

import type { InvestorWorkspace, WatchedStartup } from "@/types";

type LoadState = "loading" | "ready" | "error";

function formatScore(value: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "—";
  }
  return Number.isInteger(value) ? value.toString() : value.toFixed(1);
}

function formatDate(iso: string | null): string {
  if (!iso) {
    return "Not yet analyzed";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "Not yet analyzed";
  }
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// Phase 9 -- Investor Workspace V1. The intelligence layer on top of
// Saved Startups (which remains the underlying watchlist relationship --
// this page never creates a competing concept). Everything shown here is
// read from GET /investor/workspace, itself a deterministic re-derivation
// of canonical intelligence (see app/ai/investor_workspace.py's module
// docstring) -- nothing on this page writes to SPS/methodology, and
// nothing here is a portfolio: these are startups the user is watching,
// not startups they own.
export default function InvestorWorkspaceView() {
  const { getToken } = useAuth();

  const [workspace, setWorkspace] = useState<InvestorWorkspace | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const compareSelection = useComparisonSelection();

  useEffect(() => {
    let isMounted = true;

    async function load() {
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

        const data = await getInvestorWorkspace(token);

        if (isMounted) {
          setWorkspace(data);
          setLoadState("ready");
        }
      } catch (error) {
        console.error("Failed to load Investor Workspace:", error);
        if (isMounted) {
          setLoadState("error");
        }
      }
    }

    load();

    return () => {
      isMounted = false;
    };
  }, [getToken]);

  async function handleUnsave(startupId: number) {
    setRemovingId(startupId);
    setRemoveError(null);

    try {
      const token = await getToken();

      if (!token) {
        setRemoveError("Your session expired. Sign in again to remove startups.");
        return;
      }

      await unsaveStartup(startupId, token);

      setWorkspace((current) => {
        if (!current) {
          return current;
        }

        const remaining = current.watched_startups.filter((w) => w.startup_id !== startupId);

        return {
          ...current,
          watched_startups: remaining,
          recent_changes: current.recent_changes.filter((c) => c.startup_id !== startupId),
          attention_items: current.attention_items.filter((a) => a.startup_id !== startupId),
          overview: { ...current.overview, watched_count: current.overview.watched_count - 1 },
        };
      });
    } catch {
      setRemoveError("Couldn't remove this startup. Try again.");
    } finally {
      setRemovingId(null);
    }
  }

  if (loadState === "loading") {
    return (
      <div className="space-y-6">
        <div className="h-24 animate-pulse rounded-2xl border border-border bg-surface" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-64 animate-pulse rounded-2xl border border-border bg-surface" />
          ))}
        </div>
      </div>
    );
  }

  if (loadState === "error" || !workspace) {
    return (
      <div className="rounded-xl border border-danger/20 bg-danger-soft p-6">
        <h2 className="font-semibold text-danger">Unable to load Investor Workspace</h2>
        <p className="mt-2 text-sm text-danger/80">Try refreshing the page.</p>
      </div>
    );
  }

  const { overview, watched_startups: watchedStartups, recent_changes: recentChanges, attention_items: attentionItems } = workspace;

  return (
    <>
      {/* Phase 10.10, Part 11: title now matches PersonalMenu's own
          "Investor intelligence" label -- route (/investor) and every
          internal reference are unchanged, presentation only. */}
      <PageHeader
        title="Investor Intelligence"
        subtitle="What's happening across the startups you're tracking."
      />

      {watchedStartups.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-8">
          <OverviewRow overview={overview} />

          <AttentionSection items={attentionItems} />

          <RecentChangesSection changes={recentChanges} />

          {removeError ? (
            <p className="text-sm text-danger">{removeError}</p>
          ) : null}

          <section>
            <h2 className="text-xl font-semibold text-text-primary">Watched Startups</h2>

            <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {watchedStartups.map((watched) => (
                <WatchedStartupCard
                  key={watched.startup_id}
                  watched={watched}
                  compareSelected={compareSelection.isSelected(watched.startup_id)}
                  compareDisabled={compareSelection.atMax}
                  onToggleCompare={() => compareSelection.toggle(watched.startup_id)}
                  onUnsave={() => handleUnsave(watched.startup_id)}
                  removing={removingId === watched.startup_id}
                />
              ))}
            </div>
          </section>
        </div>
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
        Investor Workspace becomes useful once you&apos;re watching a few startups
      </p>

      <p className="mx-auto mt-2 max-w-md text-base leading-7 text-text-secondary">
        Save a startup from its profile, Rankings, or Search to start tracking
        it here -- you&apos;ll see its current VentureGPS Score, what
        changed since the last analysis, and what deserves attention.
      </p>

      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/search"
          className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
        >
          Discover Startups
        </Link>

        <Link
          href="/rankings"
          className="rounded-xl border border-border px-4 py-2.5 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-primary"
        >
          Browse Rankings
        </Link>
      </div>
    </BaseCard>
  );
}

// Part 3: only metrics honestly computable from real saved-startup data.
// No portfolio returns, no valuation changes, no "hotness" -- see
// app/ai/investor_workspace.py's InvestorOverview for what backs each of
// these.
function OverviewRow({ overview }: { overview: InvestorWorkspace["overview"] }) {
  const stats: { label: string; value: string }[] = [
    { label: "Watched startups", value: String(overview.watched_count) },
    {
      label: "Average current SPS",
      value: overview.average_current_sps !== null ? formatScore(overview.average_current_sps) : "—",
    },
    { label: "Improved", value: String(overview.improved_count) },
    { label: "Declined", value: String(overview.declined_count) },
    { label: "Recently analyzed", value: String(overview.recently_analyzed_count) },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {stats.map((stat) => (
        <BaseCard key={stat.label} className="p-4 text-center">
          <p className="text-2xl font-bold text-text-primary">{stat.value}</p>
          <p className="mt-1 text-xs text-text-muted">{stat.label}</p>
        </BaseCard>
      ))}
    </div>
  );
}

// Part 7: every reason is the actual triggering fact -- never a hidden
// "Risk Score: 74". Honest empty state when nothing currently qualifies.
function AttentionSection({ items }: { items: InvestorWorkspace["attention_items"] }) {
  return (
    <section>
      <h2 className="text-xl font-semibold text-text-primary">Needs Attention</h2>

      {items.length === 0 ? (
        <BaseCard className="mt-4 p-5">
          <p className="text-sm text-text-secondary">
            Nothing needs attention right now -- no meaningful declines, stale
            analyses, or low-confidence intelligence among your watched startups.
          </p>
        </BaseCard>
      ) : (
        <div className="mt-4 space-y-2">
          {items.map((item, index) => (
            <BaseCard key={`${item.startup_id}-${index}`} className="flex flex-wrap items-center justify-between gap-2 border-warning/30 p-4">
              <div>
                <Link
                  href={`/startup/${encodeURIComponent(item.company_name)}`}
                  className="text-sm font-semibold text-text-primary hover:text-primary"
                >
                  {item.company_name}
                </Link>
                <p className="mt-0.5 text-sm text-text-secondary">{item.reason}</p>
              </div>
            </BaseCard>
          ))}
        </div>
      )}
    </section>
  );
}

// Part 6: restrained, threshold-filtered, and never fabricated. Empty
// state is explicit, not a hidden section.
function RecentChangesSection({ changes }: { changes: InvestorWorkspace["recent_changes"] }) {
  return (
    <section>
      <h2 className="text-xl font-semibold text-text-primary">Recent Changes</h2>

      {changes.length === 0 ? (
        <BaseCard className="mt-4 p-5">
          <p className="text-sm text-text-secondary">
            No meaningful changes since the previous analysis for any watched
            startup yet.
          </p>
        </BaseCard>
      ) : (
        <BaseCard className="mt-4 divide-y divide-border p-0">
          {changes.map((change, index) => (
            <div key={index} className="flex items-center gap-3 px-5 py-3.5">
              <span
                aria-hidden="true"
                className={[
                  "text-sm font-bold",
                  change.direction === "up" ? "text-success" : "text-danger",
                ].join(" ")}
              >
                {change.direction === "up" ? "↑" : "↓"}
              </span>
              <p className="text-sm text-text-primary">{change.statement}</p>
            </div>
          ))}
        </BaseCard>
      )}
    </section>
  );
}

function PillarMiniRow({ pillars }: { pillars: WatchedStartup["pillars"] }) {
  return (
    <div className="grid grid-cols-3 gap-x-2 gap-y-2 border-t border-border pt-3 text-center text-xs sm:grid-cols-6">
      {pillars.map((pillar) => (
        <div key={pillar.pillar}>
          <p className="truncate text-text-muted" title={pillar.label}>
            {pillar.label.split(" ")[0]}
          </p>
          <p className="font-semibold text-text-secondary">
            {pillar.current_score !== null ? pillar.current_score.toFixed(1) : "—"}
          </p>
          {pillar.delta !== null ? (
            <p className={pillar.delta > 0 ? "text-success" : pillar.delta < 0 ? "text-danger" : "text-text-muted"}>
              {pillar.delta > 0 ? "+" : ""}
              {pillar.delta.toFixed(1)}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function WatchedStartupCard({
  watched,
  compareSelected,
  compareDisabled,
  onToggleCompare,
  onUnsave,
  removing,
}: {
  watched: WatchedStartup;
  compareSelected: boolean;
  compareDisabled: boolean;
  onToggleCompare: () => void;
  onUnsave: () => void;
  removing: boolean;
}) {
  const profileHref = `/startup/${encodeURIComponent(watched.company_name)}`;

  return (
    <BaseCard className="flex flex-col gap-4 p-5 transition-colors hover:border-primary/40">
      <div className="flex items-start justify-between gap-3">
        <Link href={profileHref} className="group min-w-0">
          <h3 className="truncate text-lg font-semibold text-text-primary transition-colors group-hover:text-primary">
            {watched.company_name}
          </h3>
          <p className="mt-1 text-xs text-text-muted">
            {watched.has_canonical_analysis ? `Analyzed ${formatDate(watched.latest_analysis_at)}` : "Not yet analyzed"}
          </p>
        </Link>

        {watched.has_canonical_analysis ? (
          // Phase 10.9, Part 15: SPSRing now renders null as its own
          // honest "unavailable" state -- current_sps is typed
          // number | null, so coercing to 0 here would draw a real,
          // scored-zero-looking ring for a canonical analysis that
          // simply has no score yet.
          <SPSRing
            score={watched.current_sps}
            trend={watched.has_multiple_analyses ? (watched.sps_delta ?? undefined) : undefined}
            size="xs"
            showDetails={false}
          />
        ) : (
          <div
            role="img"
            aria-label="Score not yet available"
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-2 border-dashed border-border"
          >
            <span className="text-xs font-medium text-text-muted">N/A</span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {watched.industry ? (
          <span className="rounded-full border border-border px-2.5 py-1 text-xs font-medium text-text-secondary">
            {watched.industry}
          </span>
        ) : null}
        {watched.stage ? (
          <span className="rounded-full border border-border px-2.5 py-1 text-xs font-medium text-text-secondary">
            {watched.stage}
          </span>
        ) : null}
        {watched.has_canonical_analysis && !watched.has_multiple_analyses ? (
          <span className="text-xs text-text-muted">No historical comparison yet</span>
        ) : null}
      </div>

      {watched.has_canonical_analysis ? <PillarMiniRow pillars={watched.pillars} /> : null}

      {watched.attention_reasons.length > 0 ? (
        <div className="rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
          {watched.attention_reasons[0]}
        </div>
      ) : null}

      <div className="flex items-center justify-between border-t border-border pt-3">
        <Link href={profileHref} className="text-sm font-semibold text-primary hover:text-primary-hover">
          View profile →
        </Link>

        <div className="flex items-center gap-2">
          <CompareToggle selected={compareSelected} disabled={compareDisabled} onToggle={onToggleCompare} />

          <button
            type="button"
            disabled={removing}
            onClick={onUnsave}
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-secondary transition-colors hover:border-danger hover:text-danger disabled:cursor-not-allowed disabled:opacity-60"
          >
            {removing ? "Removing…" : "Unsave"}
          </button>
        </div>
      </div>
    </BaseCard>
  );
}
