"use client";

// Portfolio Release Task 4 -- Unified UX, Analysis Retrieval and
// Authentication, Phase 2. This is now THE single, reusable navigation
// system for the homepage AND the authenticated application -- not "the
// public one" alongside a separate TopNav for signed-in users. Before
// this phase, the homepage/`/markets`/`/admin` rendered this component
// while every other route (the whole authenticated app) rendered a
// completely separate TopNav.tsx (desktop) + MobileTabBar.tsx (mobile)
// pair, with its own brand mark, its own destination list, and its own
// account-menu wiring -- exactly the "entirely different navigation and
// visual systems" problem this phase exists to remove. TopNav.tsx and
// MobileTabBar.tsx are deleted; PRIMARY_NAVIGATION (the signed-in
// destination list) now lives here, as the one array both the desktop
// row and the mobile disclosure panel below render from -- never two
// hand-authored lists (see this file's own docstring on
// SIGNED_IN_NAVIGATION for the "avoid duplicating desktop and mobile
// navigation logic" instruction this satisfies).
//
// Two states, not four:
//   Signed out -- VentureGPS branding, "How It Works" (an anchor into the
//     homepage's own explainer section, reachable from any page), "Sign
//     in", and "Get Started" (-> /analyze, which already requires sign-in
//     via its own auth.protect() -- a signed-out click lands on /sign-in
//     first, same as every other authenticated route in this app).
//   Signed in -- Analyze, My Analyses, Saved, plus PersonalMenu (account
//     controls). Build (Idea Lab), My Startups (Founder Workspace),
//     Learn (Playbooks), and Investor intelligence are NOT competing
//     primary destinations anymore -- per this phase's own explicit
//     instruction ("remove competing navigation from the primary release
//     journey" while "keep existing founder, investor, market and
//     experimental routes intact") they are demoted, not deleted: same
//     routes, same auth, reachable from PersonalMenu's account menu
//     instead (see that file's own comment for the full record of this
//     exact promote/demote history -- this is not the first time these
//     destinations have moved between "primary nav" and "account menu").
// Markets/Search are reachable from the homepage's own content and
// PersonalMenu, not the primary signed-out row -- Phase 4's own
// instruction not to feature Markets/Explore/V2 in the primary release
// journey applies to navigation just as much as homepage copy.
import { Show } from "@clerk/nextjs";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import PersonalMenu from "./PersonalMenu";
import ThemeToggle from "@/components/ui/ThemeToggle";

type NavLink = {
  label: string;
  href: string;
};

// Signed-out primary row. Deliberately short -- four things, exactly as
// specified: branding (rendered separately, below) + these three.
// Portfolio Release Task 7, Phase 3: points at the full /how-it-works
// page (the real production pipeline, stage by stage) rather than the
// homepage's own short inline section -- a primary nav destination
// should lead somewhere real to land on from any page, not just scroll
// an anchor that only exists on "/". The homepage's own section still
// exists and still links onward to this same page for anyone who lands
// there first.
const SIGNED_OUT_NAVIGATION: NavLink[] = [{ label: "How It Works", href: "/how-it-works" }];

// Signed-in primary row -- the one array TopNav.tsx's old PRIMARY_NAVIGATION
// used to be, now here so the desktop nav and the mobile disclosure panel
// share the exact same source (see this file's own header comment).
export const PRIMARY_NAVIGATION: NavLink[] = [
  { label: "Analyze", href: "/analyze" },
  { label: "My Analyses", href: "/my-analyses" },
  { label: "Saved", href: "/saved" },
];

function isLinkActive(pathname: string, href: string): boolean {
  const [path] = href.split("#");
  if (path === "") return pathname === "/";
  return pathname === path || pathname.startsWith(`${path}/`);
}

type PublicNavProps = {
  variant: "overlay" | "header";
};

const VARIANT_CLASSES: Record<PublicNavProps["variant"], string> = {
  overlay: "border-b border-white/10 bg-black/20 backdrop-blur-md",
  header: "sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80",
};

const WORDMARK_TEXT_CLASSES: Record<PublicNavProps["variant"], string> = {
  overlay: "text-white",
  header: "text-text-primary",
};

const LINK_TEXT_CLASSES: Record<PublicNavProps["variant"], string> = {
  overlay: "text-white hover:text-white/80",
  header: "text-text-secondary hover:text-text-primary",
};

const LINK_ACTIVE_CLASSES: Record<PublicNavProps["variant"], string> = {
  overlay: "text-white",
  header: "text-text-primary",
};

const MENU_BUTTON_CLASSES: Record<PublicNavProps["variant"], string> = {
  overlay: "text-white",
  header: "text-text-secondary",
};

const MOBILE_PANEL_CLASSES: Record<PublicNavProps["variant"], string> = {
  overlay: "border-t border-white/10 bg-black/70 backdrop-blur-md",
  header: "border-t border-border bg-surface",
};

