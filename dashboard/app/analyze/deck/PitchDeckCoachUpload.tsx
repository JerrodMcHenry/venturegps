"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import PageHeader from "@/components/layout/PageHeader";
import Button from "@/components/ui/Button";
import ErrorMessage from "@/components/ui/ErrorMessage";
import { uploadPitchDeckReview } from "@/lib/api";

// Phase 10.8 -- Pitch Deck Coach V1. A deliberately narrow upload flow --
// PDF only, no website/text fields, no founder-targeted mode -- this is
// NOT AnalyzeStartupForm with an extra button. It posts to a completely
// separate endpoint (POST /pitch-deck-reviews) that never touches
// Methodology v2/SPS (see app/ai/pitch_deck_coaching.py's own module
// docstring). Mirrors AnalyzeStartupForm.tsx's proven upload UX
// (client-side size/type check, elapsed timer, beforeunload guard,
// status-code-driven error copy) rather than inventing a new pattern,
// without importing anything from that file -- these two products must
// stay free to diverge.
const MAX_PDF_BYTES = 15 * 1024 * 1024;

const STAGES = [
  "Reading your deck",
  "Reconstructing the story it tells",
  "Checking what investors look for, slide by slide",
  "Prioritizing what to fix first",
  "Preparing likely investor questions",
];

const SESSION_EXPIRED_MESSAGE = "Your session has expired. Please sign in again to continue.";

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function validatePdfFile(file: File | null): string | null {
  if (!file) {
    return "Choose a PDF pitch deck to review.";
  }

  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return "Only PDF files are supported.";
  }

  if (file.size > MAX_PDF_BYTES) {
    return `That PDF is too large to review (max ${MAX_PDF_BYTES / (1024 * 1024)} MB).`;
  }

  return null;
}

type Status = "idle" | "submitting" | "error";

export default function PitchDeckCoachUpload() {
  const router = useRouter();
  const { getToken } = useAuth();

  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

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

  useEffect(() => {
    if (!isSubmitting) {
      return;
    }

    function handleBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = "";
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isSubmitting]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    const validationError = validatePdfFile(pdfFile);

    if (validationError) {
      setStatus("error");
      setError(validationError);
      return;
    }

    setStatus("submitting");
    setError(null);
    setElapsedSeconds(0);

    try {
      const token = await getToken();

      if (!token) {
        setStatus("error");
        setError(SESSION_EXPIRED_MESSAGE);
        return;
      }

      const review = await uploadPitchDeckReview(pdfFile as File, token);
      router.push(`/analyze/deck/${review.id}`);
    } catch (caughtError) {
      console.error("Pitch Deck Coach upload failed:", caughtError);

      const message = caughtError instanceof Error ? caughtError.message : "";

      setStatus("error");
      setError(
        /Request timed out/.test(message)
          ? "This is taking longer than expected and timed out. Your file hasn't been lost -- you can try again."
          : /Network error/.test(message)
            ? "Couldn't reach the SIE backend. Confirm it's running, then try again."
            : /API request failed \(401\)/.test(message)
              ? SESSION_EXPIRED_MESSAGE
              : /API request failed \(429\)/.test(message)
                ? "You've reached the current limit on pitch deck reviews. Please try again later."
                : /API request failed \(400\)/.test(message)
                  ? "That PDF couldn't be read. Please check the file and try again."
                  : "We couldn't review that deck right now. Your file hasn't been lost -- you can try again."
      );
    }
  }

  return (
    <>
      <PageHeader
        title="Review My Pitch Deck"
        subtitle="Upload a PDF pitch deck -- SIE will reconstruct the story it tells, show what's working and what's unclear, and give you a short list of what to fix first."
      />

      {!isSubmitting ? (
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label
              htmlFor="pitch-deck-coach-file"
              className="text-sm font-semibold uppercase tracking-wide text-text-secondary"
            >
              Pitch Deck (PDF)
            </label>

            <input
              id="pitch-deck-coach-file"
              ref={pdfInputRef}
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => setPdfFile(event.target.files?.[0] ?? null)}
              className="hidden"
            />

            <div className="mt-2">
              {pdfFile ? (
                <div className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-3">
                  <span className="truncate text-sm text-text-primary">{pdfFile.name}</span>

                  <Button
                    type="button"
                    variant="subtle"
                    size="sm"
                    onClick={() => {
                      setPdfFile(null);
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
                  htmlFor="pitch-deck-coach-file"
                  className="flex min-h-24 w-full cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-border-strong bg-surface px-4 py-6 text-center text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-text-primary"
                >
                  <span>Drop your PDF here, or choose a file&hellip;</span>
                  <span className="text-xs font-normal text-text-muted">Max 15 MB</span>
                </label>
              )}
            </div>
          </div>

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

          <Button type="submit">Review My Deck</Button>

          <p className="text-sm text-text-secondary">
            This is a coaching tool, not an investment decision -- it never scores your startup and
            never affects any VentureGPS Score. It&rsquo;s private to your account.
          </p>
        </form>
      ) : (
        <ReviewingState elapsedSeconds={elapsedSeconds} />
      )}
    </>
  );
}

function ReviewingState({ elapsedSeconds }: { elapsedSeconds: number }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-8">
      <div className="flex items-center gap-4">
        <span
          aria-hidden="true"
          className="h-8 w-8 shrink-0 animate-spin rounded-full border-2 border-border-strong border-t-primary"
        />

        <div>
          <p className="text-lg font-semibold text-text-primary">Reading your deck&hellip;</p>
          <p className="mt-1 text-sm text-text-secondary">
            This usually takes under a minute -- please keep this tab open.
          </p>
        </div>
      </div>

      <p className="mt-6 text-sm text-text-secondary" aria-live="polite">
        Elapsed: {formatElapsed(elapsedSeconds)}
      </p>

      <div className="mt-6 border-t border-border pt-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">What&rsquo;s happening</p>

        <ul className="mt-3 space-y-2 text-sm text-text-secondary">
          {STAGES.map((stage) => (
            <li key={stage} className="flex items-center gap-2.5">
              <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-border-strong" />
              {stage}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
