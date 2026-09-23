import type { Metadata } from "next";
import Link from "next/link";

import { listMarkets } from "@/lib/api/v2/markets.ts";
import { absoluteUrl } from "@/lib/site.ts";

// VentureGPS Increment 17.1 -- the real /markets index, added this increment specifically so the new public
// nav's "Markets" link (components/layout/PublicNav.tsx) goes somewhere real rather than being a dead link or
// omitted outright (Jerrod's own instruction: only link to routes that actually exist). One real V2 request
// (listMarkets), no per-market Capital Signal calls here -- an index page just needs names and links; a
// market's own direction/signal is what /markets/[slug] itself is for, and fetching a signal per row here for
// however many real markets exist would be exactly the kind of unbounded request growth this increment's data
// instructions rule out.
const MARKETS_INDEX_LIMIT = 50;
const MARKETS_INDEX_REVALIDATE_SECONDS = 300;

export async function generateMetadata(): Promise<Metadata> {
  const url = absoluteUrl("/markets");
  const description = "Every market VentureGPS tracks, with verified Capital Signal for each.";

  return {
    title: { absolute: "Markets — VentureGPS" },
    description,
    alternates: { canonical: url },
    openGraph: { title: "Markets — VentureGPS", description, url, type: "website", siteName: "VentureGPS" },
    twitter: { card: "summary_large_image", title: "Markets — VentureGPS", description },
  };
}

export default async function MarketsIndexPage() {
  let markets: { id: string; slug: string; display_name: string }[] = [];
  let status: "ok" | "unavailable" = "ok";

  try {
    const result = await listMarkets(MARKETS_INDEX_LIMIT, 0, MARKETS_INDEX_REVALIDATE_SECONDS);
    markets = result.markets;
  } catch {
    status = "unavailable";
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <h1 className="text-3xl font-black tracking-tight text-text-primary sm:text-4xl">Markets</h1>
      <p className="mt-3 max-w-xl text-base leading-7 text-text-secondary">
        Verified Capital Signal for every market VentureGPS tracks -- financing activity, companies funded, and
        capital deployed, compared against each market&rsquo;s own recent history.
      </p>

      {status === "unavailable" ? (
        <p className="mt-10 text-sm leading-6 text-text-secondary">VentureGPS couldn&rsquo;t reach market data just now. Try again in a moment.</p>
      ) : markets.length === 0 ? (
        <p className="mt-10 text-sm leading-6 text-text-secondary">VentureGPS is still building market coverage. Check back soon.</p>
      ) : (
        <ul className="mt-10 grid gap-3 sm:grid-cols-2">
          {markets.map((market) => (
            <li key={market.id}>
              <Link
                href={`/markets/${market.slug}`}
                className="flex min-h-14 items-center rounded-xl border border-border bg-surface px-5 text-base font-semibold text-text-primary transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                {market.display_name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
