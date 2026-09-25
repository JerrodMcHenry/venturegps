import type { RankingEntry } from "@/types";

import { apiFetch } from "./client";

// Portfolio Release Task 3B -- Secure Analysis Visibility: GET /rankings
// now requires auth and returns only the caller's own authorized analyses
// (approved decision -- no public scores-only exception). `token` is
// required, not optional -- there is no public/unauthenticated way to
// call this endpoint anymore, so every caller of this function must have
// one to pass.
export function getRankings(token: string | null): Promise<RankingEntry[]> {
  return apiFetch<RankingEntry[]>("/rankings", { token });
}
