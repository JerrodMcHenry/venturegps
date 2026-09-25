import { apiFetch } from "./client";

import type { SPSHistoryPoint, StartupProfileResponse } from "@/types";

// Portfolio Release Task 3B -- Secure Analysis Visibility: both endpoints
// now require auth and are scoped to analyses the caller is authorized to
// see (submitter, approved member, or admin -- never a public route
// anymore). `token` is required, not optional -- app/startup/[id]/page.tsx
// (a Server Component) obtains it via Clerk's server-side auth().getToken()
// and passes it straight through.
export async function getStartupProfile(
  companyName: string,
  token: string | null
): Promise<StartupProfileResponse> {
  return apiFetch<StartupProfileResponse>(
    `/startup/${encodeURIComponent(companyName)}`,
    { token }
  );
}

export async function getSPSHistory(
  companyName: string,
  token: string | null
): Promise<SPSHistoryPoint[]> {
  return apiFetch<SPSHistoryPoint[]>(
    `/startup/${encodeURIComponent(companyName)}/sps-history`,
    { token }
  );
}
