"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import PageHeader from "@/components/layout/PageHeader";
import Breadcrumbs from "@/components/layout/Breadcrumbs";
import BaseCard from "@/components/ui/BaseCard";
import { SPSRing } from "@/components/sps";
import SPSHistory from "@/components/startup/SPSHistory";
import IntelligencePillars from "@/components/startup/IntelligencePillars";
import ActionPlan from "@/components/founder/ActionPlan";
import Milestones from "@/components/founder/Milestones";
import RecentUpdates from "@/components/founder/RecentUpdates";
import FundraisingReadinessCard from "@/components/founder/FundraisingReadinessCard";
import PitchDeckCoachTeaser from "@/components/founder/PitchDeckCoachTeaser";
import NextStepCard from "@/components/journey/NextStepCard";
import { PILLARS } from "@/components/startup/pillarMeta";
import {
  formatAnalysisDate,
  getOverallConfidence,
} from "@/components/startup/StartupHeroV2";

import { getFounderStartupWorkspace } from "@/lib/api";

import type { PillarKey } from "@/components/startup/pillarMeta";
import type {
  FounderStartupWorkspace,
  PillarAnalysis,
  SIEMethodologyAnalysis,
  SPSHistoryPoint,
} from "@/types";

type LoadState = "loading" | "ready" | "not-found" | "error";

type FounderStartupWorkspaceViewProps = {
  startupId: number;
};

type ScoredPillar = {
  key: PillarKey;
  label: string;
  analysis: PillarAnalysis;
};

