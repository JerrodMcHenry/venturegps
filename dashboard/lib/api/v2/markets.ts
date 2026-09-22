// Typed wrappers over the VentureGPS V2 Capital Intelligence API (docs/v2/CAPITAL_API.md). Every function here
// is a thin, one-to-one call to a single V2 endpoint -- no calculation happens in this file; every number a
// caller sees came directly from the backend's own domain engines (app/v2/domain/capital_metrics.py,
// app/v2/domain/capital_signal.py). Duplicating that math here would be exactly the "second implementation" the
// backend's own docstrings warn against.

import { v2Fetch } from "./client.ts";

import type {
  CapitalMetricsResponse,
  CapitalSignalResponse,
  MarketDetailOut,
  MarketListOut,
  MarketOut,
} from "@/types/v2/capital";

export async function getMarketBySlug(slug: string, revalidateSeconds?: number): Promise<MarketOut | null> {
  const result = await v2Fetch<MarketListOut>("/markets", { slug }, revalidateSeconds);
  return result.markets[0] ?? null;
}

export async function getMarket(marketId: string, revalidateSeconds?: number): Promise<MarketDetailOut> {
  return v2Fetch<MarketDetailOut>(`/markets/${encodeURIComponent(marketId)}`, undefined, revalidateSeconds);
}

export async function listMarkets(limit = 50, offset = 0, revalidateSeconds?: number): Promise<MarketListOut> {
  return v2Fetch<MarketListOut>("/markets", { limit, offset }, revalidateSeconds);
}

export type CapitalMetricsParams = {
  marketId: string;
  taxonomyVersion: string;
  startDate: string; // ISO date, e.g. "2026-01-01" -- period start (inclusive)
  endDate: string; // period end (exclusive); must be strictly after startDate
};

export async function getCapitalMetrics(params: CapitalMetricsParams, revalidateSeconds?: number): Promise<CapitalMetricsResponse> {
  return v2Fetch<CapitalMetricsResponse>(
    `/markets/${encodeURIComponent(params.marketId)}/capital/metrics`,
    { taxonomy_version: params.taxonomyVersion, start_date: params.startDate, end_date: params.endDate },
    revalidateSeconds
  );
}

export type CapitalSignalParams = {
  marketId: string;
  taxonomyVersion: string;
  asOf: string; // ISO date -- the current 30-day window ends here (interpreted as UTC midnight)
};

export async function getCapitalSignal(params: CapitalSignalParams, revalidateSeconds?: number): Promise<CapitalSignalResponse> {
  return v2Fetch<CapitalSignalResponse>(
    `/markets/${encodeURIComponent(params.marketId)}/capital/signal`,
    { taxonomy_version: params.taxonomyVersion, as_of: params.asOf },
    revalidateSeconds
  );
}
