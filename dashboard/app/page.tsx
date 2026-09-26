import type { Metadata } from "next";

import VentureGpsHero from "@/components/home/ventureGps/VentureGpsHero.tsx";
import HowItWorksSection from "@/components/home/ventureGps/HowItWorksSection.tsx";

import { absoluteUrl } from "@/lib/site.ts";

// VentureGPS Increment 17.1 -- the public homepage, promoted from the approved /design/cinematic-homepage
// prototype.
//
// Task 5 -- Unified Visual Design and Homepage Simplification: this page no longer imports
// MarketDiscoverySection or loadHomepageMarkets -- this task's own explicit instruction to remove the
// homepage's featured-market widgets and Discover/Explore-the-Markets sections, so the homepage stays a
// focused, two-section page (hero + How It Works) rather than growing into a second Markets landing page.
// Nothing about /markets itself, homepageData.ts, or MarketDiscoverySection.tsx was deleted or had its own
// behavior changed -- both remain exactly as they were, just no longer imported by "/"; the real market
// route and its backend data are completely unaffected. VentureGpsHero no longer takes a `featured` prop for
// the same reason (see that component's own comment).
//
// Replaces the Phase 10.5 "Consumer Home V2" founder-funnel homepage (Hero/EntryPaths/IdeaJourney/
// ScenarioExamples/CompetitionTeaser/TrustSection, all in components/home/) at this same route. Not deleted --
// those components are untouched and still exist for reuse elsewhere -- but no longer imported here, since this
// increment establishes the public VentureGPS brand experience as what a visitor lands on at "/". Every route
// that funnel pointed into (/idea-lab/new, /analyze, sign-in, the authenticated app) is completely unaffected;
// only what "/" itself renders has changed.
export function generateMetadata(): Metadata {
  const url = absoluteUrl("/");
  // Portfolio Release Task 4 -- Phase 4: aligned with the current
  // portfolio-release product (evidence-backed startup analysis), not
  // the earlier Markets-first framing -- see VentureGpsHero.tsx's own
  // comment for the on-page headline/CTA change this description mirrors.
  const description = "Evidence-backed startup analysis. Submit a startup and get a defensible Startup Intelligence Score.";

  return {
    // Bypasses the root layout's "%s | Startup Intelligence Engine" template (same reasoning as
    // /markets/[slug]'s own generateMetadata) -- this is the VentureGPS-branded public homepage now, not the
    // legacy Startup Intelligence Engine product.
    title: { absolute: "VentureGPS — Evidence-Backed Startup Analysis" },
    description,
    alternates: { canonical: url },
    openGraph: {
      title: "VentureGPS — Evidence-Backed Startup Analysis",
      description,
      url,
      type: "website",
      siteName: "VentureGPS",
    },
    twitter: {
      card: "summary_large_image",
      title: "VentureGPS — Evidence-Backed Startup Analysis",
      description,
    },
  };
}

export default function HomePage() {
  return (
    <div>
      <VentureGpsHero />
      <HowItWorksSection />
    </div>
  );
}
