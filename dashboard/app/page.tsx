import type { Metadata } from "next";

import VentureGpsHero from "@/components/home/ventureGps/VentureGpsHero.tsx";
import HowItWorksSection from "@/components/home/ventureGps/HowItWorksSection.tsx";
import MarketDiscoverySection from "@/components/home/ventureGps/MarketDiscoverySection.tsx";

import { loadHomepageMarkets } from "@/components/home/ventureGps/homepageData.ts";
import { absoluteUrl } from "@/lib/site.ts";

// VentureGPS Increment 17.1 -- the public homepage, promoted from the approved /design/cinematic-homepage
// prototype (VentureGpsHero.tsx / MarketDiscoverySection.tsx's own header comments have the full detail on what
// changed and why: real V2 market data instead of SAMPLE_MARKET_SIGNALS, and a rights-clear placeholder standing
// in for the approved design's real photography -- see this increment's report for that blocker).
//
// Replaces the Phase 10.5 "Consumer Home V2" founder-funnel homepage (Hero/EntryPaths/IdeaJourney/
// ScenarioExamples/CompetitionTeaser/TrustSection, all in components/home/) at this same route. Not deleted --
// those components are untouched and still exist for reuse elsewhere -- but no longer imported here, since this
// increment establishes the public VentureGPS brand experience as what a visitor lands on at "/". Every route
// that funnel pointed into (/idea-lab/new, /analyze, sign-in, the authenticated app) is completely unaffected;
// only what "/" itself renders has changed.
//
// A Server Component: loadHomepageMarkets does the one real data fetch (bounded, cached via Next's Data Cache
// through v2Fetch's own revalidate option -- see homepageData.ts) that both this page and generateMetadata
// below need; React's cache() wrapper on that function means it only actually runs once per request either way.
export async function generateMetadata(): Promise<Metadata> {
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

export default async function HomePage() {
  const homepageMarkets = await loadHomepageMarkets();
  const featured = homepageMarkets.status === "ok" ? (homepageMarkets.markets[0] ?? null) : null;

  return (
    <div>
      <VentureGpsHero featured={featured} />
      <HowItWorksSection />
      <MarketDiscoverySection result={homepageMarkets} />
    </div>
  );
}
