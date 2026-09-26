"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import PageHeader from "@/components/layout/PageHeader";
import BaseCard from "@/components/ui/BaseCard";
import Badge from "@/components/ui/Badge";
import type { BadgeTone } from "@/components/ui/Badge";
import Disclosure from "@/components/ui/Disclosure";
import EmptyState from "@/components/ui/EmptyState";
import ErrorMessage from "@/components/ui/ErrorMessage";
import Skeleton from "@/components/ui/Skeleton";
import Button from "@/components/ui/Button";

import { getPitchDeckReview } from "@/lib/api";
import PlaybookLink from "@/components/playbooks/PlaybookLink";
import NextStepCard from "@/components/journey/NextStepCard";
import MakeMissionButton from "./MakeMissionButton";
import { getPlaybookForDeckSection } from "@/lib/playbooks/resourceMap";
import type {
  DeckReadinessLabel,
  DeckSectionCoaching,
  DeckStoryField,
  PitchDeckReview,
  SectionStatus,
} from "@/types";

// Phase 10.8 -- Pitch Deck Coach V1. Progressive disclosure, per Part 21:
// the default view answers "what story am I telling / what's working /
// what's confusing / what should I fix first / what should I prepare
// for", in that order. The full 12-category slide-by-slide breakdown
// lives behind ONE outer Disclosure (not 12 separate accordions) --
// Part 21's own "avoid excessive accordions" boundary.
//
// Everything rendered here is exactly what POST/GET /pitch-deck-reviews
// returned -- no client-side scoring, no re-interpretation. Coaching
// language stays in the register the backend already enforced (Part 13):
// "may confuse", "consider", "possible investor question" -- this
// component adds fixed section EYEBROWS in that same voice, never a
// verdict ("investors hate this") of its own.

type LoadState = "loading" | "ready" | "error" | "not-found";

const READINESS_COPY: Record<DeckReadinessLabel, string> = {
  "Early Draft": "Most of the core questions investors ask first aren't answered yet -- that's normal for a first draft.",
  Developing: "Some of the core questions are answered; several still need work.",
  "Getting Clear": "Most of the core questions are answered clearly; a few gaps remain.",
  "Pitch Ready": "This deck clearly answers the core questions investors ask first.",
};

const READINESS_TONE: Record<DeckReadinessLabel, BadgeTone> = {
  "Early Draft": "neutral",
  Developing: "warning",
  "Getting Clear": "primary",
  "Pitch Ready": "success",
};

const STATUS_LABEL: Record<SectionStatus, string> = {
  missing: "Missing",
  unclear: "Unclear",
  effective: "Effective",
};

const STATUS_TONE: Record<SectionStatus, BadgeTone> = {
  missing: "neutral",
  unclear: "warning",
  effective: "success",
};

const STORY_LABELS: { key: keyof PitchDeckReview["story"]; label: string }[] = [
  { key: "company", label: "The Company" },
  { key: "customer", label: "The Customer" },
  { key: "problem", label: "The Problem" },
  { key: "solution", label: "The Solution" },
  { key: "business", label: "The Business" },
  { key: "proof", label: "The Proof" },
  { key: "ask", label: "The Ask" },
];

function pageRefLabel(pageRefs: number[]): string | null {
  if (pageRefs.length === 0) {
    return null;
  }
  return pageRefs.length === 1 ? `Slide ${pageRefs[0]}` : `Slides ${pageRefs.join(", ")}`;
}

