"use client";

// VentureGPS Increment 17.1 -- the first REAL, functional public navigation for the VentureGPS brand surfaces.
// Replaces two things that were each, in their own way, not this:
// - PublicHeader.tsx (still used unmodified by the dev-only /design/* prototypes): branding only, explicitly
//   documented as deliberately not a nav menu, because no second real public route existed yet.
// - CinematicHero.tsx's own baked-in nav bar (still used unmodified by the /design/cinematic-homepage
//   prototype): plain, non-interactive <span> labels under aria-label="...(concept)" -- a mockup, not links.
//
// Only links to routes that actually exist in production (Increment 17.1's own explicit instruction): the
// wordmark goes to "/", "Markets" goes to the real /markets index this same increment adds. Discover/Companies/
// Stories are deliberately NOT rendered as links -- none of those are real production pages yet, and inventing
// them (or linking them to an unrelated legacy surface like /search, which carries the legacy Startup
// Intelligence Engine brand, not VentureGPS) would be exactly the "dead navigation link" this increment forbids.
// Revisit this file's NAV_ITEMS the moment a second real VentureGPS content route exists.
//
// One component, two visual variants, so the exact same real links/mobile-menu behavior serves both places this
// increment needs it:
// - "overlay": transparent/glass, meant to sit inside VentureGpsHero's own full-bleed composition (preserves the
//   approved prototype's look: the nav bar as part of the hero image, not a separate stacked header above it).
// - "header": a solid sticky bar, used standalone on /markets and /markets/[slug] (replacing PublicHeader there).
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

type NavLink = {
  label: string;
  href: string;
};

const NAV_LINKS: NavLink[] = [{ label: "Markets", href: "/markets" }];

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
        </nav>

        {/* Mobile menu toggle -- only rendered content sm and up hides; NAV_LINKS is short enough today that a
            simple disclosure panel (no portal, no focus trap library) is proportionate. */}
        <button
          type="button"
          onClick={() => setMobileMenuOpen((open) => !open)}
          aria-expanded={mobileMenuOpen}
          aria-controls="public-nav-mobile-menu"
          aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
          className={["flex min-h-11 min-w-11 items-center justify-center rounded-lg sm:hidden", MENU_BUTTON_CLASSES[variant]].join(" ")}
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
