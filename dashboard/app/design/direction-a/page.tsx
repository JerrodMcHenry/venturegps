import { notFound } from "next/navigation";

import DirectionA from "@/components/design/directionA/DirectionA";

// VentureGPS Increment 16.1. Same production-guard precedent as app/dev/design-system/page.tsx and
// app/design/discover/page.tsx (Increment 16): NODE_ENV-gated 404, not just unlinked.
export default function DirectionAPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <DirectionA />;
}
