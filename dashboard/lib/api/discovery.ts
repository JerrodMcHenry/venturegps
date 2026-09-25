import type { DiscoveryFilterOptions, DiscoveryFilters, DiscoveryResponse } from "@/types";

import { apiFetch } from "./client";

// Portfolio Release Task 3B -- Secure Analysis Visibility: both endpoints
// now require auth and return only the caller's own authorized analyses
// (approved decision -- no public scores-only exception). `token` is
// required, not optional, on both -- there is no public/unauthenticated
// way to call either endpoint anymore.

function buildDiscoveryQueryString(filters: DiscoveryFilters): string {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }

    params.set(key, String(value));
  }

  const queryString = params.toString();
  return queryString ? `?${queryString}` : "";
}

export function discoverStartups(
  filters: DiscoveryFilters = {},
  token: string | null
): Promise<DiscoveryResponse> {
  return apiFetch<DiscoveryResponse>(
    `/discover${buildDiscoveryQueryString(filters)}`,
    { token }
  );
}

export function getDiscoveryFilterOptions(token: string | null): Promise<DiscoveryFilterOptions> {
  return apiFetch<DiscoveryFilterOptions>("/discover/filter-options", { token });
}
