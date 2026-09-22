// VentureGPS V2 Capital chart data-shaping tests.
//
// Run with:
//   node tests/v2ChartData.test.ts

import {
  availableCapitalDeployedCurrencies,
  buildCapitalDeployedSeries,
  buildCountSeries,
  seriesMax,
} from "../lib/api/v2/chartData.ts";
import type { CapitalSignalResponse, ComponentSignalOut } from "../types/v2/capital.ts";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function window(start: string, end: string) {
  return { start, end, metrics: FAKE_METRICS_BODY };
}

const FAKE_METRICS_BODY = {
  financing_activity: 0,
  companies_funded: 0,
  capital_deployed: [],
  capital_concentration: [],
  stage_distribution: { pre_seed: 0, seed: 0, series_a: 0, series_b: 0, growth: 0, unknown: 0 },
  diagnostics: {
    events_considered: 0,
    events_included: 0,
    events_excluded_missing_date: 0,
    events_excluded_outside_period: 0,
    events_without_verified_amount: 0,
    events_without_known_stage: 0,
    classified_company_count: 0,
  },
};

function component(overrides: Partial<ComponentSignalOut>): ComponentSignalOut {
  return {
    metric: "financing_activity",
    currency_code: null,
    current_value: "3",
    historical_values: ["2", "2", "1", "0", "3", "1", "2", "2"],
    historical_nonzero_windows: 7,
    percentile_rank: { numerator: "3", denominator: "8" },
    direction: "stable",
    votes: true,
    ...overrides,
  };
}

const HISTORICAL_WINDOWS = Array.from({ length: 8 }, (_, i) =>
  window(`2025-${String(i + 1).padStart(2, "0")}-01T00:00:00Z`, `2025-${String(i + 2).padStart(2, "0")}-01T00:00:00Z`)
);

function fakeSignal(overrides: Partial<CapitalSignalResponse>): CapitalSignalResponse {
  return {
    market: { id: "m1", slug: "robotics", display_name: "Robotics" },
    taxonomy_version: "venturegps_taxonomy.v1",
    as_of: "2026-09-21T00:00:00Z",
    methodology_version: "capital_signal.v1",
    current_window: window("2026-08-22T00:00:00Z", "2026-09-21T00:00:00Z"),
    historical_windows: HISTORICAL_WINDOWS,
    financing_activity: component({ metric: "financing_activity" }),
    companies_funded: component({ metric: "companies_funded", current_value: "1", historical_values: ["1", "1", "1", "1", "1", "1", "1", "1"] }),
    capital_deployed: [],
    capital_concentration: [],
    overall: "stable",
    methodology: {
      methodology_version: "capital_signal.v1",
      date_policy: "",
      attribution_policy: "",
      verified_amount_policy: "",
      currency_policy: "",
      historical_window_policy: "",
      minimum_history_rule: "",
      comparison_method: "",
      concentration_voting_policy: "",
      limitations: "",
    },
    ...overrides,
  };
}

function test_count_series_has_exactly_nine_points_historical_then_current(): void {
  const signal = fakeSignal({});
  const series = buildCountSeries(signal, "financing_activity");
  expect(series.points.length === 9, `expected 9 points, got ${series.points.length}`);
  expect(series.points[8].isCurrent === true, "the last point must be the current window");
  expect(series.points.slice(0, 8).every((p) => !p.isCurrent), "no historical point may be marked current");
}

function test_count_series_preserves_exact_values_alongside_chart_numbers(): void {
  const signal = fakeSignal({});
  const series = buildCountSeries(signal, "financing_activity");
  expect(series.points[8].exactValue === "3", `expected exact current value "3", got ${series.points[8].exactValue}`);
  expect(series.points[8].chartValue === 3, `expected chart value 3, got ${series.points[8].chartValue}`);
}

function test_count_series_never_reorders_or_interpolates_windows(): void {
  const signal = fakeSignal({});
  const series = buildCountSeries(signal, "financing_activity");
  const exactValues = series.points.map((p) => p.exactValue);
  expect(
    exactValues.join(",") === "2,2,1,0,3,1,2,2,3",
    `expected the exact backend order preserved with no interpolation, got: ${exactValues.join(",")}`
  );
}

function test_count_series_reflects_insufficient_data_direction(): void {
  const signal = fakeSignal({
    financing_activity: component({ direction: "insufficient_data", percentile_rank: null, historical_nonzero_windows: 1 }),
  });
  const series = buildCountSeries(signal, "financing_activity");
  expect(series.sufficientHistory === false, "insufficient_data direction must mark sufficientHistory false");
}

function test_capital_deployed_series_is_per_currency_and_never_combined(): void {
  const signal = fakeSignal({
    capital_deployed: [
      component({ metric: "capital_deployed", currency_code: "USD", current_value: "2000000000", historical_values: Array(8).fill("1000000000") }),
      component({ metric: "capital_deployed", currency_code: "EUR", current_value: "800000000", historical_values: Array(8).fill("400000000") }),
    ],
  });
  const usd = buildCapitalDeployedSeries(signal, "USD");
  const eur = buildCapitalDeployedSeries(signal, "EUR");
  expect(usd !== null && usd.points[8].exactValue === "2000000000", "USD series must carry only USD values");
  expect(eur !== null && eur.points[8].exactValue === "800000000", "EUR series must carry only EUR values, never combined with USD");
  expect(availableCapitalDeployedCurrencies(signal).sort().join(",") === "EUR,USD", "expected both currencies listed");
}

function test_capital_deployed_series_for_an_absent_currency_is_null(): void {
  const signal = fakeSignal({ capital_deployed: [component({ metric: "capital_deployed", currency_code: "USD" })] });
  expect(buildCapitalDeployedSeries(signal, "GBP") === null, "a currency the signal never observed must return null, not a fabricated empty series");
}

function test_series_max_is_never_zero_even_for_an_all_zero_series(): void {
  const signal = fakeSignal({
    financing_activity: component({ current_value: "0", historical_values: Array(8).fill("0"), historical_nonzero_windows: 0, direction: "insufficient_data", percentile_rank: null }),
  });
  const series = buildCountSeries(signal, "financing_activity");
  expect(seriesMax(series) === 1, `expected a safe non-zero denominator of 1, got ${seriesMax(series)}`);
}

function main(): void {
  const tests = [
    test_count_series_has_exactly_nine_points_historical_then_current,
    test_count_series_preserves_exact_values_alongside_chart_numbers,
    test_count_series_never_reorders_or_interpolates_windows,
    test_count_series_reflects_insufficient_data_direction,
    test_capital_deployed_series_is_per_currency_and_never_combined,
    test_capital_deployed_series_for_an_absent_currency_is_null,
    test_series_max_is_never_zero_even_for_an_all_zero_series,
  ];

  let failures = 0;

  for (const test of tests) {
    try {
      test();
      console.log(`PASS ${test.name}`);
    } catch (error) {
      failures += 1;
      console.error(`FAIL ${test.name}: ${(error as Error).message}`);
    }
  }

  if (failures > 0) {
    console.error(`${failures} test(s) failed`);
    process.exit(1);
  }

  console.log(`All ${tests.length} tests passed`);
}

main();