export default function PitchDeckReviewView({ reviewId }: { reviewId: number }) {
  const { getToken } = useAuth();
  const [review, setReview] = useState<PitchDeckReview | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");

  useEffect(() => {
    let isMounted = true;

    async function loadReview() {
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

        const data = await getPitchDeckReview(reviewId, token);

        if (isMounted) {
          setReview(data);
          setLoadState("ready");
        }
      } catch (error) {
        console.error("Failed to load pitch deck review:", error);

        if (isMounted) {
          setLoadState(error instanceof Error && /\(404\)/.test(error.message) ? "not-found" : "error");
        }
      }
    }

    loadReview();

    return () => {
      isMounted = false;
    };
  }, [reviewId, getToken]);

  if (loadState === "loading") {
    return (
      <>
        <PageHeader title="Your Deck Review" />
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </>
    );
  }

  if (loadState === "not-found") {
    return (
      <>
        <PageHeader title="Your Deck Review" />
        <EmptyState
          title="We couldn't find that review"
          description="It may have been reviewed under a different account, or the link is incorrect."
          action={
            <Link href="/analyze/deck">
              <Button type="button">Review a Deck</Button>
            </Link>
          }
        />
      </>
    );
  }

  if (loadState === "error" || !review) {
    return (
      <>
        <PageHeader title="Your Deck Review" />
        <ErrorMessage>We couldn&rsquo;t load this review right now. Please try again.</ErrorMessage>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Your Deck Review"
        subtitle={review.deck_filename}
        action={
          <Link href="/analyze/deck">
            <Button type="button" variant="secondary">
              Review Another Deck
            </Button>
          </Link>
        }
      />

      <div className="space-y-8">
        <BaseCard className="p-6">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">Deck Readiness</span>
            <Badge tone={READINESS_TONE[review.readiness_label]}>{review.readiness_label}</Badge>
          </div>
          <p className="mt-2 text-sm text-text-secondary">{READINESS_COPY[review.readiness_label]}</p>
          <p className="mt-3 text-sm text-text-secondary">
            This is a coaching signal, not a score -- it never affects any VentureGPS Score, and it
            says nothing about whether your startup itself is a good idea.
          </p>
        </BaseCard>

        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
            Here&rsquo;s the story your deck tells
          </h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {STORY_LABELS.map(({ key, label }) => (
              <StoryCard key={key} label={label} field={review.story[key]} />
            ))}
          </div>
        </section>

        {review.top_fixes.length > 0 ? (
          <section>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
              Fix these {review.top_fixes.length === 1 ? "thing" : `${review.top_fixes.length} things`} first
            </h2>
            <div className="mt-3 space-y-3">
              {review.top_fixes.map((fix, index) => (
                <BaseCard key={index} variant="raised" className="p-5">
                  <div className="flex items-start gap-3">
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-bold text-primary">
                      {index + 1}
                    </span>
                    <div className="flex-1">
                      <h3 className="text-sm font-semibold text-text-primary">{fix.title}</h3>
                      <p className="mt-1.5 text-base leading-7 text-text-secondary">{fix.issue}</p>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-text-muted">
                        Why it matters
                      </p>
                      <p className="mt-1 text-base leading-7 text-text-secondary">{fix.why_it_matters}</p>
                      <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-text-muted">Try this</p>
                      <p className="mt-1 text-base leading-7 text-text-secondary">{fix.try_this}</p>

                      <MakeMissionButton fix={fix} />
                    </div>
                  </div>
                </BaseCard>
              ))}
            </div>
          </section>
        ) : null}

        {review.strengths.length > 0 ? (
          <section>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-text-muted">Keep this</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {review.strengths.map((strength, index) => (
                <BaseCard key={index} className="p-4">
                  <p className="text-sm font-semibold text-text-primary">{strength.title}</p>
                  <p className="mt-1.5 text-base leading-7 text-text-secondary">{strength.why_it_works}</p>
                </BaseCard>
              ))}
            </div>
          </section>
        ) : null}

        <Disclosure summary="See the full slide-by-slide breakdown">
          <div className="space-y-4 pt-2">
            {review.sections.map((section) => (
              <SectionCard key={section.category} section={section} />
            ))}
          </div>
        </Disclosure>

        {review.open_questions.length > 0 ? (
          <section>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
              Questions your deck may leave open
            </h2>
            <BaseCard className="mt-3 p-4">
              <ul className="space-y-2 text-sm text-text-secondary">
                {review.open_questions.map((item, index) => (
                  <li key={index} className="flex gap-2">
                    <span aria-hidden="true" className="text-warning">?</span>
                    <span>{item.question}</span>
                  </li>
                ))}
              </ul>
            </BaseCard>
          </section>
        ) : null}

        {review.prep_questions.length > 0 ? (
          <section>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
              Prepare for the conversation
            </h2>
            <p className="mt-1 text-sm text-text-secondary">
              These are possible investor questions based on your deck -- not actual investor feedback.
            </p>
            <div className="mt-3 space-y-2">
              {review.prep_questions.map((item, index) => (
                <BaseCard key={index} className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                    Possible investor question
                  </p>
                  <p className="mt-1 text-base leading-7 text-text-primary">&ldquo;{item.question}&rdquo;</p>
                </BaseCard>
              ))}
            </div>
          </section>
        ) : null}

        {/* Phase 10.10 -- Founder Journey Integration, Part 9: a deck
            review is never the end of the loop. Deliberately generic and
            never inferring fundraising readiness from deck quality (Part
            9's own explicit warning) -- this is an educational pointer
            forward, not a claim this deck (or this founder) is ready to
            raise. A canonical founder with an actual Fundraising
            Readiness assessment already finds it via My Startup in the
            account menu; nothing here guesses at or links a specific
            startup. */}
        <NextStepCard
          eyebrow="What's next?"
          title="Keep preparing for the conversation"
          why="A clear deck is one part of being ready to raise -- not the whole picture. Fundraising Readiness looks at the evidence behind your whole story."
          primaryAction={{ label: "Review another deck", href: "/analyze/deck" }}
          learnPlaybookSlug="fundraising"
        />
      </div>
    </>
  );
}

