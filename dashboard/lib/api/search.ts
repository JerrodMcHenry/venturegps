import type { StartupSearchResult } from "@/types";

import { apiFetch } from "./client";

// Portfolio Release Task 3B -- Secure Analysis Visibility: GET
// /analyses/search now requires auth and returns only the caller's own
// authorized analyses (approved decision -- no public scores-only
// exception). `token` is required, not optional.
export function searchStartups(query: string, token: string | null): Promise<StartupSearchResult[]> {
  return apiFetch<StartupSearchResult[]>(
    `/analyses/search?query=${encodeURIComponent(query)}`,
    { token }
  );
}
