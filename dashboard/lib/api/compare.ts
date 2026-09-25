import type { ComparisonResponse } from "@/types";

import { apiFetch } from "./client";

// Portfolio Release Task 3B -- Secure Analysis Visibility: GET /compare
// now requires auth and resolves only startup_ids the caller is
// authorized to see -- an explicit, correct startup_id for an analysis
// the caller isn't authorized for resolves to nothing (missing_startup_ids),
// never a leak (approved decision, item 4: explicit IDs must not bypass
// authorization). `token` is required, not optional.
export function compareStartups(
  startupIds: number[],
  token: string | null
): Promise<ComparisonResponse> {
  return apiFetch<ComparisonResponse>(
    `/compare?startups=${startupIds.join(",")}`,
    { token }
  );
}