// Phase 7.2 -- Founder Workspace V1. This is the founder's own private
// view of intelligence that already exists publicly -- the difference is
// framing (improvement-oriented, "where do I stand / what's next") and
// authorization (GET /founder/startups/{id} requires a live
// startup_memberships row via RequireStartupMember; the public Startup
// Profile requires nothing). No intelligence is recomputed, re-scored,
// or duplicated here -- every field below comes straight from the same
// SIEMethodologyAnalysis the public profile renders.
export default function FounderStartupWorkspaceView({
  startupId,
}: FounderStartupWorkspaceViewProps) {
  const { getToken } = useAuth();
  const router = useRouter();

  const [workspace, setWorkspace] = useState<FounderStartupWorkspace | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");

  useEffect(() => {
    let isMounted = true;

    async function loadWorkspace() {
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

        const data = await getFounderStartupWorkspace(startupId, token);

        if (isMounted) {
          setWorkspace(data);
          setLoadState("ready");
        }
      } catch (error) {
        console.error("Failed to load Founder Workspace:", error);

        if (isMounted) {
          // A 404 here means "doesn't exist, or you don't have access" --
          // the backend deliberately never distinguishes the two (see
          // RequireStartupMember's own docstring), so neither does this
          // message.
          setLoadState(
            error instanceof Error && /\(404\)/.test(error.message) ? "not-found" : "error"
          );
        }
      }
    }

    loadWorkspace();

    return () => {
      isMounted = false;
    };
  }, [startupId, getToken]);

  // Phase 37B -- Company Identity + Workspace Routing Bridge. Backward
  // compatibility for bookmarks/old links/direct navigation: once this
  // startup's own workspace response says it's linked (ownership-
  // checked) to a venture the caller still owns, redirect into the
  // existing Venture Workspace rather than rendering the page below at
  // all -- there is no second operating workspace for a linked company.
  // An unlinked (legacy) startup's `linked_venture_id` is null and this
  // effect is a no-op, so that case renders exactly as before this phase.
  useEffect(() => {
    if (loadState === "ready" && workspace?.linked_venture_id != null) {
      router.replace(`/idea-lab/${workspace.linked_venture_id}`);
    }
  }, [loadState, workspace, router]);

  if (loadState === "loading" || (loadState === "ready" && workspace?.linked_venture_id != null)) {
    return (
      <div className="space-y-6">
        <div className="h-40 animate-pulse rounded-2xl border border-border bg-surface" />
        <div className="h-56 animate-pulse rounded-2xl border border-border bg-surface" />
        <div className="h-96 animate-pulse rounded-2xl border border-border bg-surface" />
      </div>
    );
  }

  if (loadState === "not-found") {
    return (
      <BaseCard className="p-10 text-center">
        <h1 className="text-xl font-bold text-text-primary">
          Workspace not available
        </h1>
        <p className="mt-3 text-text-secondary">
          This startup workspace doesn&rsquo;t exist, or you don&rsquo;t
          have access to it.
        </p>
        <Link
          href="/founder"
          className="mt-6 inline-flex text-sm font-semibold text-primary hover:text-primary-hover"
        >
          ← Back to Founder Workspace
        </Link>
      </BaseCard>
    );
  }

  if (loadState === "error" || !workspace) {
    return (
      <div className="rounded-xl border border-danger/20 bg-danger-soft p-6">
        <h2 className="font-semibold text-danger">
          Unable to load this workspace
        </h2>
        <p className="mt-2 text-sm text-danger/80">Try refreshing the page.</p>
      </div>
    );
  }

  const { startup_id, canonical_name, created_at, methodology, sps_history, graduated_from_venture } = workspace;
  const publicProfileHref = `/startup/${encodeURIComponent(canonical_name)}`;
  // Phase 7.2.1 -- Deterministic Founder Re-analysis: startup_id in the
  // query string is what makes AnalyzeStartupForm verify membership and
  // guarantee this exact canonical startup as the write target -- see
  // that component's own FounderTargetState comment. Never the company
  // name: a name-based link could never guarantee re-attachment to this
  // same startup, which was the whole problem this phase fixes.
  const reanalyzeHref = `/analyze?startup_id=${startup_id}`;

  return (
    <div className="space-y-8">
      {/* Phase 32, Part 7: matches the directive's own second worked
          example ("My Startups / ClaimPilot") -- a founder with several
          startups needs to know which one they're in without re-reading
          the H1 every time. */}
      <Breadcrumbs
        items={[
          { label: "My Startups", href: "/founder" },
          { label: canonical_name },
        ]}
      />
      <PageHeader
        title={canonical_name}
        subtitle="Founder Workspace — private to you and your team. Public intelligence for this startup is unaffected by anything shown here."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={publicProfileHref}
              className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-primary"
            >
              View Public Profile
            </Link>
            <Link
              href={reanalyzeHref}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
            >
              Re-analyze
            </Link>
          </div>
        }
      />

      {/* Phase 32 -- Product Information Architecture + Seamless User
          Journey, Part 1/5. Trust state, shown honestly and explicitly,
          replacing the old subtitle's "private to verified members" --
          that language implied every workspace here required an
          independent SIE review to reach, which was never actually true
          for the common path: a founder who graduates their own modeled
          venture is granted this workspace immediately, self-approved,
          with zero human review (see _ensure_graduation_membership() in
          app/database/db.py) -- that is a real, legitimate way to reach
          a private workspace, just not the same claim as "SIE verified
          your relationship to this company." graduated_from_venture
          (already returned by GET /founder/startups/{id}, unchanged) is
          the one reliable, zero-new-schema signal for which case this
          is: present only when a venture_graduations row exists, which
          only ever happens via that exact self-approved path. No new
          endpoint, no new column, no access-control change -- honest
          labeling of a distinction that already existed in the data. */}
      <div className="flex flex-wrap items-center gap-3">
        {graduated_from_venture ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-muted px-3 py-1 text-sm font-semibold text-text-secondary">
            Founder-managed
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-3 py-1 text-sm font-semibold text-success">
            ✓ Verified
          </span>
        )}

        {graduated_from_venture ? (
          <p className="text-sm text-text-secondary">
            Created from your{" "}
            <Link
              href={`/idea-lab/${graduated_from_venture.venture_id}`}
              className="font-semibold text-primary hover:text-primary-hover"
            >
              {graduated_from_venture.venture_name}
            </Link>{" "}
            venture — self-reported, not yet independently reviewed by SIE.
          </p>
        ) : (
          <p className="text-sm text-text-secondary">
            SIE has confirmed your relationship to this company.
          </p>
        )}
      </div>

      {!methodology ? (
        <NotYetAnalyzed canonicalName={canonical_name} reanalyzeHref={reanalyzeHref} />
      ) : (
        <>
          <OverviewSection
            methodology={methodology}
            createdAt={created_at}
            spsHistory={sps_history}
          />

          <PrioritiesSection methodology={methodology} />
        </>
      )}

      {/* Phase 8 -- Fundraising Readiness V1 + Phase 10.10, Part 9/10: a
          compact teaser card linking to the dedicated /fundraising page,
          paired with a Pitch Deck Coach teaser so "prepare pitch" and
          "assess fundraising readiness" read as one connected step in
          the founder journey rather than two unrelated features. Rendered
          regardless of whether this startup has a canonical analysis yet
          -- the readiness page itself handles that honestly. */}
      <div className="grid gap-4 sm:grid-cols-2">
        <FundraisingReadinessCard startupId={startup_id} />
        <PitchDeckCoachTeaser />
      </div>

      {/* Phase 23 -- Universal Founder Capture V1, Part 14: moved ahead of
          Actions/Milestones to match the same STATUS -> PRIORITY ->
          CAPTURE -> ACTION hierarchy the Idea Lab venture workspace now
          uses (CaptureWhatHappened there, RecentUpdates here) -- "record
          what happened" should not require scrolling past the action
          list to find it. RecentUpdates itself is unmodified in
          persistence/semantics: still founder_update rows, still never
          touching SPS (see that component's own docstring). */}
      <RecentUpdates startupId={startup_id} />

      {/* Phase 7.3 -- Founder Progress & Improvement V1: rendered even
          when this startup has no canonical analysis yet, since
          founder-created actions don't depend on one (Part 17) -- only
          the "Recommended by SIE" sub-section inside ActionPlan itself
          is conditional on methodology being non-null. */}
      <ActionPlan
        startupId={startup_id}
        canonicalName={canonical_name}
        methodology={methodology}
      />

      {/* Phase 7.4 -- Founder Evidence + Milestones V1: same as
          ActionPlan above, rendered regardless of whether this startup
          has a canonical analysis yet (Part 18: "Founder may still
          create milestones and updates" with no analysis). Neither
          component reads or writes methodology/SPS at all. */}
      <Milestones startupId={startup_id} />

      {/* Part 15: the single re-analysis nudge at the true end of the
          operating loop (Needs Attention -> Action Plan -> Milestones ->
          Recent Updates -> Re-analyze), rather than a separate copy
          inside each section above -- one truthful, restrained CTA, not
          three similar ones stacked down the page. Only shown once
          there's an existing SPS to potentially update; re-analysis
          itself is always the founder's deliberate choice, never
          automatic (Part 15's own requirement). */}
      {methodology ? (
        <BaseCard className="flex flex-wrap items-center justify-between gap-3 border-primary/20 bg-primary/5 p-5">
          <div>
            <p className="text-sm font-semibold text-text-primary">
              Have meaningful new evidence?
            </p>
            <p className="mt-1 text-sm text-text-secondary">
              Update {canonical_name}&rsquo;s startup intelligence to see whether your
              VentureGPS Score reflects what&rsquo;s actually happened.
            </p>
          </div>
          <Link
            href={reanalyzeHref}
            className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
          >
            Re-analyze Startup
          </Link>
        </BaseCard>
      ) : null}

      {methodology ? (
        <>
          <SPSHistory history={sps_history} />

          <IntelligencePillars methodology={methodology} />
        </>
      ) : null}
    </div>
  );
}

