"use client";

// VentureGPS Increment 17.1 -- the first REAL, functional public navigation for the VentureGPS brand surfaces.
// Replaces two things that were each, in their own way, not this:
// - PublicHeader.tsx (still used unmodified by the dev-only /design/* prototypes): branding only, explicitly
//   documented as deliberately not a nav menu, because no second real public route existed yet.
// - CinematicHero.tsx's own baked-in nav bar (still used unmodified by the /design/cinematic-homepage
//   prototype): plain, non-interactive <span> labels under aria-label="...(concept)" -- a mockup, not links.
//
// Only links to routes that actually exist in production. Revisit this file's NAV_LINKS the moment a route is
// removed or renamed.
//
// Milestone 1, Task 1 -- Unify Navigation: "Search" (/search) and "Analyze" (/analyze) added, and sign-in/
// account access added alongside NAV_LINKS. Increment 17.1's original comment here said linking to /search
// "would be exactly the 'dead navigation link' this increment forbids" -- that was true only because no
// VentureGPS-branded route existed yet to distinguish it from; the task instruction now explicitly requires
// visitors be able to reach existing search and Analyze from here, while (its own explicit requirement)
// NEVER implying legacy SIE search/assessments and V2's verified Markets records are the same kind of data.
// Deliberately NOT solved by restyling this into two visually separate groups (a homepage-chrome redesign this
// task's own boundaries forbid) -- solved the smaller way instead: the labels themselves ("Markets" vs.
// "Search"/"Analyze") are never implied to be the same product, and neither page's own content is touched by
// this file at all, so each page's own honest framing (V2 verified facts vs. an AI-assisted assessment) is
// exactly as before. /analyze itself already requires sign-in (its own existing auth.protect()) -- linking to
// it directly from here is safe by construction, not a new auth surface: a signed-out click lands on sign-in
// first, same as always.
import { Show } from "@clerk/nextjs";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import PersonalMenu from "./PersonalMenu";

type NavLink = {
  label: string;
  href: string;
};

const NAV_LINKS: NavLink[] = [
  { label: "Markets", href: "/markets" },
  { label: "Search", href: "/search" },
  { label: "Analyze", href: "/analyze" },
];

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

const MENU_BUTTON_CLASSES: Record<PublicNavProps["variant"], string> = {
  overlay: "text-white",
  header: "text-text-secondary",
};

const MOBILE_PANEL_CLASSES: Record<PublicNavProps["variant"], string> = {
  overlay: "border-t border-white/10 bg-black/70 backdrop-blur-md",
  header: "border-t border-border bg-surface",
};

export default function PublicNav({ variant }: PublicNavProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const pathname = usePathname();

  return (
    <div className={variant === "header" ? VARIANT_CLASSES.header : undefined}>
      <div className={["relative z-10 flex items-center justify-between px-4 py-4 sm:px-8 sm:py-5", variant === "overlay" ? VARIANT_CLASSES.overlay : "h-14 py-0 sm:px-6 lg:px-10"].join(" ")}>
        <Link href="/" className="flex items-center gap-2" onClick={() => setMobileMenuOpen(false)}>
          <span aria-hidden="true" className={["size-2 rounded-full", variant === "overlay" ? "bg-white" : "bg-primary"].join(" ")} />
          <span className={["text-base font-bold tracking-tight", WORDMARK_TEXT_CLASSES[variant]].join(" ")}>VentureGPS</span>
        </Link>

        <nav aria-label="VentureGPS" className="hidden items-center gap-7 sm:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href || pathname.startsWith(`${link.href}/`) ? "page" : undefined}
              className={["text-sm font-medium tracking-wide transition-colors", LINK_TEXT_CLASSES[variant]].join(" ")}
            >
              {link.label}
            </Link>
          ))}

          {/* Milestone 1, Task 1: account access, same <Show>-gated pattern TopNav.tsx already uses -- a solid
              pill button works unchanged on both the dark "overlay" hero background and the light "header" bar,
              so no per-variant styling is needed here the way the plain nav links above need. Auth itself is
              completely unchanged: this is Clerk's own sign-in link / UserButton, the exact same components
              TopNav.tsx already renders, not a second implementation. */}
          <Show when="signed-out">
            <Link
              href="/sign-in"
              className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
            >
              Sign in
            </Link>
          </Show>
          <Show when="signed-in">
            <PersonalMenu />
          </Show>
        </nav>

        {/* Mobile: a compact always-visible account affordance next to the hamburger (not hidden behind the
            disclosure panel -- signing in/managing your account is a one-tap action, not a secondary nav item),
            plus the menu toggle. NAV_LINKS is short enough today that a simple disclosure panel (no portal, no
            focus trap library) is proportionate. */}
        <div className="flex items-center gap-2 sm:hidden">
          <Show when="signed-out">
            <Link
              href="/sign-in"
              onClick={() => setMobileMenuOpen(false)}
              className="rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
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
          <nav aria-label="VentureGPS" className="flex flex-col px-4 py-2">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                aria-current={pathname === link.href || pathname.startsWith(`${link.href}/`) ? "page" : undefined}
                className={["min-h-11 py-3 text-base font-medium", LINK_TEXT_CLASSES[variant]].join(" ")}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      ) : null}
    </div>
  );
}
