// VentureGPS Increment 15, Part 6 -- canonical public URLs and OG metadata need an absolute site origin to build
// share links and to give next/og's ImageResponse an absolute image URL. No such config existed anywhere in the
// app before this (every existing page is relative-link-only, reached through Clerk-gated navigation rather than
// shared externally) -- this is the "smallest explicit config" the increment instructions ask for when no
// selection mechanism exists yet, following the same one-env-var pattern as
// lib/api/v2/taxonomyVersion.ts's NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION. Document any real value in
// dashboard/.env.local when deploying publicly; defaults to localhost for local development.
const DEFAULT_SITE_URL = "http://localhost:3000";

export function getSiteUrl(): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL;
  if (!configured || configured.trim() === "") return DEFAULT_SITE_URL;
  return configured.replace(/\/+$/, ""); // strip a trailing slash so callers can safely do `${getSiteUrl()}/path`
}

export function absoluteUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getSiteUrl()}${normalizedPath}`;
}