// Phase 10.10, Part 16: consolidated onto the same shared NextStepCard
// every other "what should I do next?" moment in the product now uses
// (Idea Lab's IdeaLabNextStep, this same pattern) -- this used to be its
// own bespoke BaseCard with identical intent.
function NotYetAnalyzed({
  canonicalName,
  reanalyzeHref,
}: {
  canonicalName: string;
  reanalyzeHref: string;
}) {
  return (
    <NextStepCard
      eyebrow="No intelligence yet"
      title={`Analyze ${canonicalName} to see its VentureGPS Score`}
      why="Run SIE's analysis to see pillar scores, strengths, risks, and recommendations here."
      primaryAction={{ label: "Analyze this startup", href: reanalyzeHref }}
    />
  );
}

function OverviewSection({
  methodology,
  createdAt,
  spsHistory,
}: {
  methodology: SIEMethodologyAnalysis;
  createdAt: string | null;
  spsHistory: SPSHistoryPoint[];
}) {
  const confidence = getOverallConfidence(methodology);
  const analysisDate = createdAt ? formatAnalysisDate(createdAt) : null;

  // "How has SPS changed" -- change since the immediately preceding
  // analysis, same underlying sps_history data SPSHistory below charts
  // in full. Omitted (not zeroed) when fewer than two points exist yet.
  const trend =
    spsHistory.length >= 2
      ? spsHistory[spsHistory.length - 1].startup_intelligence_score -
        spsHistory[spsHistory.length - 2].startup_intelligence_score
      : undefined;

  // Phase 31C-A, Part 1/6: dropped the raw internal methodology-version
  // string (getMethodologyVersion()) from this line -- see
  // StartupHeroV2.tsx's own matching comment for the full reasoning
  // (live-discovered on this exact screen: "Methodology
  // v2.1-spec-2026-08-29"). "Analyzed {date}" is the fact a founder
  // actually needs.
  const metaParts = [
    analysisDate ? `Analyzed ${analysisDate}` : null,
  ].filter((part): part is string => Boolean(part));

  return (
    <BaseCard className="p-8">
      <div className="grid gap-8 lg:grid-cols-[240px_1fr] lg:items-center">
        <div className="flex justify-center">
          <SPSRing
            score={methodology.startup_intelligence_score}
            confidence={confidence}
            trend={trend}
            size="lg"
          />
        </div>

        <div>
          <h2 className="text-lg font-semibold text-text-primary">
            Current Standing
          </h2>

          {metaParts.length > 0 ? (
            <p className="mt-1 text-sm text-text-secondary">
              {metaParts.join(" · ")}
            </p>
          ) : null}

          {methodology.executive_coaching_summary ? (
            <p className="mt-4 max-w-prose text-base leading-7 text-text-secondary">
              {methodology.executive_coaching_summary}
            </p>
          ) : null}
        </div>
      </div>
    </BaseCard>
  );
}

