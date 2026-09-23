import { auth } from "@clerk/nextjs/server";

import V2ReviewView from "./V2ReviewView";

// Increment 18.4 -- internal V2 evidence review interface. Mirrors app/admin/analytics/page.tsx exactly:
// auth.protect() here is only a "signed in" UX gate (identical to every other protected page in this app).
// REAL admin authorization happens server-side, in the FastAPI backend, via the existing RequireAdmin
// dependency (app/auth.py's ADMIN_USER_IDS allowlist, unchanged) on every /admin/v2-review/* route. A
// signed-in non-admin who navigates here sees V2ReviewView's own "Access denied" state (a real 403 from the
// backend), never real candidate/evidence data -- there is no client-side admin check anywhere standing in
// for that.
export default async function V2ReviewPage() {
  await auth.protect();

  return <V2ReviewView />;
}
