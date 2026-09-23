import { notFound } from "next/navigation";

import CinematicHomepage from "@/components/design/cinematicHomepage/CinematicHomepage";

// VentureGPS Increment 16.2. Same production-guard precedent as every prior /design/* route
// (app/dev/design-system/page.tsx originally, then Increments 16 and 16.1): NODE_ENV-gated 404, not just
// unlinked.
export default function CinematicHomepagePage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <CinematicHomepage />;
}
