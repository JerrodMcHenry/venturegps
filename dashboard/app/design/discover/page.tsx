import { notFound } from "next/navigation";

import DiscoverPrototype from "@/components/design/discover/DiscoverPrototype";

// VentureGPS Increment 16 -- Consumer Experience Blueprint prototype. Follows the exact precedent
// app/dev/design-system/page.tsx already established for a dev-only, non-production route: gated out of
// production builds entirely via a NODE_ENV check, not just hidden from navigation. `next build`/`next start`
// run with NODE_ENV=production, `next dev` with NODE_ENV=development, so this route 404s in any real deployment
// regardless of whether a link to it ever existed anywhere -- satisfying "do not deploy the prototype publicly"
// structurally rather than by convention alone.
export default function DesignDiscoverPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <DiscoverPrototype />;
}