function getScoredPillars(methodology: SIEMethodologyAnalysis): ScoredPillar[] {
  const scored: ScoredPillar[] = [];

  for (const pillar of PILLARS) {
    const analysis = methodology[pillar.key];

    // Unavailable pillars (score === null) are excluded from ranking
    // entirely -- never treated as a 0, never ranked as "weakest".
    if (analysis.score !== null) {
      scored.push({ key: pillar.key, label: pillar.label, analysis });
    }
  }

  return scored;
}

// "What's working" / "Needs attention" -- derived purely by sorting the
// same six real pillar scores/strengths/weaknesses the public profile
// already has; nothing here is recomputed or re-scored. The
// recommendations themselves (formerly a read-only "Top Priorities" list
// here) now live in the Action Plan section below as actionable
// "Recommended by SIE" suggestions (Phase 7.3,
// components/founder/founderActionSuggestions.ts) -- kept in exactly one
// place so the same five sentences never appear twice on this page.
function PrioritiesSection({ methodology }: { methodology: SIEMethodologyAnalysis }) {
  const scored = getScoredPillars(methodology);

  if (scored.length === 0) {
    return (
      <BaseCard className="p-6">
        <p className="text-sm text-text-secondary">
          Not enough evidence yet to identify strengths or priorities.
        </p>
      </BaseCard>
    );
  }

  const sortedByScoreDesc = [...scored].sort(
    (a, b) => (b.analysis.score as number) - (a.analysis.score as number)
  );

  const strongest = sortedByScoreDesc.slice(0, 2);
  const strongestKeys = new Set(strongest.map((p) => p.key));
  const weakest = [...sortedByScoreDesc]
    .reverse()
    .filter((p) => !strongestKeys.has(p.key))
    .slice(0, 2);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Phase 31C-C -- Global Visual Scale + Readability Correction,
          Part 8/9: these are real <h2> section headings on the founder's
          main dashboard, rendered at 12px -- the same hierarchy-inversion
          class as the playbooks page's own headings. Matched to this
          page's own "Current Standing"/"Action Plan" heading convention
          (text-lg, regular case, text-primary) instead of the small-caps
          eyebrow style, since these ARE the section titles, not a label
          above one. */}
      <BaseCard className="p-6">
        <h2 className="text-lg font-semibold text-text-primary">
          What&rsquo;s Working
        </h2>

        <div className="mt-4 space-y-4">
          {strongest.map((pillar) => (
            <PillarHighlight
              key={pillar.key}
              pillar={pillar}
              items={pillar.analysis.strengths}
              emptyLabel="No specific strengths noted yet."
              dotClassName="bg-success"
              scoreClassName="text-success"
            />
          ))}
        </div>
      </BaseCard>

      <BaseCard className="p-6">
        <h2 className="text-lg font-semibold text-text-primary">
          Needs Attention
        </h2>

        <div className="mt-4 space-y-4">
          {weakest.map((pillar) => (
            <PillarHighlight
              key={pillar.key}
              pillar={pillar}
              items={pillar.analysis.weaknesses}
              emptyLabel="No specific weaknesses noted yet."
              dotClassName="bg-danger"
              scoreClassName="text-danger"
            />
          ))}
        </div>
      </BaseCard>
    </div>
  );
}

function PillarHighlight({
  pillar,
  items,
  emptyLabel,
  dotClassName,
  scoreClassName,
}: {
  pillar: ScoredPillar;
  items: string[];
  emptyLabel: string;
  dotClassName: string;
  scoreClassName: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="text-base font-semibold text-text-primary">{pillar.label}</p>
        <span className={["text-base font-bold", scoreClassName].join(" ")}>
          {(pillar.analysis.score as number).toFixed(1)} / 10
        </span>
      </div>

      <ul className="mt-1.5 space-y-1">
        {items.length > 0 ? (
          items.slice(0, 2).map((item, index) => (
            <li key={index} className="flex gap-2 text-base leading-7 text-text-secondary">
              <span
                aria-hidden="true"
                className={["mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full", dotClassName].join(" ")}
              />
              <span>{item}</span>
            </li>
          ))
        ) : (
          <li className="text-base text-text-secondary">{emptyLabel}</li>
        )}
      </ul>
    </div>
  );
}