function NavLinks({
  links,
  variant,
  pathname,
  onNavigate,
  mobile = false,
}: {
  links: NavLink[];
  variant: PublicNavProps["variant"];
  pathname: string;
  onNavigate?: () => void;
  mobile?: boolean;
}) {
  return (
    <>
      {links.map((link) => {
        const active = isLinkActive(pathname, link.href);

        return (
          <Link
            key={link.href}
            href={link.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={[
              mobile ? "min-h-11 py-3 text-base font-medium" : "text-sm font-medium tracking-wide transition-colors",
              active ? LINK_ACTIVE_CLASSES[variant] : LINK_TEXT_CLASSES[variant],
            ].join(" ")}
          >
            {link.label}
          </Link>
        );
      })}
    </>
  );
}

export default function PublicNav({ variant }: PublicNavProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const pathname = usePathname();
  const closeMobileMenu = () => setMobileMenuOpen(false);

  return (
    <div className={variant === "header" ? VARIANT_CLASSES.header : undefined}>
      <div className={["relative z-10 flex items-center justify-between px-4 py-4 sm:px-8 sm:py-5", variant === "overlay" ? VARIANT_CLASSES.overlay : "h-14 py-0 sm:px-6 lg:px-10"].join(" ")}>
        <Link href="/" className="flex shrink-0 items-center gap-2" onClick={closeMobileMenu} aria-label="VentureGPS home">
          <span aria-hidden="true" className={["size-2 rounded-full", variant === "overlay" ? "bg-white" : "bg-primary"].join(" ")} />
          <span className={["text-base font-bold tracking-tight", WORDMARK_TEXT_CLASSES[variant]].join(" ")}>VentureGPS</span>
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-7 sm:flex">
          <Show when="signed-out">
            <NavLinks links={SIGNED_OUT_NAVIGATION} variant={variant} pathname={pathname} />
          </Show>
          <Show when="signed-in">
            <NavLinks links={PRIMARY_NAVIGATION} variant={variant} pathname={pathname} />
          </Show>

          {variant === "header" ? <ThemeToggle /> : null}

          <Show when="signed-out">
            <Link
              href="/sign-in"
              className={[
                "rounded-full px-4 py-2 text-sm font-semibold transition-colors",
                variant === "overlay" ? "border border-white/40 text-white hover:bg-white/10" : "border border-border text-text-primary hover:bg-surface-muted",
              ].join(" ")}
            >
              Sign in
            </Link>
            <Link
              href="/analyze"
              className="rounded-full bg-gradient-to-r from-accent to-secondary px-4 py-2 text-sm font-bold text-white shadow-sm transition-opacity hover:opacity-90"
            >
              Get Started
            </Link>
          </Show>
          <Show when="signed-in">
            <PersonalMenu />
          </Show>
        </nav>

        {/* Mobile: a compact always-visible account affordance next to the hamburger, plus the menu toggle.
            Same NavLinks/data source as desktop (see this file's own header comment on
            "avoid duplicating desktop and mobile navigation logic") -- only the disclosure panel below differs
            in presentation, never in which destinations exist. */}
        <div className="flex items-center gap-2 sm:hidden">
          {variant === "header" ? <ThemeToggle /> : null}

          <Show when="signed-out">
            <Link
              href="/sign-in"
              onClick={closeMobileMenu}
              className={[
                "rounded-full px-3 py-1.5 text-sm font-semibold transition-colors",
                variant === "overlay" ? "border border-white/40 text-white" : "border border-border text-text-primary",
              ].join(" ")}
            >
              Sign in
            </Link>
          </Show>
          <Show when="signed-in">
            <PersonalMenu />
          </Show>

          <button
            type="button"
            onClick={() => setMobileMenuOpen((open) => !open)}
            aria-expanded={mobileMenuOpen}
            aria-controls="public-nav-mobile-menu"
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            className={["flex min-h-11 min-w-11 items-center justify-center rounded-lg", MENU_BUTTON_CLASSES[variant]].join(" ")}
          >
            {mobileMenuOpen ? (
              <svg aria-hidden="true" viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg aria-hidden="true" viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {mobileMenuOpen ? (
        <div id="public-nav-mobile-menu" className={["relative z-10 sm:hidden", MOBILE_PANEL_CLASSES[variant]].join(" ")}>
          <nav aria-label="Primary" className="flex flex-col px-4 py-2">
            <Show when="signed-out">
              <NavLinks links={SIGNED_OUT_NAVIGATION} variant={variant} pathname={pathname} onNavigate={closeMobileMenu} mobile />
              <Link
                href="/analyze"
                onClick={closeMobileMenu}
                className="my-2 inline-flex min-h-11 items-center justify-center rounded-xl bg-gradient-to-r from-accent to-secondary px-4 text-base font-bold text-white"
              >
                Get Started
              </Link>
            </Show>
            <Show when="signed-in">
              <NavLinks links={PRIMARY_NAVIGATION} variant={variant} pathname={pathname} onNavigate={closeMobileMenu} mobile />
            </Show>
          </nav>
        </div>
      ) : null}
    </div>
  );
}
