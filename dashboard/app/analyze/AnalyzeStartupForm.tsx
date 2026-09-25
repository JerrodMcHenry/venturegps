"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import PageHeader from "@/components/layout/PageHeader";
import Button from "@/components/ui/Button";
import ErrorMessage from "@/components/ui/ErrorMessage";
import Input from "@/components/ui/Input";
import Skeleton from "@/components/ui/Skeleton";
import Textarea from "@/components/ui/Textarea";
import { analyzeMultiSource, getFounderStartupWorkspace } from "@/lib/api";
import { consumeVentureDescriptionForAnalyze } from "@/lib/ventureToStartupHandoff";

// Unified Multi-Source Analyze Startup: company website, pitch deck, and
// additional company information are evidence SOURCES feeding one
// canonical analysis, not separate mutually-exclusive modes -- all three
// fields are shown together, any combination (including just one) is
// valid, and a single submit sends whichever were filled in to POST
// /analyze (see lib/api/analyze.ts::analyzeMultiSource). This replaces
// the earlier three-tab mode switcher.
//
// SIE Authentication Phase 1: this used to be app/analyze/page.tsx
// itself. It's now a plain client component rendered by that page after
// the page's own server-side auth.protect() check -- auth() only works
// server-side, and this component's interactive form/submit/analyzing-
// state logic all genuinely needs to run client-side, so the page was
// split into a thin server wrapper (auth gate) + this unchanged client
// component (everything else). No behavior here changed.

// Client-side only, matching app/pdf_extractor.py's real cap -- catches
// an obviously-oversized file before spending a network round trip. The
// backend re-validates independently (size, magic bytes, page count,
// encryption, ...) regardless of what passes here.
const MAX_PDF_BYTES = 15 * 1024 * 1024;

const COMPANY_TEXT_PLACEHOLDER = `Anything else worth including that the website or pitch deck might not
capture -- recent traction or metrics, funding details, specific
customers, financial details, or context on stage/business model.

This is optional and supplementary -- it doesn't need to stand on its
own the way it would if it were your only source.`;

// What the pipeline actually does, in order -- shown as a static list of
// what SIE evaluates, never as a checklist that claims a given stage has
// finished. The backend does not currently report which stage is
// in-flight, so this is intentionally NOT rendered as live progress.
const STAGES = [
  "Researching the company",
  "Analyzing the six intelligence pillars",
  "Evaluating evidence",
  "Calculating the Startup Power Score",
  "Building the intelligence profile",
];

type Status = "idle" | "submitting" | "error";

// Phase 7.2.1 -- Deterministic Founder Re-analysis: this component now
// has two modes, distinguished ONLY by the presence of a `startup_id`
// query param -- normal analysis (no param) is completely unchanged.
// "founder-targeted" mode is verified with a real backend call
// (GET /founder/startups/{id}, the exact same RequireStartupMember-gated
// endpoint Founder Workspace itself uses) BEFORE the form is even shown
// -- a cheap, fast check, run instead of the multi-minute pipeline, so
// an unauthorized/invalid/stale startup_id is rejected without wasting
// an LLM run and without ever rendering a form that would silently fall
// back to creating a new, unrelated public analysis. This frontend check
// is UX only, exactly like every other client-side check in this file --
// POST /analyze re-verifies membership itself regardless (see app/api.py).
type FounderTargetState =
  | { status: "none" }
  | { status: "checking" }
  | { status: "ready"; startupId: number; canonicalName: string }
  | { status: "denied" };

function parseStartupIdParam(raw: string | null): number | null {
  if (!raw) {
    return null;
  }

  const parsed = Number(raw);

  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

// SIE Authentication Phase 2: shown for both a client-side-detected
// expired session (getToken() returned null) and a backend 401 --
// deliberately never shows the raw backend/JWT error text, and never
// blames the user's input (their entered sources are left exactly as
// typed either way, per the existing error-preserves-input behavior
// below).
const SESSION_EXPIRED_MESSAGE =
  "Your session has expired. Please sign in again to continue.";

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

// Every field below is individually optional -- validate its own shape
// only when something was actually entered, then separately require that
// at least one of the three ended up supplied. Same client-side-only
// contract as before: catches the obvious case before a network round
// trip, the backend re-validates every source independently regardless.
function validateWebsiteUrl(url: string): string | null {
  const trimmed = url.trim();

  if (trimmed.length === 0) {
    return null;
  }

  if (!/^https?:\/\//i.test(trimmed)) {
    return "Website URL must start with http:// or https://";
  }

  return null;
}

function validatePdfFile(file: File | null): string | null {
  if (!file) {
    return null;
  }

  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return "Only PDF files are supported.";
  }

  if (file.size > MAX_PDF_BYTES) {
    return `That PDF is too large to analyze (max ${MAX_PDF_BYTES / (1024 * 1024)} MB).`;
  }

  return null;
}

