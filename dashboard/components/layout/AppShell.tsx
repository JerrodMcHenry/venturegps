"use client";

import { usePathname } from "next/navigation";

import TopNav from "./TopNav";
import MobileTabBar from "./MobileTabBar";
import PublicHeader from "./PublicHeader";

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
const PUBLIC_ROUTE_PREFIXES = ["/markets"];

function isPublicRoute(pathname: string): boolean {
  return PUBLIC_ROUTE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();

  if (isPublicRoute(pathname)) {
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