function StoryCard({ label, field }: { label: string; field: DeckStoryField }) {
  const pageLabel = pageRefLabel(field.page_refs);

  return (
    <BaseCard className="p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{label}</p>
      <p className={`mt-1.5 text-base leading-7 ${field.found ? "text-text-primary" : "text-text-muted italic"}`}>
        {field.summary}
      </p>
      {pageLabel ? <p className="mt-2 text-xs text-text-muted">{pageLabel}</p> : null}
    </BaseCard>
  );
}

function SectionCard({ section }: { section: DeckSectionCoaching }) {
  const pageLabel = pageRefLabel(section.page_refs);
  // Phase 10.9 -- Founder Playbooks V1, Part 5C: purely additive
  // presentation -- does not touch the grounding/sanitization pipeline
  // (app/ai/pitch_deck_coaching.py) or turn playbook content into deck
  // evidence in any way; `section.category` is the exact same field
  // this card already renders.
  const playbook = getPlaybookForDeckSection(section.category);

  return (
    <BaseCard className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-text-primary">{section.label}</p>
        <div className="flex items-center gap-2">
          {pageLabel ? <span className="text-xs text-text-muted">{pageLabel}</span> : null}
          <Badge tone={STATUS_TONE[section.status]}>{STATUS_LABEL[section.status]}</Badge>
        </div>
      </div>

      {section.what_its_saying ? (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">What this is saying</p>
          <p className="mt-1 text-base leading-7 text-text-secondary">{section.what_its_saying}</p>
        </div>
      ) : null}

      {section.whats_working ? (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">What&rsquo;s working</p>
          <p className="mt-1 text-base leading-7 text-text-secondary">{section.whats_working}</p>
        </div>
      ) : null}

      {section.may_confuse ? (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            What may confuse an investor
          </p>
          <p className="mt-1 text-base leading-7 text-text-secondary">{section.may_confuse}</p>
        </div>
      ) : null}

      <div className="mt-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Why investors care</p>
        <p className="mt-1 text-base leading-7 text-text-secondary">{section.why_investors_care}</p>
      </div>

      {section.try_this ? (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Try this</p>
          <p className="mt-1 text-base leading-7 text-text-secondary">{section.try_this}</p>
        </div>
      ) : null}

      {playbook ? (
        <PlaybookLink slug={playbook.slug} label="Learn how to improve this →" className="mt-3 block" />
      ) : null}
    </BaseCard>
  );
}
