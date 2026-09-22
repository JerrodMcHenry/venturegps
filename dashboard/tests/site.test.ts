// Site URL config tests (lib/site.ts).
//
// Run with:
//   node tests/site.test.ts

import { absoluteUrl, getSiteUrl } from "../lib/site.ts";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function test_falls_back_to_localhost_when_unset(): void {
  delete process.env.NEXT_PUBLIC_SITE_URL;
  expect(getSiteUrl() === "http://localhost:3000", `expected the localhost default, got ${getSiteUrl()}`);
}

function test_uses_an_explicitly_configured_value(): void {
  process.env.NEXT_PUBLIC_SITE_URL = "https://venturegps.example";
  expect(getSiteUrl() === "https://venturegps.example", `expected the configured value, got ${getSiteUrl()}`);
  delete process.env.NEXT_PUBLIC_SITE_URL;
}

function test_strips_a_trailing_slash(): void {
  process.env.NEXT_PUBLIC_SITE_URL = "https://venturegps.example/";
  expect(getSiteUrl() === "https://venturegps.example", `expected the trailing slash stripped, got ${getSiteUrl()}`);
  delete process.env.NEXT_PUBLIC_SITE_URL;
}

function test_absolute_url_joins_the_site_origin_and_path(): void {
  process.env.NEXT_PUBLIC_SITE_URL = "https://venturegps.example";
  expect(
    absoluteUrl("/markets/robotics") === "https://venturegps.example/markets/robotics",
    `expected a joined absolute URL, got ${absoluteUrl("/markets/robotics")}`
  );
  delete process.env.NEXT_PUBLIC_SITE_URL;
}

function test_absolute_url_tolerates_a_path_missing_its_leading_slash(): void {
  process.env.NEXT_PUBLIC_SITE_URL = "https://venturegps.example";
  expect(
    absoluteUrl("markets/robotics") === "https://venturegps.example/markets/robotics",
    `expected the missing leading slash to be added, got ${absoluteUrl("markets/robotics")}`
  );
  delete process.env.NEXT_PUBLIC_SITE_URL;
}

function main(): void {
  const tests = [
    test_falls_back_to_localhost_when_unset,
    test_uses_an_explicitly_configured_value,
    test_strips_a_trailing_slash,
    test_absolute_url_joins_the_site_origin_and_path,
    test_absolute_url_tolerates_a_path_missing_its_leading_slash,
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
