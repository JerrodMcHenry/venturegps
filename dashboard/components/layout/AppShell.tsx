"use client";

import { usePathname } from "next/navigation";

import TopNav from "./TopNav";
import MobileTabBar from "./MobileTabBar";
import PublicHeader from "./PublicHeader";
import PublicNav from "./PublicNav";

type AppShellProps = {
  children: React.ReactNode;
};

// Phase 10.3 -- Shell & Navigation Reset. Replaces the previous fixed-
// width desktop sidebar (Sidebar.tsx, now removed) with a sticky top
// navigation bar (TopNav) and a purpose-built mobile bottom tab bar
// (MobileTabBar) -- see both components' own docstrings for the full
// design record. No route/auth logic lives here or ever did; this file
// is pure layout chrome.
//
// The old shell permanently reserved 288px (`lg:pl-72`) for the sidebar
// on every single page, including narrow, focused ones. That offset is
// gone entirely -- content now has the full viewport width to work with,
// and any page that wants a narrower reading column constrains itself
// (e.g. NewVentureForm's own `max-w-2xl`), rather than the shell forcing
// one width on everything. max-w-[1600px] is kept as the outer ceiling
// (unchanged from before) so wide data pages (Rankings, Discovery,
// Compare) render exactly as they did previously -- this phase changes
// the chrome around pages, not their own internal layouts (Part 4/9).
//
// Also fixes a pre-existing bug while touching this file anyway:
// previously hardcoded `bg-slate-950 text-white` ignored the light/dark
// theme entirely (every page's own content already read the real
// --background/--foreground tokens; only this outer shell didn't) --
// now uses the same token-driven classes as everything else, which is
// what actually makes light mode work correctly at the shell level for
// the first time.
//
// Increment 15.1 -- Consumer Experience Refinement, Part 1: a public
// VentureGPS route (currently only /markets/[slug]) must not show the
// legacy "Build / Analyze / My Startups / Learn" Startup Intelligence
// Engine navigation or its mobile tab bar -- that chrome is for the
// existing founder-facing product and would misbrand/confuse a visitor
// arriving from a VentureGPS video link. Rather than restructuring the
// route tree into parallel root layouts (a much larger, riskier change
// this increment's own "frontend refinement only" scope forbids), this
// branches on pathname -- the SAME pattern TopNav.tsx/MobileTabBar.tsx
// already use internally (`usePathname()`, `"use client"`) for their own
// active-route highlighting, just one level up. Legacy routes render
// byte-identical chrome to before; only the /markets prefix's chrome
// changes, and children (server-rendered page content either way) are
// unaffected either way -- see "passing Server Components as children to
// a Client Component" in Next's own docs.
// Increment 16: "/design" added for the dev-only Consumer Experience Blueprint prototype
// (app/design/discover/page.tsx) -- a brand-new route prefix nothing else uses, so this is purely additive; no
// existing route's chrome changes. Gets the same minimal VentureGPS branding /markets used to, since the whole
// point of the prototype is reviewing the VentureGPS brand experience without legacy chrome bleeding in.
//
// Increment 17.1: "/markets" removed from this list -- it now matches REAL_PUBLIC_NAV_ROUTE_PREFIXES below
// instead (checked first), which is what actually renders for it now. Left as a single-entry list rather than
// collapsed into a plain `pathname.startsWith` check so a future prototype route can be added the same additive
// way "/design" was.
const PUBLIC_ROUTE_PREFIXES = ["/design"];

// Increment 16.2 (Cinematic Homepage hero refinement), Part 4: the cinematic hero builds its own complete,
// self-contained nav overlay as part of its full-bleed composition -- PublicHeader stacked above it duplicated
// that nav (two "VentureGPS" wordmarks, two navigation rows) and ate vertical space from a hero whose whole
// point is an uninterrupted first viewport. `BARE_ROUTE_PREFIXES` renders children with NO shared header at
// all, checked before PUBLIC_ROUTE_PREFIXES -- scoped to exactly this one route; every other /design/* prototype
// (direction-a/b/c, discover, directions) is unaffected and still gets PublicHeader as before.
//
// Increment 17.1: "/" joins this list for the identical reason -- the production homepage's VentureGpsHero
// (promoted from the cinematic-homepage prototype) renders the real PublicNav itself, as part of its own
// full-bleed composition, so a second shared header stacked above it would duplicate the wordmark/nav exactly as
// it would have for the prototype.
const BARE_ROUTE_PREFIXES = ["/design/cinematic-homepage", "/"];

// Increment 17.1: "/markets" moved out of PUBLIC_ROUTE_PREFIXES into its own group -- it now gets the real,
// functional PublicNav (working links + mobile menu) rather than PublicHeader (deliberately branding-only, no
// links, since no second real public route existed when it was written). "/design" stays on PublicHeader,
// unchanged -- Increment 17.1's own instruction is to keep the original prototype available in development
// exactly as it already behaves, not to upgrade its chrome too.
const REAL_PUBLIC_NAV_ROUTE_PREFIXES = ["/markets"];

function matchesPrefix(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((prefix) => (prefix === "/" ? pathname === "/" : pathname === prefix || pathname.startsWith(`${prefix}/`)));
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();

  if (matchesPrefix(pathname, BARE_ROUTE_PREFIXES)) {
    return <div className="min-h-screen bg-background text-foreground">{children}</div>;
  }

  if (matchesPrefix(pathname, REAL_PUBLIC_NAV_ROUTE_PREFIXES)) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <PublicNav variant="header" />
        <main className="min-h-screen">{children}</main>
      </div>
    );
  }

  if (matchesPrefix(pathname, PUBLIC_ROUTE_PREFIXES)) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <PublicHeader />
        <main className="min-h-screen">{children}</main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopNav />

      {/* Phase 32, Part 2/12: md:pb-0 -> lg:pb-0 -- matches the exact
          breakpoint TopNav.tsx/MobileTabBar.tsx now swap at, so page
          content never loses its bottom-tab-bar clearance between 768px
          and 1024px (where the bottom tab bar still renders). */}
      <main className="min-h-screen pb-24 lg:pb-0">
        <div className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">
          {children}
        </div>
      </main>

      <MobileTabBar />
    </div>
  );
}
