import { auth } from "@clerk/nextjs/server";

import RankingsView from "./RankingsView";

// Portfolio Release Task 3B -- Secure Analysis Visibility: Rankings is no
// longer public (approved decision -- no public scores-only exception).
// Same server-wrapper auth pattern as app/analyze/page.tsx: auth.protect()
// is the real, resource-based, server-side gate, redirecting a signed-out
// visitor to /sign-in itself. This protects the FRONTEND route only --
// GET /rankings on the backend enforces its own auth independently (see
// app/auth.py's RequireAuth), so a direct API call without a token still
// can't reach the data either way.
export default async function RankingsPage() {
  await auth.protect();

  return <RankingsView />;
}
