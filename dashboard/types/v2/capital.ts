// VentureGPS V2 Capital Intelligence API response types.
//
// Hand-mirrors app/v2/api_schemas.py field-for-field (Increment 14). This is NOT auto-generated -- there is no
// OpenAPI-to-TS pipeline in this repo yet, so keeping these two files in agreement is a manual discipline (same
// as every other file in dashboard/types/ mirroring a backend Pydantic model by hand; see the main CLAUDE.md's
// "when a Pydantic model changes, update the matching TypeScript type").
//
// EXACTNESS, non-negotiable: every field the backend serializes as a decimal STRING (never a JSON number, see
// docs/v2/CAPITAL_API.md) is typed `string` here, not `number`. This is deliberate and must never be "corrected"
// to a numeric type -- large minor-unit amounts can exceed Number.MAX_SAFE_INTEGER, and a Fraction is not a
// float. Parse these strings with BigInt (see lib/api/v2/money.ts), never Number()/parseFloat().

export type MoneyOut = {
  currency_code: string;
  minor_units: string; // exact integer, decimal string
};

export type RatioOut = {
  numerator: string; // exact integer, decimal string
  denominator: string;
};

export type MarketOut = {
  id: string; // UUID
  slug: string;
  display_name: string;
};

export type MarketListOut = {
  markets: MarketOut[];
  limit: number;
  offset: number;
  total: number;
};

export type MarketDetailOut = {
  id: string;
  slug: string;
  display_name: string;
  taxonomy_versions: string[]; // every taxonomy version registered system-wide, NOT scoped to this market
};

export type CapitalConcentrationAmountOut = {
  currency_code: string;
  largest_minor_units: string;
  total_minor_units: string;
};

export type CapitalMetricsDiagnosticsOut = {
  events_considered: number;
  events_included: number;
  events_excluded_missing_date: number;
  events_excluded_outside_period: number;
  events_without_verified_amount: number;
  events_without_known_stage: number;
  // How many canonical Companies hold a PRIMARY classification into this market/taxonomy version, regardless of
  // period. Zero here (unlike zero financing_activity) means no companies are even classified into this market
  // yet -- see docs/v2/CAPITAL_API.md's "Coverage and honesty" section. Never treat this as a completeness score.
  classified_company_count: number;
};

export type PeriodOut = {
  start: string; // ISO 8601
  end: string;
};

// The canonical six-key stage vocabulary. Every response includes ALL six keys, zero-filled -- never partial.
export type StageKey = "pre_seed" | "seed" | "series_a" | "series_b" | "growth" | "unknown";

export type StageDistribution = Record<StageKey, number>;

export type CapitalMetricsBodyOut = {
  financing_activity: number;
  companies_funded: number;
  capital_deployed: MoneyOut[];
  capital_concentration: CapitalConcentrationAmountOut[];
  stage_distribution: StageDistribution;
  diagnostics: CapitalMetricsDiagnosticsOut;
};

export type CapitalMetricsMethodologyOut = {
  methodology_version: string; // "capital_metrics.v1"
  date_policy: string;
  attribution_policy: string;
  verified_amount_policy: string;
  currency_policy: string;
};

export type CapitalMetricsResponse = CapitalMetricsBodyOut & {
  market: MarketOut;
  taxonomy_version: string;
  period: PeriodOut;
  methodology: CapitalMetricsMethodologyOut;
};

// The frozen VentureGPS Capital Signal direction vocabulary (app.v2.domain.capital_signal.CapitalDirection).
// `mixed` is legal ONLY on the overall signal, never on a single component -- the backend enforces this
// structurally; this type does not re-enforce it (nothing here constructs a CapitalDirection, only reads one).
export type CapitalDirection =
  | "strong_increase"
  | "increase"
  | "stable"
  | "decrease"
  | "strong_decrease"
  | "insufficient_data"
  | "mixed";

export type ComponentMetric = "financing_activity" | "companies_funded" | "capital_deployed";

export type ComponentSignalOut = {
  metric: ComponentMetric;
  currency_code: string | null; // set iff metric === "capital_deployed"
  current_value: string; // exact integer (a count or minor units), decimal string
  historical_values: string[]; // exactly 8, oldest first, decimal strings
  historical_nonzero_windows: number;
  percentile_rank: RatioOut | null; // null iff direction === "insufficient_data"
  direction: CapitalDirection; // never "mixed" here
  votes: boolean;
};

// Deliberately a SEPARATE vocabulary from CapitalDirection: concentration moving up or down is not itself
// Capital activity increasing or decreasing. Never render this with the same up/down/flat mapping as
// CapitalDirection.
export type ConcentrationTrend = "more_concentrated" | "less_concentrated" | "stable" | "insufficient_data";

export type ConcentrationSignalOut = {
  currency_code: string;
  current_share: RatioOut | null; // null iff no verified capital this period (absent, not zero)
  historical_shares: (RatioOut | null)[]; // exactly 8, oldest first; null where that window had no verified capital
  trend: ConcentrationTrend;
};

export type CapitalWindowOut = {
  start: string; // ISO 8601
  end: string;
  metrics: CapitalMetricsBodyOut;
};

export type CapitalSignalMethodologyOut = {
  methodology_version: string; // "capital_signal.v1"
  date_policy: string;
  attribution_policy: string;
  verified_amount_policy: string;
  currency_policy: string;
  historical_window_policy: string;
  minimum_history_rule: string;
  comparison_method: string;
  concentration_voting_policy: string;
  limitations: string; // the explicit "this is not a forecast" caveat -- always render this, never trim it
};

export type CapitalSignalResponse = {
  market: MarketOut;
  taxonomy_version: string;
  as_of: string; // ISO 8601
  methodology_version: string; // "capital_signal.v1"

  current_window: CapitalWindowOut;
  historical_windows: CapitalWindowOut[]; // exactly 8, oldest first

  financing_activity: ComponentSignalOut;
  companies_funded: ComponentSignalOut;
  capital_deployed: ComponentSignalOut[]; // one entry per currency observed; can be empty
  capital_concentration: ConcentrationSignalOut[]; // contextual only; never treat as a vote

  overall: CapitalDirection;
  methodology: CapitalSignalMethodologyOut;
};
