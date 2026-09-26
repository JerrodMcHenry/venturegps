import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// SIE Authentication Phase 1: Next.js 16 renamed middleware.ts to
// proxy.ts (confirmed against the installed Next.js 16.2.9 docs --
// "Starting with Next.js 16, Middleware is now called Proxy... The
// functionality remains the same") -- this file is that rename, not a
// new concept.
//
// This is a UX-only optimistic redirect layer, NOT the real security
// boundary -- confirmed by BOTH Clerk's and Next.js's own current
// guidance (see the Phase 1 compatibility spike), and now also by the
// installed @clerk/nextjs package itself: createRouteMatcher is marked
// @deprecated in this version ("Use resource-based auth checks instead
// ... Middleware-based auth checks rely on path matching, which can
// diverge from how Next.js routes requests and leave protected
// resources reachable"). It still works (not removed until a future
// major version) and the task explicitly wants this redirect at the
// proxy layer, so it's used here -- but the REAL enforcement is the
// auth.protect() call inside /analyze's own page.tsx (Server Component,
// resource-based, not deprecated), which does not depend on this file's
// route list being correct or complete. /saved doesn't exist as a page
// yet -- it's listed here only so the matcher already anticipates it
// once it's built; no Saved Startups behavior is implemented in this
// slice.
//
// IMPORTANT: this protects Next.js page navigation only. The FastAPI
// backend (POST /analyze and friends) enforces nothing yet -- that's
// Phase 2. A direct call to the backend bypasses this file entirely.
// Idea Lab / Venture Simulator V1: /idea-lab added alongside /analyze and
// /saved -- same UX-only redirect, real enforcement is each page's own
// auth.protect() (app/idea-lab/page.tsx, app/idea-lab/new/page.tsx,
// app/idea-lab/[id]/page.tsx).
//
// Phase 7.2 -- Founder Workspace V1: /founder added the same way. Real
// enforcement is each page's own auth.protect() (app/founder/page.tsx,
// app/founder/startups/[startupId]/page.tsx) PLUS, for a specific
// startup's data, the backend's own RequireStartupMember dependency
// (app/auth.py) -- this route-matcher redirect has no bearing on which
// startups a signed-in user may see, only on whether /founder(.*) is
// reachable at all while signed out.
//
// Phase 9 -- Investor Workspace V1: /investor added the same way. Real
// enforcement is app/investor/page.tsx's own auth.protect() PLUS the
// backend's RequireAuth (not RequireStartupMember -- Investor Workspace
// is personal, not membership-gated).
//
// Portfolio Release Task 3B -- Secure Analysis Visibility: /startup,
// /rankings, /search, /compare added -- all four were public until this
// task (approved decision: no public scores-only exception). Same UX-only
// redirect; real enforcement is each page's own auth.protect() PLUS the
// backend's own independent auth + the submitter/approved-member/admin
// visibility rule (app/auth.py, app/database/db.py's
// _analysis_visibility_clause()) -- this route-matcher redirect has no
// bearing on WHICH analyses a signed-in user may see, only on whether
// these routes are reachable at all while signed out.
// Portfolio Release Task 4 -- My Analyses: /my-analyses added the same
// way every other Task 3B route was -- UX-only redirect here; real
// enforcement is app/my-analyses/page.tsx's own auth.protect() PLUS the
// backend's independent RequireAuth on GET /me/analyses.
const isProtectedRoute = createRouteMatcher([
  "/analyze(.*)",
  "/saved(.*)",
  "/idea-lab(.*)",
  "/founder(.*)",
  "/investor(.*)",
  "/startup(.*)",
  "/rankings(.*)",
  "/search(.*)",
  "/compare(.*)",
  "/my-analyses(.*)",
]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtectedRoute(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
  ],
};
