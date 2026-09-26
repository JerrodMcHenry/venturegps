"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import BaseCard from "@/components/ui/BaseCard";
import PageHeader from "@/components/layout/PageHeader";
import Breadcrumbs from "@/components/layout/Breadcrumbs";
import PlaybookLink from "@/components/playbooks/PlaybookLink";
import { getPlaybookForReadinessGap } from "@/lib/playbooks/resourceMap";

import { createFounderAction, getFounderActions, getFundraisingReadiness } from "@/lib/api";

import type { FundraisingReadiness, ReadinessGap } from "@/types";

type LoadState = "loading" | "ready" | "not-found" | "error";

type FundraisingReadinessViewProps = {
  startupId: number;
};

const BAND_CLASSES: Record<string, string> = {
  Early: "border border-border text-text-secondary",
  Developing: "bg-warning/10 text-warning",
  "Getting Ready": "bg-primary/10 text-primary",
  "Raise Ready": "bg-success/10 text-success",
};

const CHECKLIST_STATUS_CLASSES: Record<string, string> = {
  Ready: "bg-success/10 text-success",
  "Needs Work": "bg-warning/10 text-warning",
  "Missing / Unknown": "border border-border text-text-muted",
};

// Phase 8 -- Fundraising Readiness V1. A dedicated private page, not a
// second scoring system -- everything shown here is either (a) a
// deterministic re-derivation of the same canonical pillar intelligence
// the public Startup Profile and Founder Workspace already show, framed
// around "how defensible is this in a fundraising conversation" rather
// than "what does the evidence say" (see
// app/ai/fundraising_readiness.py's own module docstring for the exact
// formula), or (b) an honest statement that something isn't known yet.
// Nothing here is computed by an LLM, and nothing here writes back to
// SPS/methodology/Rankings/Discovery -- this page only ever reads.
export default function FundraisingReadinessView({ startupId }: FundraisingReadinessViewProps) {
  const { getToken } = useAuth();
  const router = useRouter();

  const [readiness, setReadiness] = useState<FundraisingReadiness | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [addedGapTexts, setAddedGapTexts] = useState<Set<string>>(new Set());
  const [pendingGapTexts, setPendingGapTexts] = useState<Set<string>>(new Set());
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadReadiness() {
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

        const data = await getFundraisingReadiness(startupId, token);

        // Hydrate "already added" state from existing Action Plan rows so a
        // gap added in an earlier visit still shows "Added to Plan" after a
        // reload, instead of misleadingly offering to add it again. Backend
        // dedup (source <> 'founder_created' unique index) already prevents
        // an actual duplicate row either way -- this only fixes the display.
        let existingGapTitles = new Set<string>();
        try {
          const existingActions = await getFounderActions(startupId, token);
          existingGapTitles = new Set(
            existingActions.filter((action) => action.source === "fundraising_gap").map((action) => action.title)
          );
        } catch (actionsError) {
          console.error("Failed to load existing Action Plan items for readiness hydration:", actionsError);
        }

        if (isMounted) {
          setReadiness(data);
          setAddedGapTexts(existingGapTitles);
          setLoadState("ready");
        }
      } catch (error) {
        console.error("Failed to load Fundraising Readiness:", error);

        if (isMounted) {
          setLoadState(
            error instanceof Error && /\(404\)/.test(error.message) ? "not-found" : "error"
          );
        }
      }
    }

    loadReadiness();

    return () => {
      isMounted = false;
    };
  }, [startupId, getToken]);

  // Phase 37D -- Unified Workspace Simplification + Legacy Containment.
  // Same backward-compatibility redirect FounderStartupWorkspaceView.tsx
  // already applies (Phase 37B): a linked company has no second
  // "operating fundraising readiness" page -- this dedicated view exists
  // only for unlinked, legacy-workspace startups. `linked_venture_id` is
  // ownership-checked server-side; a null value (the common, unlinked
  // case) makes this a no-op, so this page renders exactly as it did
  // before this phase for every startup that isn't linked.
  useEffect(() => {
    if (loadState === "ready" && readiness?.linked_venture_id != null) {
      router.replace(`/idea-lab/${readiness.linked_venture_id}?tab=analyze`);
    }
  }, [loadState, readiness, router]);

  async function handleAddGapToPlan(gap: ReadinessGap) {
    setPendingGapTexts((previous) => new Set(previous).add(gap.source_text));
    setActionError(null);

    try {
      const token = await getToken();

      if (!token) {
        setActionError("Your session expired. Sign in again.");
        return;
      }

      await createFounderAction(
        startupId,
        {
          title: gap.issue,
          related_pillar: gap.pillar,
          source: "fundraising_gap",
        },
        token
      );
      setAddedGapTexts((previous) => new Set(previous).add(gap.source_text));
    } catch (error) {
      console.error("Failed to add fundraising gap to plan:", error);
      setActionError("Couldn't add that to your Action Plan. Try again.");
    } finally {
      setPendingGapTexts((previous) => {
        const next = new Set(previous);
        next.delete(gap.source_text);
        return next;
      });
    }
  }

  if (loadState === "loading" || (loadState === "ready" && readiness?.linked_venture_id != null)) {
    return (
      <div className="space-y-6">
        <div className="h-32 animate-pulse rounded-2xl border border-border bg-surface" />
        <div className="h-64 animate-pulse rounded-2xl border border-border bg-surface" />
      </div>
    );
  }

  if (loadState === "not-found") {
    return (
      <BaseCard className="p-10 text-center">
        <h1 className="text-xl font-bold text-text-primary">Not available</h1>
        <p className="mt-3 text-text-secondary">
          This startup&rsquo;s fundraising readiness isn&rsquo;t available, or you
          don&rsquo;t have access to it.
        </p>
        <Link href="/founder" className="mt-6 inline-flex text-sm font-semibold text-primary hover:text-primary-hover">
          ← Back to Founder Workspace
        </Link>
      </BaseCard>
    );
  }

  if (loadState === "error" || !readiness) {
    return (
      <div className="rounded-xl border border-danger/20 bg-danger-soft p-6">
        <h2 className="font-semibold text-danger">Unable to load Fundraising Readiness</h2>
        <p className="mt-2 text-sm text-danger/80">Try refreshing the page.</p>
      </div>
    );
  }

  const workspaceHref = `/founder/startups/${startupId}`;
  const reanalyzeHref = `/analyze?startup_id=${startupId}`;

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { label: "My Startups", href: "/founder" },
          { label: readiness.canonical_name, href: workspaceHref },
          { label: "Fundraising" },
        ]}
      />
      <PageHeader
        title="Fundraising Readiness"
        subtitle={`${readiness.canonical_name} — private to you and your team.`}
        action={
          <Link
            href={workspaceHref}
            className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-primary"
          >
            ← Founder Workspace
          </Link>
        }
      />

      {!readiness.has_canonical_analysis ? (
        <BaseCard className="p-10 text-center">
          <h2 className="text-xl font-bold text-text-primary">Not assessed yet</h2>
          <p className="mx-auto mt-3 max-w-md text-sm text-text-secondary">
            SIE needs a startup analysis before it can assess fundraising readiness.
          </p>
          <Link
            href={reanalyzeHref}
            className="mt-6 inline-flex rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
          >
            Analyze Startup
          </Link>
        </BaseCard>
      ) : (
        <>
          {/* Score/band + "what this means" + SPS as context only */}
          <BaseCard className="p-8">
            <div className="grid gap-8 lg:grid-cols-[220px_1fr] lg:items-center">
              <div className="flex flex-col items-center gap-3">
                {readiness.readiness_score !== null ? (
                  <>
                    <div className="text-5xl font-bold text-text-primary">
                      {readiness.readiness_score.toFixed(0)}
                    </div>
                    <span
                      className={[
                        "rounded-full px-3 py-1 text-xs font-semibold",
                        BAND_CLASSES[readiness.readiness_band ?? ""] ?? "border border-border text-text-secondary",
                      ].join(" ")}
                    >
                      {readiness.readiness_band}
                    </span>
                  </>
                ) : (
                  <p className="text-sm text-text-secondary">Not enough data to assess yet.</p>
                )}
              </div>

              <div>
                <h2 className="text-lg font-semibold text-text-primary">What this means</h2>
                <p className="mt-2 max-w-prose text-base leading-7 text-text-secondary">
                  Fundraising Readiness estimates how well-prepared and well-evidenced{" "}
                  {readiness.canonical_name}&rsquo;s story is for a{" "}
                  <span className="font-medium text-text-primary">{readiness.stage_label}</span>{" "}
                  fundraising conversation — not how good the company is, and not the odds of
                  actually closing a round. A strong VentureGPS Score doesn&rsquo;t
                  automatically mean an investor-ready story, and a modest one doesn&rsquo;t rule
                  one out.
                </p>
                {/* Phase 31C-A -- Global Founder UX Acceptance, Part 1/2/6:
                    live-discovered bare "SPS" plus 12px text on an
                    explanation of a real methodology firewall (Fundraising
                    Readiness never feeds back into the score) -- exactly
                    the kind of thing a founder needs to actually be able
                    to read. Bumped to the 14px floor, spelled out. */}
                {readiness.current_sps !== null ? (
                  <p className="mt-2 text-sm text-text-secondary">
                    Current VentureGPS Score: <span className="font-medium text-text-secondary">{readiness.current_sps.toFixed(1)}</span>{" "}
                    (shown for context only — Fundraising Readiness never changes it, and never appears in Rankings).
                  </p>
                ) : null}
              </div>
            </div>
          </BaseCard>

          {actionError ? <p className="text-xs text-danger">{actionError}</p> : null}

          {/* Top fundraising gaps */}
          <section>
            <h2 className="text-xl font-semibold text-text-primary">Top Fundraising Gaps</h2>
            {readiness.gaps.length === 0 ? (
              <BaseCard className="mt-4 p-6">
                <p className="text-sm text-text-secondary">
                  No significant gaps identified from the current analysis.
                </p>
              </BaseCard>
            ) : (
              <div className="mt-4 space-y-3">
                {readiness.gaps.map((gap) => {
                  const isAdded = addedGapTexts.has(gap.source_text);
                  const isPending = pendingGapTexts.has(gap.source_text);
                  // Phase 10.9 -- Founder Playbooks V1, Part 5D: educational
                  // guidance only -- reads the exact same gap.category/
                  // gap.pillar this card already renders through, never
                  // affects readiness_score or any other computed value.
                  const playbook = getPlaybookForReadinessGap({ category: gap.category, pillar: gap.pillar });

                  return (
                    <BaseCard key={gap.source_text} className="p-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-text-primary">{gap.issue}</p>
                          <p className="mt-1.5 text-sm text-text-secondary">{gap.why_it_matters}</p>
                          <p className="mt-1.5 text-sm text-primary">→ {gap.recommended_next_step}</p>
                          {playbook ? (
                            <PlaybookLink slug={playbook.slug} label={`Learn how: ${playbook.title} →`} className="mt-1.5 block" />
                          ) : null}
                        </div>

                        <button
                          type="button"
                          disabled={isAdded || isPending}
                          onClick={() => handleAddGapToPlan(gap)}
                          className="shrink-0 rounded-lg border border-primary/30 px-3 py-1.5 text-xs font-semibold text-primary transition-colors hover:bg-primary-soft disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {isAdded ? "Added to Plan" : isPending ? "Adding…" : "Add to Action Plan"}
                        </button>
                      </div>
                    </BaseCard>
                  );
                })}
              </div>
            )}
          </section>

          {/* Readiness by area */}
          <section>
            <h2 className="text-xl font-semibold text-text-primary">Readiness by Area</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {readiness.pillar_readiness.map((pillar) => (
                <BaseCard key={pillar.pillar} className="p-5">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-text-primary">{pillar.label}</p>
                    <span className="text-sm font-bold text-text-primary">
                      {pillar.readiness_contribution !== null
                        ? `${pillar.readiness_contribution.toFixed(1)} / 10`
                        : "—"}
                    </span>
                  </div>
                  {/* Phase 31C-A -- Global Founder UX Acceptance, Part 1/2/6:
                      "SPS 8.0/10" was doubly confusing -- bare jargon,
                      AND actually mislabeled (this is the PILLAR's own
                      0-10 score, not the aggregate VentureGPS Score,
                      which is 0-100). Relabeled for accuracy, not just
                      readability. Kept at the compact metadata size
                      (Part 8's own "genuinely constrained UI" exception --
                      three figures on one line, six times on this page)
                      but the weakness sentence below it is real
                      explanatory prose and bumped to the 14px floor. */}
                  <p className="mt-1 text-xs text-text-muted">
                    {pillar.score !== null
                      ? `Pillar score ${pillar.score.toFixed(1)}/10 · ${pillar.confidence} confidence · ${pillar.evidence_coverage.toFixed(0)}% evidence coverage`
                      : "No usable evidence yet"}
                  </p>
                  {pillar.top_weakness ? (
                    <p className="mt-2 text-sm text-text-secondary">{pillar.top_weakness}</p>
                  ) : null}
                </BaseCard>
              ))}
            </div>
          </section>

          {/* Questions investors may ask */}
          <section>
            <h2 className="text-xl font-semibold text-text-primary">Questions Investors May Ask</h2>
            {readiness.investor_questions.length === 0 ? (
              <BaseCard className="mt-4 p-6">
                <p className="text-sm text-text-secondary">
                  No specific investor questions surfaced from the current analysis.
                </p>
              </BaseCard>
            ) : (
              <BaseCard className="mt-4 p-5">
                <ul className="space-y-2">
                  {readiness.investor_questions.map((question, index) => (
                    <li key={index} className="flex gap-2.5 text-sm text-text-primary">
                      <span aria-hidden="true" className="text-text-muted">Q.</span>
                      <span>{question}</span>
                    </li>
                  ))}
                </ul>
              </BaseCard>
            )}
          </section>

          {/* Checklist */}
          <section>
            <h2 className="text-xl font-semibold text-text-primary">Readiness Checklist</h2>
            <BaseCard className="mt-4 divide-y divide-border p-0">
              {readiness.checklist.map((item) => (
                <div key={item.category} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3.5">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{item.category}</p>
                    <p className="text-sm text-text-secondary">{item.note}</p>
                  </div>
                  <span
                    className={[
                      "shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold",
                      CHECKLIST_STATUS_CLASSES[item.status] ?? "border border-border text-text-muted",
                    ].join(" ")}
                  >
                    {item.status}
                  </span>
                </div>
              ))}
            </BaseCard>
            <p className="mt-2 text-sm text-text-secondary">
              Checklist status reflects SIE&rsquo;s current assessment — completing Action
              Plan items or milestones doesn&rsquo;t change it directly. Re-analyzing does.
            </p>
          </section>

          {/* Next steps / re-analyze */}
          <BaseCard className="flex flex-wrap items-center justify-between gap-3 border-primary/20 bg-primary/5 p-5">
            <div>
              <p className="text-sm font-semibold text-text-primary">Next steps</p>
              <p className="mt-1 text-sm text-text-secondary">
                Work the gaps above, then re-analyze to see whether your intelligence — and this
                assessment — reflects the progress.
              </p>
            </div>
            <Link
              href={reanalyzeHref}
              className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
            >
              Re-analyze Startup
            </Link>
          </BaseCard>

          <p className="text-base leading-7 text-text-secondary">
            {readiness.pitch_deck_note} Fundraising Readiness is a separate, deterministic
            assessment of how prepared and well-evidenced your story is for a fundraising
            conversation — it is not your VentureGPS Score, and completing actions or
            milestones never changes it directly.
          </p>
        </>
      )}
    </div>
  );
}
