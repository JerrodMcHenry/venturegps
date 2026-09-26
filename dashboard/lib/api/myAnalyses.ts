import type { MyAnalysisEntry } from "@/types";

import { apiFetch } from "./client";

// Portfolio Release Task 4 -- My Analyses. GET /me/analyses requires auth
// (RequireAuth, no admin/membership bypass -- see app/api.py's own
// comment) and returns only analyses THIS caller submitted, newest
// first. `token` is required, not optional -- same convention every
// other Task-3B-scoped client function in this directory already uses
// (getRankings, discoverStartups, etc.) -- there is no public,
// unauthenticated way to call this endpoint.
export function getMyAnalyses(token: string | null): Promise<MyAnalysisEntry[]> {
  return apiFetch<MyAnalysisEntry[]>("/me/analyses", { token });
}
