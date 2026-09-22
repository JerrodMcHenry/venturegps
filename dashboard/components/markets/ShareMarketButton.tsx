"use client";

// VentureGPS Increment 15, Part 6 -- Sharing/social distribution. Web Share API where the browser supports it
// (the primary path for a mobile visitor arriving from a video link -- YouTube/TikTok/Instagram in-app browsers
// all support navigator.share on iOS/Android), falling back to copy-to-clipboard everywhere else. Never throws
// an unhandled error on a user cancelling their OS share sheet (AbortError is expected, not a failure).
import { useState } from "react";

import Button from "@/components/ui/Button";

type ShareMarketButtonProps = {
  url: string;
  title: string;
};

export default function ShareMarketButton({ url, title }: ShareMarketButtonProps) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);

  async function handleShare() {
    setCopyFailed(false);

    if (typeof navigator !== "undefined" && "share" in navigator) {
      try {
        await navigator.share({ title, url });
        return;
      } catch (error) {
        // A user dismissing the native share sheet rejects with AbortError -- not a failure, nothing to report.
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        // Any other share failure (e.g. a permissions error) falls through to the copy-link path below.
      }
    }

    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyFailed(true);
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <Button type="button" variant="secondary" size="md" onClick={handleShare} aria-live="polite">
        {copied ? "Link copied" : "Share this market"}
      </Button>

      {copyFailed ? (
        <p className="text-sm text-text-muted">
          Couldn&rsquo;t copy automatically -- here&rsquo;s the link:{" "}
          <a href={url} className="font-medium text-primary underline underline-offset-2">
            {url}
          </a>
        </p>
      ) : null}
    </div>
  );
}
