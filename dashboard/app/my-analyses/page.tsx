import { auth } from "@clerk/nextjs/server";

import MyAnalysesView from "./MyAnalysesView";

// Portfolio Release Task 4 -- My Analyses, Phase 3. Same server-wrapper
// auth pattern as app/rankings/page.tsx: auth.protect() is the real,
// resource-based, server-side gate. This protects the FRONTEND route
// only -- GET /me/analyses on the backend enforces its own RequireAuth
// independently (app/auth.py), so a direct API call without a token
// still can't reach any data either way.
export default async function MyAnalysesPage() {
  await auth.protect();

  return <MyAnalysesView />;
}