function validateForm(
  websiteUrl: string,
  pdfFile: File | null,
  companyText: string
): string | null {
  const urlError = validateWebsiteUrl(websiteUrl);
  if (urlError) {
    return urlError;
  }

  const pdfError = validatePdfFile(pdfFile);
  if (pdfError) {
    return pdfError;
  }

  const hasWebsite = websiteUrl.trim().length > 0;
  const hasPdf = pdfFile !== null;
  const hasText = companyText.trim().length > 0;

  if (!hasWebsite && !hasPdf && !hasText) {
    return "Provide at least one of: company website, pitch deck, or company information.";
  }

  return null;
}

export default function AnalyzeStartupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // SIE Authentication Phase 2: getToken() is Clerk's current supported
  // API for obtaining the real session JWT to attach to a backend call
  // (see the compatibility spike) -- called fresh at submit time, never
  // cached in state/localStorage, so it's always Clerk's current token.
  const { getToken } = useAuth();

  const [websiteUrl, setWebsiteUrl] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const [companyText, setCompanyText] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  // Phase 40A-FIX -- Private Beta P1 Hardening, P1 #3: Venture Workspace's
  // own "Run a standalone evaluation" button already tells a founder this
  // won't be tied to their venture (see VentureWorkspace.tsx's own
  // comment) -- but that promise wasn't echoed on THIS side once they
  // land here with their venture description pre-filled, so nothing
  // confirmed it actually happened. Tracked separately from
  // `companyText` itself so clearing/editing the textarea doesn't need to
  // un-set this -- the note describes how the text GOT here, not what it
  // currently contains.
  const [arrivedFromVenture, setArrivedFromVenture] = useState(false);

  const requestedStartupId = parseStartupIdParam(searchParams.get("startup_id"));
  const [founderTarget, setFounderTarget] = useState<FounderTargetState>(
    requestedStartupId !== null ? { status: "checking" } : { status: "none" }
  );

  // Phase 10.8 -- Pitch Deck Coach V1, Part 20: "Analyze" becomes a
  // chooser first ("What do you want to improve?") for a normal visitor,
  // rather than dropping straight into the canonical-analysis form. A
  // founder-targeted re-analysis (?startup_id=) skips this entirely --
  // that visitor arrived via an explicit "Re-analyze" CTA and must land
  // straight on the form, never a generic chooser. Choosing "Review My
  // Pitch Deck" navigates away to the completely separate /analyze/deck
  // surface (POST /pitch-deck-reviews, never POST /analyze); choosing
  // "Analyze My Startup" simply reveals this exact, unchanged form.
  const [mode, setMode] = useState<"choose" | "startup">(
    requestedStartupId !== null ? "startup" : "choose"
  );

  // Phase 10.10 -- Founder Journey Integration, Part 8: pre-fills
  // "Additional Company Information" with the founder's own venture
  // description if they arrived via Idea Lab's "Ready to turn this into a
  // real startup?" bridge (see lib/ventureToStartupHandoff.ts).
  //
  // Phase 31 -- Venture -> Startup Graduation V1, Part 5: this USED to
  // early-return for a founder-targeted re-analysis (?startup_id=), on
  // the assumption that flow "always re-analyzes the SAME existing
  // canonical startup, which has nothing to do with any modeled
  // venture's description." Graduation makes that assumption false: it
  // redirects the founder to exactly this `?startup_id=` re-analysis
  // flow immediately after creating a brand-new startup FROM a venture,
  // stashing that venture's own reviewable summary first. Removing the
  // early-return costs nothing for the normal re-analysis case --
  // consumeVentureDescriptionForAnalyze() already returns null harmlessly
  // when nothing was stashed, exactly like every other visit to
  // /analyze. Promise.resolve().then() is the same genuine microtask
  // boundary NewVentureForm.tsx already uses for the analogous
  // homepage-idea consume, for the same "sessionStorage doesn't exist
  // during SSR" reason.
  useEffect(() => {
    Promise.resolve().then(() => {
      const stashedDescription = consumeVentureDescriptionForAnalyze();

      if (stashedDescription) {
        setCompanyText(stashedDescription);
        setMode("startup");
        setArrivedFromVenture(true);
      }
    });
  }, [requestedStartupId]);

  // Phase 7.2.1: verifies the founder-targeted request BEFORE showing
  // any form -- see FounderTargetState's own comment for why this reuses
  // Founder Workspace's own membership-gated endpoint rather than
  // inventing a second check. Every setState call below lives inside
  // this locally-defined async function (react-hooks/set-state-in-effect
  // convention, same pattern as SaveStartupButton/ClaimStartupButton).
  useEffect(() => {
    let isMounted = true;

    async function verifyFounderTarget() {
      if (requestedStartupId === null) {
        if (isMounted) {
          setFounderTarget({ status: "none" });
        }
        return;
      }

      if (isMounted) {
        setFounderTarget({ status: "checking" });
      }

      try {
        const token = await getToken();

        if (!token) {
          if (isMounted) {
            setFounderTarget({ status: "denied" });
          }
          return;
        }

        const workspace = await getFounderStartupWorkspace(requestedStartupId, token);

        if (isMounted) {
          setFounderTarget({
            status: "ready",
            startupId: requestedStartupId,
            canonicalName: workspace.canonical_name,
          });
        }
      } catch (verifyError) {
        console.error("Failed to verify founder-targeted re-analysis:", verifyError);

        if (isMounted) {
          setFounderTarget({ status: "denied" });
        }
      }
    }

    verifyFounderTarget();

    return () => {
      isMounted = false;
    };
  }, [requestedStartupId, getToken]);

  const isSubmitting = status === "submitting";

  useEffect(() => {
    if (!isSubmitting) {
      return;
    }

    const interval = setInterval(() => {
      setElapsedSeconds((seconds) => seconds + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, [isSubmitting]);

  // MVP hardening: a refresh or tab close mid-analysis doesn't lose the
  // (expensive, multi-minute) analysis itself -- the backend request keeps
  // running and still persists on completion -- but it does strand the
  // user with no way to know when it finished or land on the resulting
  // profile automatically. The native browser confirmation is the
  // smallest honest guard against an accidental refresh/close; it can't
  // (and doesn't try to) prevent a deliberate one.
  useEffect(() => {
    if (!isSubmitting) {
      return;
    }

    function handleBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
      // Legacy browsers key off the return value rather than
      // preventDefault() alone.
      event.returnValue = "";
    }

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isSubmitting]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // Defense in depth: the submit button/form is unmounted while
    // isSubmitting is true (replaced by the analyzing state below), so
    // there is no visible control to double-click -- this guard only
    // matters if a submit event somehow fires again before that re-render.
    if (isSubmitting) {
      return;
    }

    const validationError = validateForm(websiteUrl, pdfFile, companyText);

    if (validationError) {
      setStatus("error");
      setError(validationError);
      return;
    }

    setStatus("submitting");
    setError(null);
    setElapsedSeconds(0);

    try {
      // The page itself already requires a signed-in visitor
      // (auth.protect() in page.tsx) before this form ever renders, but
      // a session can still expire mid-fill -- getToken() returning null
      // here is exactly that case, and is treated identically to the
      // backend's own 401 below rather than sending a request we already
      // know will fail.
      const token = await getToken();

      if (!token) {
        setStatus("error");
        setError(SESSION_EXPIRED_MESSAGE);
        return;
      }

      const isFounderTargeted = founderTarget.status === "ready";

      const response = await analyzeMultiSource({
        websiteUrl: websiteUrl.trim() || undefined,
        pdfFile: pdfFile ?? undefined,
        companyText: companyText.trim() || undefined,
        startupId: isFounderTargeted ? founderTarget.startupId : undefined,
        token,
      });

      // Founder-targeted mode: redirect back into Founder Workspace for
      // the exact startup_id just submitted, not the public profile --
      // this also sidesteps a real mismatch: the analysis just extracted
      // may have named the company something slightly different (e.g.
      // "Linear App" instead of "Linear"), and POST /analyze deliberately
      // persists the row under the EXISTING canonical name for identity
      // purposes (see save_analysis()'s own docstring) rather than this
      // extracted variant, so building a profile URL from
      // response.context.company_name here could 404. Founder Workspace
      // itself always resolves by the real startup_id, never by name.
      if (isFounderTargeted) {
        router.push(`/founder/startups/${founderTarget.startupId}`);
        return;
      }

      const companyName = response.context?.company_name?.trim();

      if (!companyName) {
        setStatus("error");
        setError(
          "The analysis completed, but SIE could not determine a clear company name to build a profile for. Try including the company's name explicitly and submit again."
        );
        return;
      }

      // Encode exactly once here -- the Startup Profile route decodes
      // exactly once when it reads the dynamic segment back out (see
      // app/startup/[id]/page.tsx), so this stays a single encode/decode
      // pass end-to-end, same contract as every other link into that route.
      router.push(`/startup/${encodeURIComponent(companyName)}`);
    } catch (caughtError) {
      console.error("Analyze Startup failed:", caughtError);

      const message =
        caughtError instanceof Error ? caughtError.message : "";

      setStatus("error");
      setError(
        /Request timed out/.test(message)
          ? "The analysis is taking longer than expected and timed out. Your input hasn't been lost -- you can try submitting again."
          : /Network error/.test(message)
            ? "Couldn't reach the SIE backend. Confirm it's running, then try again."
            : /API request failed \(401\)/.test(message)
              ? SESSION_EXPIRED_MESSAGE
              : /API request failed \(404\)/.test(message) && founderTarget.status === "ready"
                ? "You no longer have access to update this startup. Return to Founder Workspace and try again."
                : // Phase 10.1B -- AI Cost + Analysis Abuse Protection: 409
                  // covers both the same-account concurrency lock and the
                  // duplicate-submission cooldown; 429 covers the beta usage
                  // cap. Deliberately generic, friendly copy here rather than
                  // parsing/displaying the backend's own detail string --
                  // matches this catch block's existing convention of fixed,
                  // reviewed messages per status code, never raw backend text.
                  /API request failed \(409\)/.test(message)
                  ? "An analysis is already in progress or was just submitted for your account. Please wait a few minutes before trying again."
                  : /API request failed \(429\)/.test(message)
                    ? "You've reached the current beta analysis limit. Please try again later."
                    : "The analysis failed. Your input hasn't been lost -- you can try again."
      );
    }
  }

  // Phase 7.2.1: a founder-targeted request that fails verification never
  // falls back to the normal form -- per that phase's own "do not fall
  // back to normal analysis mode" requirement, showing this instead of a
  // form that would silently create an unrelated public analysis.
  if (founderTarget.status === "checking") {
    return (
      <>
        <PageHeader title="Analyze Startup" />
        <Skeleton className="h-64 w-full" />
      </>
    );
  }

  // Phase 10.8, Part 20: the chooser only ever shows for a normal
  // (non-founder-targeted) visitor who hasn't picked a path yet.
  if (founderTarget.status === "none" && mode === "choose") {
    return (
      <>
        <PageHeader
          title="What do you want to improve?"
          subtitle="Choose the kind of feedback you're looking for."
        />

        <div className="grid gap-4 sm:grid-cols-2">
          {/* Phase 31C-C -- Global Visual Scale + Readability Correction,
              Part 6: this is the whole decision surface of the page --
              two cards, a lot of empty canvas around them. Bumped
              min-height/padding and the card titles to text-lg (18px, the
              card-heading floor) so the choice reads as substantial
              rather than as two undersized buttons. */}
          <button
            type="button"
            onClick={() => router.push("/analyze/deck")}
            className="flex min-h-40 flex-col items-start gap-2.5 rounded-2xl border border-border bg-surface p-7 text-left transition-colors hover:border-primary/40 hover:bg-surface-muted"
          >
            <span className="text-lg font-semibold text-text-primary">Review My Pitch Deck</span>
            <span className="text-base leading-7 text-text-secondary">
              Upload a PDF deck and get coaching on the story it tells, what&rsquo;s working, and what to
              fix first.
            </span>
          </button>

          <button
            type="button"
            onClick={() => setMode("startup")}
            className="flex min-h-40 flex-col items-start gap-2.5 rounded-2xl border border-border bg-surface p-7 text-left transition-colors hover:border-primary/40 hover:bg-surface-muted"
          >
            <span className="text-lg font-semibold text-text-primary">Analyze My Startup</span>
            {/* Phase 31C-A -- Global Founder UX Acceptance, Part 1/6:
                live-discovered bare "Methodology v2" -- an internal
                version name with no meaning to a first-time founder.
                Replaced with what the process actually does. */}
            <span className="text-base leading-7 text-text-secondary">
              Provide a website, pitch deck, or company information and build a full,
              evidence-based Startup Profile.
            </span>
          </button>
        </div>
      </>
    );
  }

  if (founderTarget.status === "denied") {
    return (
      <>
        <PageHeader title="Analyze Startup" />
        <ErrorMessage
          className="p-8 text-center"
          action={
            <Link href="/founder" className="font-semibold underline hover:text-danger/80">
              ← Back to Founder Workspace
            </Link>
          }
        >
          <h2 className="text-lg font-semibold text-danger">
            You don&rsquo;t have access to update this startup
          </h2>
          {/* Phase 32A -- Trust-State Consistency: "verified member" was
              being used here as a generic synonym for "you don't have
              access" -- this error covers BOTH the Founder-managed and
              Verified cases equally (neither has anything to do with why
              access failed here), so naming "verified" at all was
              misleading, not just imprecise. */}
          <p className="mx-auto mt-2 max-w-md text-sm text-danger/80">
            This startup workspace doesn&rsquo;t exist, or you don&rsquo;t
            have access to it.
          </p>
        </ErrorMessage>
      </>
    );
  }

  const isFounderTargeted = founderTarget.status === "ready";

  return (
    <>
      <PageHeader
        title={isFounderTargeted ? "Re-analyze Startup" : "Analyze Startup"}
        subtitle={
          isFounderTargeted
            ? "Provide a company website, an updated pitch deck, or additional information -- SIE combines it with its own research and refreshes this startup's intelligence."
            : "Provide a company website, a pitch deck, additional information, or any combination -- SIE will combine what you give it with its own research and build one full, evidence-based Startup Profile."
        }
      />

      {isFounderTargeted && !isSubmitting ? (
        <div className="mb-6 rounded-xl border border-info/30 bg-info-soft px-5 py-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-info">
            Updating intelligence for
          </p>
          <p className="mt-1 text-xl font-bold text-text-primary">
            {founderTarget.canonicalName}
          </p>
          <p className="mt-2 text-sm text-text-secondary">
            This analysis will be attached directly to {founderTarget.canonicalName}
            &rsquo;s existing profile -- it will never create a separate startup.
          </p>
        </div>
      ) : null}

      {/* Phase 40A-FIX -- Private Beta P1 Hardening, P1 #3: the reciprocal
          half of VentureWorkspace.tsx's "This runs a standalone
          evaluation, not tied to {venture.name}" copy -- confirms, on
          arrival, that pre-filling this textarea from a venture did not
          quietly link the two. Never shown together with the founder-
          targeted box above: that box means an existing startup's
          `?startup_id=` re-analysis, a completely different entry point
          from a fresh Idea Lab venture that has no startup yet. */}
      {arrivedFromVenture && !isFounderTargeted && !isSubmitting ? (
        <div className="mb-6 rounded-xl border border-info/30 bg-info-soft px-5 py-4">
          <p className="text-sm text-text-secondary">
            Pre-filled from your venture&rsquo;s description. This builds a new,
            independent Startup Profile -- it won&rsquo;t be linked to or update
            your venture workspace.
          </p>
        </div>
      ) : null}

      {!isSubmitting ? (
        <form onSubmit={handleSubmit} className="space-y-6">
          <Input
            id="website-url"
            label="Company Website"
            type="text"
            inputMode="url"
            value={websiteUrl}
            onChange={(event) => setWebsiteUrl(event.target.value)}
            placeholder="https://example.com"
          />

          <div>
            <label
              htmlFor="pitch-deck-file"
              className="text-sm font-semibold uppercase tracking-wide text-text-secondary"
            >
              Pitch Deck
            </label>

            <input
              id="pitch-deck-file"
              ref={pdfInputRef}
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) =>
                setPdfFile(event.target.files?.[0] ?? null)
              }
              className="hidden"
            />

            <div className="mt-2">
              {pdfFile ? (
                <div className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-3">
                  <span className="truncate text-sm text-text-primary">
                    {pdfFile.name}
                  </span>

                  <Button
                    type="button"
                    variant="subtle"
                    size="sm"
                    onClick={() => {
                      setPdfFile(null);
                      // Reset the underlying input so choosing the same
                      // file again after removing it still fires
                      // onChange (the browser otherwise treats it as an
                      // unchanged selection and stays silent).
                      if (pdfInputRef.current) {
                        pdfInputRef.current.value = "";
                      }
                    }}
                  >
                    Remove
                  </Button>
                </div>
              ) : (
                <label
                  htmlFor="pitch-deck-file"
                  className="flex min-h-11 w-full cursor-pointer items-center justify-center rounded-xl border border-dashed border-border-strong bg-surface px-4 py-3 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-text-primary"
                >
                  Choose PDF file&hellip;
                </label>
              )}
            </div>
          </div>

          <Textarea
            id="company-text"
            label="Additional Company Information"
            value={companyText}
            onChange={(event) => setCompanyText(event.target.value)}
            placeholder={COMPANY_TEXT_PLACEHOLDER}
            rows={8}
            className="font-mono"
          />

          <p className="text-sm text-text-secondary">
            At least one source is required. Provide any combination --
            SIE combines everything you give it into one analysis.
          </p>

          {/* Portfolio Release Task 3B -- Secure Analysis Visibility.
              Analyses are now private by default (approved decision):
              GET /startup/{name} and every intelligence surface (Rankings,
              Discovery, Search, Compare, history) are scoped server-side
              to the submitter, an approved startup member, or an admin --
              never anyone else, signed in or not. This replaces the
              earlier, now-inaccurate assumption that a submitted analysis
              becomes a public URL; it's the opposite by default. See
              app/database/db.py::_analysis_visibility_clause() for the
              enforced rule this disclosure describes. */}
          <p className="rounded-xl border border-border bg-surface px-4 py-3 text-sm text-text-secondary">
            <span className="font-semibold text-text-primary">Private by default.</span>{" "}
            Only you can see this analysis, unless you later claim the startup and add other
            approved members -- including anything from an uploaded pitch deck.
          </p>

          {error ? (
            <ErrorMessage
              action={
                error === SESSION_EXPIRED_MESSAGE ? (
                  <Link href="/sign-in" className="font-semibold underline hover:text-danger/80">
                    Sign in
                  </Link>
                ) : undefined
              }
            >
              {error}
            </ErrorMessage>
          ) : null}

          <Button type="submit">
            {isFounderTargeted ? "Update Startup" : "Analyze Startup"}
          </Button>
        </form>
      ) : (
        <AnalyzingState elapsedSeconds={elapsedSeconds} />
      )}
    </>
  );
}

