"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { submitStartupClaim } from "@/lib/api";

import type { StartupClaimSubmissionResponse } from "@/types";

const MAX_JUSTIFICATION_LENGTH = 2000;

type ClaimStartupFormProps = {
  startupId: number;
  onSubmitted: (result: StartupClaimSubmissionResponse) => void;
  onDismiss: () => void;
};

// Phase 7.1B, Part 2: deliberately small -- one required field, one
// optional field, and copy that is explicit about what this is NOT
// (automated verification, domain verification, legal ownership
// verification, a guarantee of approval or of review time). Nothing here
// implies submitting changes the public startup intelligence or SPS.
export default function ClaimStartupForm({
  startupId,
  onSubmitted,
  onDismiss,
}: ClaimStartupFormProps) {
  const { getToken } = useAuth();
  const [justification, setJustification] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedJustification = justification.trim();

    if (!trimmedJustification) {
      setError("Let us know how you're connected to this startup.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const token = await getToken();

      if (!token) {
        setError("Your session expired. Please sign in again.");
        setIsSubmitting(false);
        return;
      }

      const result = await submitStartupClaim(
        {
          startup_id: startupId,
          justification: trimmedJustification,
          contact_email: contactEmail.trim() || null,
        },
        token
      );

      onSubmitted(result);
    } catch (submitError) {
      console.error("Failed to submit startup claim:", submitError);

      // Form input (justification/contactEmail) is deliberately left
      // exactly as typed on every error path below -- never cleared.
      const message = submitError instanceof Error ? submitError.message : "";

      if (/\(404\)/.test(message)) {
        setError("This startup couldn't be found. Try refreshing the page.");
      } else if (/already have a pending claim/i.test(message)) {
        setError("You already have a pending claim for this startup.");
      } else if (/already have access/i.test(message)) {
        setError("You already have access to this startup — no claim is needed.");
      } else if (/\(401\)/.test(message)) {
        setError("Your session expired. Please sign in again.");
      } else {
        setError("Your claim could not be submitted. Please try again.");
      }

      setIsSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-xl border border-border bg-surface p-4"
    >
      <div>
        <label
          htmlFor="claim-justification"
          className="mb-1.5 block text-sm font-medium text-text-primary"
        >
          Tell us how you&rsquo;re connected to this startup
        </label>

        <textarea
          id="claim-justification"
          rows={3}
          maxLength={MAX_JUSTIFICATION_LENGTH}
          value={justification}
          onChange={(event) => setJustification(event.target.value)}
          placeholder="e.g. I'm a cofounder, I run product here, I'm on the founding team..."
          disabled={isSubmitting}
          className="w-full resize-y rounded-lg border border-border bg-background px-3 py-2 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20 disabled:opacity-60"
        />
      </div>

      <div>
        <label
          htmlFor="claim-contact-email"
          className="mb-1.5 block text-sm font-medium text-text-primary"
        >
          Contact email <span className="font-normal text-text-muted">(optional)</span>
        </label>

        <input
          id="claim-contact-email"
          type="email"
          value={contactEmail}
          onChange={(event) => setContactEmail(event.target.value)}
          placeholder="you@company.com"
          disabled={isSubmitting}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20 disabled:opacity-60"
        />
      </div>

      <p className="text-base leading-7 text-text-secondary">
        We manually review startup claims before granting founder access —
        we don&rsquo;t verify domains or documents automatically, and review
        isn&rsquo;t instant. Submitting a claim never changes this startup&rsquo;s
        public intelligence or VentureGPS Score.
      </p>

      {error ? <p className="text-xs text-danger">{error}</p> : null}

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? "Submitting..." : "Submit Claim"}
        </button>

        <button
          type="button"
          onClick={onDismiss}
          disabled={isSubmitting}
          className="rounded-lg px-3 py-2 text-sm font-semibold text-text-muted transition-colors hover:text-text-secondary disabled:cursor-not-allowed disabled:opacity-60"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
