"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import BaseCard from "@/components/ui/BaseCard";
import { PILLARS } from "@/components/startup/pillarMeta";
import { getSuggestedActions } from "./founderActionSuggestions";

import {
  createFounderAction,
  getFounderActions,
  updateFounderActionStatus,
} from "@/lib/api";

import type { PillarKey } from "@/components/startup/pillarMeta";
import type {
  FounderAction,
  FounderActionStatus,
  SIEMethodologyAnalysis,
} from "@/types";

type LoadState = "loading" | "ready" | "error";

type ActionPlanProps = {
  startupId: number;
  canonicalName: string;
  methodology: SIEMethodologyAnalysis | null;
};

const PILLAR_LABELS: Record<PillarKey, string> = Object.fromEntries(
  PILLARS.map((pillar) => [pillar.key, pillar.label])
) as Record<PillarKey, string>;

// Phase 7.3 -- Founder Progress & Improvement V1. Persistent, shared-
// per-startup workflow state (Part 11) -- every verified member sees and
// can act on the exact same plan. This component NEVER computes, sends,
// or implies a score: every mutation here is a plain status transition
// on a founder_actions row (app/database/db.py's own Phase 7.3 section
// is the authoritative "never touches scoring" boundary). The only path
// from here back to SPS is the explicit "Re-analyze" CTA at the bottom,
// which routes into the existing deterministic founder re-analysis flow
// (Phase 7.2.1) -- it does not itself change anything.
export default function ActionPlan({ startupId, canonicalName, methodology }: ActionPlanProps) {
  const { getToken } = useAuth();

  const [actions, setActions] = useState<FounderAction[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");

  const [pendingActionIds, setPendingActionIds] = useState<Set<number>>(new Set());
  const [pendingSuggestions, setPendingSuggestions] = useState<Set<string>>(new Set());
  const [rowError, setRowError] = useState<string | null>(null);

  const [isAddingCustom, setIsAddingCustom] = useState(false);
  const [customTitle, setCustomTitle] = useState("");
  const [customPillar, setCustomPillar] = useState("");
  const [isSubmittingCustom, setIsSubmittingCustom] = useState(false);
  const [customError, setCustomError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadActions() {
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

        const data = await getFounderActions(startupId, token);

        if (isMounted) {
          setActions(data);
          setLoadState("ready");
        }
      } catch (error) {
        console.error("Failed to load Action Plan:", error);

        if (isMounted) {
          setLoadState("error");
        }
      }
    }

    loadActions();

    return () => {
      isMounted = false;
    };
  }, [startupId, getToken]);

  function upsertAction(updated: FounderAction) {
    setActions((previous) => {
      const exists = previous.some((action) => action.id === updated.id);
      return exists
        ? previous.map((action) => (action.id === updated.id ? updated : action))
        : [...previous, updated];
    });
  }

  const suggestions = useMemo(
    () => (methodology ? getSuggestedActions(methodology) : []),
    [methodology]
  );

  // Text-based, regardless of current status -- a dismissed
  // sie_recommendation still occupies the (startup_id, source_ref)
  // dedup slot on the backend (see create_founder_action()'s own
  // docstring), so re-clicking "Add to Plan" on it would just return the
  // same dismissed row rather than reviving it. Showing "Already in
  // plan" here is honest about that rather than implying a click would
  // do something. A founder who wants that exact text back can add it as
  // their own action instead (founder-authored text is never
  // deduplicated) -- a known, deliberately small V1 gap.
  const alreadyAddedTexts = useMemo(
    () =>
      new Set(
        actions.filter((action) => action.source === "sie_recommendation").map((action) => action.title)
      ),
    [actions]
  );

  const visibleActions = actions.filter((action) => action.status !== "dismissed");
  const todoActions = visibleActions.filter((action) => action.status === "todo");
  const inProgressActions = visibleActions.filter((action) => action.status === "in_progress");
  const completedActions = visibleActions.filter((action) => action.status === "completed");

  const totalCount = visibleActions.length;
  const completedCount = completedActions.length;
  const completionPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  async function handleAddSuggestion(suggestion: { pillar: PillarKey; text: string }) {
    setPendingSuggestions((previous) => new Set(previous).add(suggestion.text));
    setRowError(null);

    try {
      const token = await getToken();

      if (!token) {
        setRowError("Your session expired. Sign in again.");
        return;
      }

      const created = await createFounderAction(
        startupId,
        { title: suggestion.text, related_pillar: suggestion.pillar, source: "sie_recommendation" },
        token
      );
      upsertAction(created);
    } catch (error) {
      console.error("Failed to add suggested action:", error);
      setRowError("Couldn't add that to your plan. Try again.");
    } finally {
      setPendingSuggestions((previous) => {
        const next = new Set(previous);
        next.delete(suggestion.text);
        return next;
      });
    }
  }

  async function handleCreateCustomAction(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedTitle = customTitle.trim();

    if (!trimmedTitle) {
      setCustomError("Enter what you want to accomplish.");
      return;
    }

    setIsSubmittingCustom(true);
    setCustomError(null);

    try {
      const token = await getToken();

      if (!token) {
        setCustomError("Your session expired. Sign in again.");
        return;
      }

      const created = await createFounderAction(
        startupId,
        {
          title: trimmedTitle,
          related_pillar: customPillar || null,
          source: "founder_created",
        },
        token
      );
      upsertAction(created);
      setCustomTitle("");
      setCustomPillar("");
      setIsAddingCustom(false);
    } catch (error) {
      console.error("Failed to create action:", error);
      setCustomError("Couldn't add that action. Try again.");
    } finally {
      setIsSubmittingCustom(false);
    }
  }

  async function handleStatusChange(actionId: number, status: FounderActionStatus) {
    setPendingActionIds((previous) => new Set(previous).add(actionId));
    setRowError(null);

    try {
      const token = await getToken();

      if (!token) {
        setRowError("Your session expired. Sign in again.");
        return;
      }

      const updated = await updateFounderActionStatus(startupId, actionId, { status }, token);
      upsertAction(updated);
    } catch (error) {
      console.error("Failed to update action:", error);
      setRowError("Couldn't update that action. Try again.");
    } finally {
      setPendingActionIds((previous) => {
        const next = new Set(previous);
        next.delete(actionId);
        return next;
      });
    }
  }

  if (loadState === "loading") {
    return (
      <div className="h-72 animate-pulse rounded-2xl border border-border bg-surface" />
    );
  }

  if (loadState === "error") {
    return (
      <BaseCard className="border-danger/20 bg-danger-soft p-6">
        <h2 className="text-sm font-semibold text-danger">Unable to load Action Plan</h2>
        <p className="mt-1 text-sm text-danger/80">Try refreshing the page.</p>
      </BaseCard>
    );
  }

  const visibleSuggestions = suggestions.filter((s) => !alreadyAddedTexts.has(s.text));

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-text-primary">Action Plan</h2>
          <p className="mt-1 text-sm text-text-secondary">
            {totalCount > 0
              ? `${completedCount} of ${totalCount} action${totalCount === 1 ? "" : "s"} completed`
              : "Build your improvement plan from SIE recommendations or add your own action."}
          </p>
        </div>
      </div>

      {totalCount > 0 ? (
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-muted">
          <div
            className="h-full rounded-full bg-success transition-[width] duration-500"
            style={{ width: `${completionPercent}%` }}
          />
        </div>
      ) : null}

      {/* Phase 31C-A -- Global Founder UX Acceptance, Part 1/2/6:
          live-discovered bare "SPS" plus 12px body copy -- bumped to the
          14px helper-copy floor and spelled out the score name, same
          fix as the SPS ring itself (RingCenter.tsx). */}
      <p className="mt-3 text-base leading-7 text-text-secondary">
        Completing actions tracks your execution progress. Your VentureGPS Score only
        changes when new evidence is analyzed.
      </p>

      {rowError ? <p className="mt-2 text-xs text-danger">{rowError}</p> : null}

      {/* Recommended by SIE */}
      {methodology ? (
        visibleSuggestions.length > 0 ? (
          <BaseCard className="mt-5 p-5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
              Recommended by SIE
            </h3>

            <ul className="mt-3 space-y-2">
              {visibleSuggestions.map((suggestion) => (
                <li
                  key={suggestion.text}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-primary/5 px-3.5 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-text-primary">{suggestion.text}</p>
                    <span className="mt-1 inline-block rounded-full border border-border px-2 py-0.5 text-xs font-medium text-text-muted">
                      {suggestion.pillarLabel}
                    </span>
                  </div>

                  <button
                    type="button"
                    disabled={pendingSuggestions.has(suggestion.text)}
                    onClick={() => handleAddSuggestion(suggestion)}
                    className="shrink-0 rounded-lg border border-primary/30 px-3 py-1.5 text-xs font-semibold text-primary transition-colors hover:bg-primary-soft disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {pendingSuggestions.has(suggestion.text) ? "Adding…" : "Add to Plan"}
                  </button>
                </li>
              ))}
            </ul>
          </BaseCard>
        ) : null
      ) : (
        <BaseCard className="mt-5 p-5">
          <p className="text-sm text-text-secondary">
            SIE needs a completed analysis of {canonicalName} before it can suggest
            evidence-based actions. You can still add your own actions below.
          </p>
        </BaseCard>
      )}

      {/* Add a custom action */}
      <div className="mt-5">
        {isAddingCustom ? (
          <BaseCard className="p-5">
            <form onSubmit={handleCreateCustomAction} className="space-y-3">
              <div>
                <label htmlFor="custom-action-title" className="mb-1.5 block text-sm font-medium text-text-primary">
                  What do you want to accomplish?
                </label>
                <input
                  id="custom-action-title"
                  type="text"
                  value={customTitle}
                  onChange={(event) => setCustomTitle(event.target.value)}
                  placeholder="e.g. Interview 10 customers about pricing"
                  disabled={isSubmittingCustom}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20 disabled:opacity-60"
                />
              </div>

              <div>
                <label htmlFor="custom-action-pillar" className="mb-1.5 block text-sm font-medium text-text-primary">
                  Related pillar <span className="font-normal text-text-muted">(optional)</span>
                </label>
                <select
                  id="custom-action-pillar"
                  value={customPillar}
                  onChange={(event) => setCustomPillar(event.target.value)}
                  disabled={isSubmittingCustom}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-text-primary outline-none transition-colors focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20 disabled:opacity-60"
                >
                  <option value="">No specific pillar</option>
                  {PILLARS.map((pillar) => (
                    <option key={pillar.key} value={pillar.key}>
                      {pillar.label}
                    </option>
                  ))}
                </select>
              </div>

              {customError ? <p className="text-xs text-danger">{customError}</p> : null}

              <div className="flex items-center gap-2">
                <button
                  type="submit"
                  disabled={isSubmittingCustom}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSubmittingCustom ? "Adding…" : "Add action"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsAddingCustom(false);
                    setCustomError(null);
                  }}
                  disabled={isSubmittingCustom}
                  className="rounded-lg px-3 py-2 text-sm font-semibold text-text-muted transition-colors hover:text-text-secondary disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Cancel
                </button>
              </div>
            </form>
          </BaseCard>
        ) : (
          <button
            type="button"
            onClick={() => setIsAddingCustom(true)}
            className="rounded-lg border border-dashed border-border px-4 py-2.5 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-primary"
          >
            + Add your own action
          </button>
        )}
      </div>

      {/* NEXT UP / IN PROGRESS / COMPLETED */}
      {totalCount > 0 ? (
        <div className="mt-6 grid gap-4 lg:grid-cols-3">
          <ActionColumn
            title="Next Up"
            actions={todoActions}
            emptyLabel="Nothing queued."
            pendingActionIds={pendingActionIds}
            onStatusChange={handleStatusChange}
          />
          <ActionColumn
            title="In Progress"
            actions={inProgressActions}
            emptyLabel="Nothing in progress."
            pendingActionIds={pendingActionIds}
            onStatusChange={handleStatusChange}
          />
          <ActionColumn
            title="Completed"
            actions={completedActions}
            emptyLabel="Nothing completed yet."
            pendingActionIds={pendingActionIds}
            onStatusChange={handleStatusChange}
          />
        </div>
      ) : null}
    </section>
  );
}

