// Which VentureGPS taxonomy version the public frontend queries Capital Metrics/Signal under.
//
// The smallest explicit configuration necessary (per Increment 15's own instruction): the V2 API has no
// "current/default taxonomy version" concept of its own yet -- GET /markets/{id} lists every version a Market
// COULD be classified under (see docs/v2/CAPITAL_API.md), never which one is "active." Introducing that concept
// properly (e.g. a backend-flagged default) is a backend decision out of this increment's frontend scope, so
// this file is the ONE place the frontend's choice of version lives, read from one explicit env var with a
// documented fallback -- never hardcoded inline at each call site, and never silently guessed per-request.
export const DEFAULT_TAXONOMY_VERSION = "venturegps_taxonomy.v1";

export function getConfiguredTaxonomyVersion(): string {
  const configured = process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION;
  return configured && configured.trim().length > 0 ? configured.trim() : DEFAULT_TAXONOMY_VERSION;
}