function AnalyzingState({ elapsedSeconds }: { elapsedSeconds: number }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-8">
      <div className="flex items-center gap-4">
        <span
          aria-hidden="true"
          className="h-8 w-8 shrink-0 animate-spin rounded-full border-2 border-border-strong border-t-primary"
        />

        <div>
          <p className="text-lg font-semibold text-text-primary">
            Analyzing startup&hellip;
          </p>

          <p className="mt-1 text-sm text-text-secondary">
            SIE is researching and evaluating this startup. This typically
            takes a few minutes -- please keep this tab open.
          </p>
        </div>
      </div>

      <p className="mt-6 text-sm text-text-secondary" aria-live="polite">
        Elapsed: {formatElapsed(elapsedSeconds)}
      </p>

      <div className="mt-6 border-t border-border pt-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          What SIE evaluates
        </p>

        <ul className="mt-3 space-y-2 text-sm text-text-secondary">
          {STAGES.map((stage) => (
            <li key={stage} className="flex items-center gap-2.5">
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 shrink-0 rounded-full bg-border-strong"
              />
              {stage}
            </li>
          ))}
        </ul>

        <p className="mt-4 text-sm text-text-secondary">
          This describes what the analysis covers, not live progress -- SIE
          doesn&rsquo;t currently report which stage is in flight, so no
          single step is shown as complete until the whole analysis
          finishes.
        </p>
      </div>
    </div>
  );
}
