// VentureGPS V2 Capital Signal label/tone mapping tests.
//
// Run with:
//   node tests/v2SignalLabels.test.ts

import {
  CONCENTRATION_EXPLANATION,
  CONCENTRATION_LABEL,
  DIRECTION_EXPLANATION,
  DIRECTION_LABEL,
  DIRECTION_SYMBOL,
  DIRECTION_TONE,
  METRIC_EXPLANATION,
  METRIC_LABEL,
} from "../lib/api/v2/signalLabels.ts";
import type { CapitalDirection, ConcentrationTrend } from "../types/v2/capital.ts";

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

const ALL_DIRECTIONS: CapitalDirection[] = [
  "strong_increase",
  "increase",
  "stable",
  "decrease",
  "strong_decrease",
  "insufficient_data",
  "mixed",
];

const ALL_CONCENTRATION_TRENDS: ConcentrationTrend[] = ["more_concentrated", "less_concentrated", "stable", "insufficient_data"];

function test_every_direction_has_a_tone_symbol_label_and_explanation(): void {
  for (const direction of ALL_DIRECTIONS) {
    expect(DIRECTION_TONE[direction] !== undefined, `missing tone for ${direction}`);
    expect(DIRECTION_SYMBOL[direction] !== undefined, `missing symbol for ${direction}`);
    expect(DIRECTION_LABEL[direction] !== undefined && DIRECTION_LABEL[direction].length > 0, `missing label for ${direction}`);
    expect(
      DIRECTION_EXPLANATION[direction] !== undefined && DIRECTION_EXPLANATION[direction].length > 0,
      `missing explanation for ${direction}`
    );
  }
}

function test_mixed_and_insufficient_data_are_distinct_tones_from_stable(): void {
  expect(DIRECTION_TONE.mixed !== DIRECTION_TONE.stable, "mixed must never share stable's tone");
  expect(DIRECTION_TONE.insufficient_data !== DIRECTION_TONE.stable, "insufficient_data must never share stable's tone");
  expect(DIRECTION_TONE.mixed !== DIRECTION_TONE.insufficient_data, "mixed and insufficient_data must remain distinct from each other");
}

function test_increase_and_decrease_map_to_positive_and_negative_tones(): void {
  expect(DIRECTION_TONE.increase === "positive" && DIRECTION_TONE.strong_increase === "positive", "increase/strong_increase must be positive tone");
  expect(DIRECTION_TONE.decrease === "negative" && DIRECTION_TONE.strong_decrease === "negative", "decrease/strong_decrease must be negative tone");
}

function test_no_direction_label_or_explanation_uses_sensational_or_forecasting_language(): void {
  const forbidden = ["explod", "crash", "trillion-dollar", "opportunity", "should invest", "will grow", "guarantee"];
  for (const direction of ALL_DIRECTIONS) {
    const text = (DIRECTION_LABEL[direction] + " " + DIRECTION_EXPLANATION[direction]).toLowerCase();
    for (const word of forbidden) {
      expect(!text.includes(word), `direction ${direction} text contains forbidden word "${word}": ${text}`);
    }
  }
}

function test_insufficient_data_explanation_explicitly_distinguishes_from_zero_activity(): void {
  const text = DIRECTION_EXPLANATION.insufficient_data.toLowerCase();
  expect(text.includes("not the same as zero"), `expected an explicit zero-activity disclaimer, got: ${text}`);
}

function test_concentration_uses_a_separate_vocabulary_never_forecasting_language(): void {
  for (const trend of ALL_CONCENTRATION_TRENDS) {
    expect(CONCENTRATION_LABEL[trend] !== undefined, `missing label for ${trend}`);
    expect(CONCENTRATION_EXPLANATION[trend] !== undefined, `missing explanation for ${trend}`);
  }
  const moreText = CONCENTRATION_EXPLANATION.more_concentrated.toLowerCase();
  expect(!moreText.includes("good") && !moreText.includes("bad"), "concentration explanations must not moralize the trend");
}

function test_metric_labels_and_explanations_exist_for_all_three_components(): void {
  for (const metric of ["financing_activity", "companies_funded", "capital_deployed"] as const) {
    expect(METRIC_LABEL[metric] !== undefined && METRIC_LABEL[metric].length > 0, `missing label for ${metric}`);
    expect(METRIC_EXPLANATION[metric] !== undefined && METRIC_EXPLANATION[metric].length > 0, `missing explanation for ${metric}`);
  }
}

function main(): void {
  const tests = [
    test_every_direction_has_a_tone_symbol_label_and_explanation,
    test_mixed_and_insufficient_data_are_distinct_tones_from_stable,
    test_increase_and_decrease_map_to_positive_and_negative_tones,
    test_no_direction_label_or_explanation_uses_sensational_or_forecasting_language,
    test_insufficient_data_explanation_explicitly_distinguishes_from_zero_activity,
    test_concentration_uses_a_separate_vocabulary_never_forecasting_language,
    test_metric_labels_and_explanations_exist_for_all_three_components,
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
