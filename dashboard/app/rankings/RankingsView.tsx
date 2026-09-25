"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import PageHeader from "@/components/layout/PageHeader";
import RankingsTable from "@/components/rankings/RankingsTable";
import ErrorMessage from "@/components/ui/ErrorMessage";
import Skeleton from "@/components/ui/Skeleton";

import { getRankings } from "@/lib/api";

import type { RankingEntry } from "@/types";

// Portfolio Release Task 3B -- Secure Analysis Visibility: this used to be
// app/rankings/page.tsx itself, fully public. GET /rankings now requires
// auth and returns only THIS caller's own authorized analyses (approved
// decision -- no public scores-only exception), so this component needs a
// real Clerk token -- same useAuth()/getToken() pattern
// AnalyzeStartupForm.tsx already established, since this stays a Client
// Component (its own interactive loading/error state genuinely needs to
// run client-side) rendered by page.tsx after that file's own server-side
// auth.protect() check.
export default function RankingsView() {
  const { getToken } = useAuth();
  const [rankings, setRankings] = useState<RankingEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadRankings() {
      try {
        setIsLoading(true);
        setError(null);

        const token = await getToken();
        const data = await getRankings(token);

        if (isMounted) {
          setRankings(data);
        }
      } catch (error) {
        console.error("Failed to load rankings:", error);

        if (isMounted) {
          setError("The rankings could not be loaded.");
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    loadRankings();

    return () => {
      isMounted = false;
    };
  }, [getToken]);

  return (
    <>
      <PageHeader
        title="Rankings"
        subtitle="See how real startups compare — and what's driving their scores."
        action={
          <Link
            href="/search"
            className="text-sm font-semibold text-primary hover:text-primary-hover"
          >
            Advanced search &amp; compare →
          </Link>
        }
      />

      {isLoading ? (
        // Phase 10.11, Part 8/12: Design System V2's own Skeleton --
        // this was still the pre-migration hardcoded slate-800/900
        // (dark-only) box, invisible on a light background.
        <Skeleton className="h-96 w-full" />
      ) : error ? (
        <ErrorMessage>
          <h2 className="font-semibold text-danger">Unable to load rankings</h2>
          <p className="mt-2 text-sm text-danger/80">{error}</p>
        </ErrorMessage>
      ) : (
        <>
          <RankingsTable rankings={rankings} />

          {/* Phase 10.11, Part 19: a restrained contextual bridge back
              into Build -- Explore should inspire builders, not only
              serve investors. Existing route only. */}
          {rankings.length > 0 ? (
            <p className="mt-6 text-center text-sm text-text-secondary">
              Inspired by what you see?{" "}
              <Link href="/idea-lab" className="font-semibold text-primary hover:text-primary-hover">
                Build your own idea →
              </Link>
            </p>
          ) : null}
        </>
      )}
    </>
  );
}
