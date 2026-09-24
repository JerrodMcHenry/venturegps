import type { Metadata } from "next";

import MarketHero from "@/components/markets/MarketHero.tsx";
import CapitalChart from "@/components/markets/CapitalChart.tsx";
import CapitalSignalExplore from "@/components/markets/CapitalSignalExplore.tsx";
import MarketDiscoveryNav from "@/components/markets/MarketDiscoveryNav.tsx";
import MarketNotAvailable from "@/components/markets/MarketNotAvailable.tsx";

import { loadMarketPageData } from "./marketPageData.ts";
import { absoluteUrl } from "@/lib/site.ts";
import { DIRECTION_LABEL } from "@/lib/api/v2/signalLabels.ts";
import { formatExactAmount } from "@/lib/api/v2/money.ts";

type Props = {
  params: Promise<{ slug: string }>;
};

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
      //
      // data.market is null when the market LOOKUP itself failed (we never learned its real display name) and
      // non-null when only its Capital Signal failed (the market resolved fine) -- fall back to a generic title
      // only in the first case, same as the existing "unknown" branch above already does.
      title: { absolute: data.market ? `${data.market.display_name} — VentureGPS` : "VentureGPS" },
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
