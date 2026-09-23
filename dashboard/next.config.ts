import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Increment 16.3.2 -- root cause of the confirmed "clicks do nothing" interaction bug: Next 16's dev server
  // treats "127.0.0.1" and "localhost" as DIFFERENT origins (per the Same-Origin Policy, they're different
  // strings even though they resolve to the same machine) and, as a dev-only safety default, BLOCKS
  // cross-origin access to its own dev resources -- including `/_next/hmr`, the Turbopack dev/HMR client
  // endpoint. The dev server's own terminal output states this plainly: "Blocked cross-origin request to
  // Next.js dev resource /_next/hmr from '127.0.0.1'." Whenever the dev server is reached via 127.0.0.1 (as
  // this whole investigation, and very plausibly Jerrod's own manual test, did), that block appears to cascade
  // into React never completing hydration at all -- confirmed directly with a minimal HydrationProbe component
  // showing "NOT HYDRATED" indefinitely on every route tested, not just Section B -- which is exactly what
  // presents as "every onClick handler in the app does nothing" while the server-rendered HTML still looks
  // correct. `allowedDevOrigins` is the fix Next's own warning names; dev-only (no effect on production
  // builds/behavior), and does not touch anything about the approved visual design.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