function ActionColumn({
  title,
  actions,
  emptyLabel,
  pendingActionIds,
  onStatusChange,
}: {
  title: string;
  actions: FounderAction[];
  emptyLabel: string;
  pendingActionIds: Set<number>;
  onStatusChange: (actionId: number, status: FounderActionStatus) => void;
}) {
  return (
    <BaseCard className="p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
        {title} <span className="text-text-muted">({actions.length})</span>
      </h3>

      {actions.length === 0 ? (
        <p className="mt-3 text-sm text-text-secondary">{emptyLabel}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {actions.map((action) => (
            <ActionRow
              key={action.id}
              action={action}
              isPending={pendingActionIds.has(action.id)}
              onStatusChange={onStatusChange}
            />
          ))}
        </ul>
      )}
    </BaseCard>
  );
}

function ActionRow({
  action,
  isPending,
  onStatusChange,
}: {
  action: FounderAction;
  isPending: boolean;
  onStatusChange: (actionId: number, status: FounderActionStatus) => void;
}) {
  const pillarLabel = action.related_pillar
    ? PILLAR_LABELS[action.related_pillar as PillarKey]
    : null;

  return (
    <li className="rounded-lg border border-border p-3">
      <p className="text-sm text-text-primary">{action.title}</p>

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {pillarLabel ? (
          <span className="rounded-full border border-border px-2 py-0.5 text-xs font-medium text-text-muted">
            {pillarLabel}
          </span>
        ) : null}
        {action.source === "sie_recommendation" ? (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            SIE
          </span>
        ) : null}
        {/* Phase 8: visibly distinguishes a Fundraising-Readiness-derived
            action from an SIE pillar recommendation -- same idea, a
            different source/provenance, per Part 16's own requirement. */}
        {action.source === "fundraising_gap" ? (
          <span className="rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
            Fundraising
          </span>
        ) : null}
      </div>

      <div className="mt-2.5 flex flex-wrap gap-2">
        {action.status === "todo" ? (
          <>
            <StatusButton
              label="Start"
              disabled={isPending}
              onClick={() => onStatusChange(action.id, "in_progress")}
              primary
            />
            <StatusButton
              label="Dismiss"
              disabled={isPending}
              onClick={() => onStatusChange(action.id, "dismissed")}
            />
          </>
        ) : null}

        {action.status === "in_progress" ? (
          <>
            <StatusButton
              label="Complete"
              disabled={isPending}
              onClick={() => onStatusChange(action.id, "completed")}
              primary
            />
            <StatusButton
              label="Dismiss"
              disabled={isPending}
              onClick={() => onStatusChange(action.id, "dismissed")}
            />
          </>
        ) : null}

        {action.status === "completed" ? (
          <StatusButton
            label="Reopen"
            disabled={isPending}
            onClick={() => onStatusChange(action.id, "todo")}
          />
        ) : null}
      </div>
    </li>
  );
}

function StatusButton({
  label,
  onClick,
  disabled,
  primary,
}: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={[
        "rounded-md px-2.5 py-1 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        primary
          ? "bg-primary text-white hover:bg-primary-hover"
          : "border border-border text-text-muted hover:text-text-secondary",
      ].join(" ")}
    >
      {label}
    </button>
  );
}
