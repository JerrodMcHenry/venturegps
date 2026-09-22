import { cache } from "react";
import type { Metadata } from "next";

import MarketHero from "@/components/markets/MarketHero.tsx";
import CapitalChart from "@/components/markets/CapitalChart.tsx";
import CapitalSignalExplore from "@/components/markets/CapitalSignalExplore.tsx";
import MarketDiscoveryNav from "@/components/markets/MarketDiscoveryNav.tsx";
import MarketNotAvailable from "@/components/markets/MarketNotAvailable.tsx";

import { getCapitalSignal, getMarketBySlug } from "@/lib/api/v2/markets.ts";
import { getConfiguredTaxonomyVersion } from "@/lib/api/v2/taxonomyVersion.ts";
import { absoluteUrl } from "@/lib/site.ts";
import { DIRECTION_LABEL } from "@/lib/api/v2/signalLabels.ts";
import { formatExactAmount } from "@/lib/api/v2/money.ts";

import type { CapitalSignalResponse, MarketOut } from "@/types/v2/capital";

type Props = {
  params: Promise<{ slug: string }>;
};

// A market's own record (slug/name) barely ever changes; its Capital Signal is safe to reuse across visitors for
// a few minutes without misleadingly claiming real-time freshness -- the page always shows the response's own
// `as_of` date rather than implying "live."
const MARKET_REVALIDATE_SECONDS = 300;

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

type MarketPageData =
  | { status: "unknown" }
  | { status: "unavailable"; market: MarketOut }
  | { status: "ok"; market: MarketOut; signal: CapitalSignalResponse };

// Wrapped in React's `cache()` so generateMetadata and the page component -- both of which need the same
// market+signal data -- trigger exactly one network round trip per request, not two (see Next's own
// "memoizing data requests" guidance in node_modules/next/dist/docs).
const loadMarketPageData = cache(async (slug: string): Promise<MarketPageData> => {
  const market = await getMarketBySlug(slug, MARKET_REVALIDATE_SECONDS);
  if (!market) return { status: "unknown" };

  try {
    const signal = await getCapitalSignal(
      { marketId: market.id, taxonomyVersion: getConfiguredTaxonomyVersion(), asOf: todayIsoDate() },
      MARKET_REVALIDATE_SECONDS
    );
    return { status: "ok", market, signal };
  } catch {
    // The market itself resolved fine -- any failure fetching its Capital Signal (taxonomy misconfiguration,
    // database unavailable, a transient 5xx) is a service problem, not "this market doesn't exist."
    return { status: "unavailable", market };
  }
});

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const data = await loadMarketPageData(slug);

  if (data.status === "unknown") {
    return { title: { absolute: "Market not found — VentureGPS" } };
  }

  const url = absoluteUrl(`/markets/${slug}`);

  if (data.status === "unavailable") {
    return {
      // `title.absolute` bypasses the root layout's "%s | Startup Intelligence Engine" template (Increment
      // 15.1, Part 1) -- this is a VentureGPS-branded public page, not a Startup Intelligence Engine one; the
      // legacy template must never leak into a VentureGPS tab title, OG title, or search-result title.
      title: { absolute: `${data.market.display_name} — VentureGPS` },
      alternates: { canonical: url },
    };
  }

  const { market, signal } = data;
  const description = `${DIRECTION_LABEL[signal.overall]}: ${market.display_name} on VentureGPS. Verified financing activity, companies funded, and capital deployed, compared against this market's own recent history.`;

  return {
    title: { absolute: `${market.display_name} — VentureGPS` },
    description,
    alternates: { canonical: url },
    openGraph: {
      title: `${market.display_name} — VentureGPS`,
      description,
      url,
      type: "website",
      siteName: "VentureGPS",
    },
    twitter: {
      card: "summary_large_image",
      title: `${market.display_name} — VentureGPS`,
      description,
    },
  };
}

export default async function MarketPage({ params }: Props) {
  const { slug } = await params;
  const data = await loadMarketPageData(slug);

  if (data.status === "unknown") {
    return <MarketNotAvailable reason="unknown" />;
  }

  if (data.status === "unavailable") {
    return <MarketNotAvailable reason="unavailable" />;
  }

  const { signal } = data;
  const shareUrl = absoluteUrl(`/markets/${slug}`);
  const verifiedCapitalSummary = signal.current_window.metrics.capital_deployed
    .map((money) => formatExactAmount(money.minor_units, money.currency_code))
    .join(", ");

  return (
    <div>
      <MarketHero signal={signal} shareUrl={shareUrl} />

      {/* A visually-hidden summary of the current period's headline numbers -- gives a screen reader user (or a
          search crawler) the substance of the chart section immediately, without depending on interacting with
          the chart's buttons first. */}
      <p className="sr-only">
        Current 30-day period: {signal.current_window.metrics.financing_activity} financings,{" "}
        {signal.current_window.metrics.companies_funded} companies funded
        {verifiedCapitalSummary ? `, ${verifiedCapitalSummary} verified capital` : ""}.
      </p>

      <CapitalChart signal={signal} />
      <CapitalSignalExplore signal={signal} />
      <MarketDiscoveryNav currentSlug={slug} />
    </div>
  );
}
