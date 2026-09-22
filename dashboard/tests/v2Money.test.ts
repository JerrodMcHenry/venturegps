// VentureGPS V2 Capital API money/ratio exactness tests.
//
// Same hand-rolled expect()/PASS-FAIL/main() convention as the rest of this directory (no jest/vitest here).
//
// Run with:
//   node tests/v2Money.test.ts

import {
  bigIntToChartNumber,
  formatAbbreviatedAmount,
  formatExactAmount,
  formatRatioAsPercent,
  minorUnitsToExactUnitString,
  parseMinorUnits,
} from "../lib/api/v2/money.ts";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function test_parse_minor_units_never_loses_precision_beyond_number_max_safe_integer(): void {
  const huge = "92233720368547758"; // near BigInt-storable max (2^63-1 minor units), well beyond Number.MAX_SAFE_INTEGER
  const parsed = parseMinorUnits(huge);
  expect(parsed === 92233720368547758n, `expected exact bigint, got ${parsed}`);
  expect(parsed > BigInt(Number.MAX_SAFE_INTEGER), "the whole point of this test: this value exceeds Number.MAX_SAFE_INTEGER");
}

function test_exact_unit_string_usd(): void {
  expect(
    minorUnitsToExactUnitString("2000000000", "USD") === "20000000.00",
    `got: ${minorUnitsToExactUnitString("2000000000", "USD")}`
  );
}

function test_exact_unit_string_jpy_has_no_decimal_places(): void {
  // JPY has zero minor-unit decimal places (see app/v2/domain/financing.py's CURRENCY_MINOR_UNIT_EXPONENTS)
  expect(minorUnitsToExactUnitString("5000", "JPY") === "5000", `got: ${minorUnitsToExactUnitString("5000", "JPY")}`);
}

function test_exact_unit_string_preserves_small_fractional_amounts(): void {
  expect(minorUnitsToExactUnitString("1", "USD") === "0.01", `got: ${minorUnitsToExactUnitString("1", "USD")}`);
}

function test_format_exact_amount_groups_and_keeps_symbol(): void {
  expect(
    formatExactAmount("2000000000", "USD") === "$20,000,000.00",
    `got: ${formatExactAmount("2000000000", "USD")}`
  );
}

function test_format_exact_amount_handles_a_bigint_range_amount_exactly(): void {
  const huge = "92233720368547758";
  const exact = formatExactAmount(huge, "USD");
  // 92233720368547758 minor units of USD = 922337203685477.58 dollars, exactly.
  expect(exact === "$922,337,203,685,477.58", `got: ${exact}`);
}

function test_format_abbreviated_amount_millions(): void {
  expect(formatAbbreviatedAmount("2000000000", "USD") === "$20.0M", `got: ${formatAbbreviatedAmount("2000000000", "USD")}`);
}

function test_format_abbreviated_amount_billions(): void {
  expect(formatAbbreviatedAmount("250000000000", "USD") === "$2.5B", `got: ${formatAbbreviatedAmount("250000000000", "USD")}`);
}

function test_format_abbreviated_amount_below_thousand(): void {
  expect(formatAbbreviatedAmount("50000", "USD") === "$500", `got: ${formatAbbreviatedAmount("50000", "USD")}`);
}

function test_format_abbreviated_amount_rounds_exactly_half_up(): void {
  // $20,050,000 -> 20.05M -> rounds to 20.1M (half rounds up), computed with exact integer arithmetic
  expect(formatAbbreviatedAmount("2005000000", "USD") === "$20.1M", `got: ${formatAbbreviatedAmount("2005000000", "USD")}`);
}

function test_format_abbreviated_amount_zero(): void {
  expect(formatAbbreviatedAmount("0", "USD") === "$0", `got: ${formatAbbreviatedAmount("0", "USD")}`);
}

function test_format_abbreviated_amount_unsupported_currency_falls_back_to_code(): void {
  const result = formatAbbreviatedAmount("2000000000", "BTC");
  expect(result.includes("BTC"), `expected the currency code to appear for an unmapped symbol, got: ${result}`);
}

function test_format_ratio_as_percent_exact(): void {
  expect(formatRatioAsPercent("3", "5") === "60.0%", `got: ${formatRatioAsPercent("3", "5")}`);
}

function test_format_ratio_as_percent_percentile_rank_eighths(): void {
  // 3/8 = 37.5% exactly
  expect(formatRatioAsPercent("3", "8") === "37.5%", `got: ${formatRatioAsPercent("3", "8")}`);
}

function test_format_ratio_as_percent_zero_denominator_is_safe(): void {
  expect(formatRatioAsPercent("1", "0") === "—", `got: ${formatRatioAsPercent("1", "0")}`);
}

function test_bigint_to_chart_number_is_the_only_lossy_conversion_and_is_explicit(): void {
  expect(bigIntToChartNumber(2000000000n) === 2000000000, "a moderate value should convert exactly for chart purposes");
}

function main(): void {
  const tests = [
    test_parse_minor_units_never_loses_precision_beyond_number_max_safe_integer,
    test_exact_unit_string_usd,
    test_exact_unit_string_jpy_has_no_decimal_places,
    test_exact_unit_string_preserves_small_fractional_amounts,
    test_format_exact_amount_groups_and_keeps_symbol,
    test_format_exact_amount_handles_a_bigint_range_amount_exactly,
    test_format_abbreviated_amount_millions,
    test_format_abbreviated_amount_billions,
    test_format_abbreviated_amount_below_thousand,
    test_format_abbreviated_amount_rounds_exactly_half_up,
    test_format_abbreviated_amount_zero,
    test_format_abbreviated_amount_unsupported_currency_falls_back_to_code,
    test_format_ratio_as_percent_exact,
    test_format_ratio_as_percent_percentile_rank_eighths,
    test_format_ratio_as_percent_zero_denominator_is_safe,
    test_bigint_to_chart_number_is_the_only_lossy_conversion_and_is_explicit,
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
