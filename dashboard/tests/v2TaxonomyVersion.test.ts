// VentureGPS V2 taxonomy-version configuration tests.
//
// Run with:
//   node tests/v2TaxonomyVersion.test.ts

import { DEFAULT_TAXONOMY_VERSION, getConfiguredTaxonomyVersion } from "../lib/api/v2/taxonomyVersion.ts";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function test_default_taxonomy_version_matches_the_documented_fallback(): void {
  expect(DEFAULT_TAXONOMY_VERSION === "venturegps_taxonomy.v1", `got: ${DEFAULT_TAXONOMY_VERSION}`);
}

function test_falls_back_to_the_default_when_unset(): void {
  const original = process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION;
  delete process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION;
  try {
    expect(getConfiguredTaxonomyVersion() === DEFAULT_TAXONOMY_VERSION, "expected the documented default");
  } finally {
    if (original !== undefined) process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION = original;
  }
}

function test_falls_back_to_the_default_when_blank(): void {
  const original = process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION;
  process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION = "   ";
  try {
    expect(getConfiguredTaxonomyVersion() === DEFAULT_TAXONOMY_VERSION, "a blank/whitespace value must not be treated as configured");
  } finally {
    if (original !== undefined) {
      process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION = original;
    } else {
      delete process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION;
    }
  }
}

function test_uses_an_explicitly_configured_value(): void {
  const original = process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION;
  process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION = "venturegps_taxonomy.v2";
  try {
    expect(getConfiguredTaxonomyVersion() === "venturegps_taxonomy.v2", `got: ${getConfiguredTaxonomyVersion()}`);
  } finally {
    if (original !== undefined) {
      process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION = original;
    } else {
      delete process.env.NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION;
    }
  }
}

function main(): void {
  const tests = [
    test_default_taxonomy_version_matches_the_documented_fallback,
    test_falls_back_to_the_default_when_unset,
    test_falls_back_to_the_default_when_blank,
    test_uses_an_explicitly_configured_value,
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
