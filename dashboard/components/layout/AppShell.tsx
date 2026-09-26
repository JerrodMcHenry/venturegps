"use client";

import { usePathname } from "next/navigation";

import PublicNav from "./PublicNav";
import PublicHeader from "./PublicHeader";

type AppShellProps = {
  children: React.ReactNode;
};

// Phase 10.3 -- Shell & Navigation Reset. Replaces the previous fixed-
// width desktop sidebar (Sidebar.tsx, now removed) with a shared top nav
// bar. No route/auth logic lives here or ever did; this file is pure
// layout chrome.
//
// Portfolio Release Task 4 -- Unified UX, Phase 2: this file used to
// branch THREE ways -- bare chrome, PublicNav for a small allowlist of
// "real" VentureGPS routes, PublicHeader for dev prototypes, and a
// fourth, completely separate TopNav + MobileTabBar pair for literally
// everything else (the whole authenticated application). That fourth
// branch was the actual "entirely different navigation and visual
// systems" problem this phase exists to remove. TopNav.tsx and
// MobileTabBar.tsx are deleted; PublicNav is now THE nav for every route
// except the two below, so REAL_PUBLIC_NAV_ROUTE_PREFIXES (the old
// allowlist) no longer exists -- there is nothing left for it to
// distinguish. Also gone: the separate bottom MobileTabBar on mobile --
// PublicNav's own responsive disclosure panel is the one mobile
// implementation now (see that file's own header comment on "avoid
// duplicating desktop and mobile navigation logic").
//
// The old shell permanently reserved 288px (`lg:pl-72`) for the sidebar
// on every single page, including narrow, focused ones. That offset is
// gone entirely -- content now has the full viewport width to work with,
// and any page that wants a narrower reading column constrains itself
// (e.g. NewVentureForm's own `max-w-2xl`), rather than the shell forcing
// one width on everything. max-w-[1600px] is kept as the outer ceiling
// (unchanged from before) so wide data pages (Rankings, Discovery,
// Compare) render exactly as they did previously -- this phase changes
// the chrome around pages, not their own internal layouts.
//
// A public VentureGPS route (currently only /markets/[slug]) must not
// show the legacy "Build / Analyze / My Startups / Learn" Startup
// Intelligence Engine navigation or its mobile tab bar -- that chrome
// was for the pre-Task-4 founder-facing product and would misbrand/
// confuse a visitor arriving from a VentureGPS video link. Moot now that
// there is only one nav system, but the branching shape (pathname-based,
// same pattern PublicNav.tsx itself uses for active-route highlighting)
// is unchanged from before.
const PUBLIC_ROUTE_PREFIXES = ["/design"];

// Increment 16.2 (Cinematic Homepage hero refinement), Part 4: the cinematic hero builds its own complete,
// self-contained nav overlay as part of its full-bleed composition -- a shared header stacked above it would
// duplicate the nav (two "VentureGPS" wordmarks, two navigation rows) and eat vertical space from a hero whose
// whole point is an uninterrupted first viewport. `BARE_ROUTE_PREFIXES` renders children with NO shared header at
// all, checked before PUBLIC_ROUTE_PREFIXES -- scoped to exactly this one route; every other /design/* prototype
// (direction-a/b/c, discover, directions) is unaffected and still gets PublicHeader as before.
//
// "/" stays on this list for the identical reason -- the production homepage's VentureGpsHero renders the real
// PublicNav itself (variant="overlay"), as part of its own full-bleed composition, so a second shared header
// stacked above it would duplicate the wordmark/nav exactly as it would have for the prototype. This is NOT a
// "no homepage redesign" boundary -- Task 4 Phase 4 changes the homepage's own headline/CTA/copy freely -- it is
// only about which component renders the nav chrome (the hero itself, not this shell).
const BARE_ROUTE_PREFIXES = ["/design/cinematic-homepage", "/"];

function matchesPrefix(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((prefix) => (prefix === "/" ? pathname === "/" : pathname === prefix || pathname.startsWith(`${prefix}/`)));
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();

  if (matchesPrefix(pathname, BARE_ROUTE_PREFIXES)) {
    return <div className="min-h-screen bg-background text-foreground">{children}</div>;
  }

  if (matchesPrefix(pathname, PUBLIC_ROUTE_PREFIXES)) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <PublicHeader />
        <main className="min-h-screen">{children}</main>
      </div>
    );
  }

  // Every other route -- /markets, /admin, and the entire authenticated
  // application alike -- gets the same PublicNav (header variant). No
  // separate bottom tab bar; PublicNav's own mobile disclosure panel
  // covers small viewports for every one of these routes now.
  return (
    <div className="min-h-screen bg-background text-foreground">
      <PublicNav variant="header" />

      <main className="min-h-screen">
        <div className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">
          {children}
        </div>
      </main>
    </div>
  );
}
