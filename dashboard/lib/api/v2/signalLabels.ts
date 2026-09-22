// Plain-language labels, symbols and tone mapping for the Capital Signal vocabulary (app/v2/domain/
// capital_signal.py's CapitalDirection / ConcentrationTrend). Pure, presentation-only: this file never decides a
// direction, it only describes one the backend already computed. Never renders a directional signal as a
// forecast or a quality judgement -- every label here describes a HISTORICAL COMPARISON, in the past tense.

import type { CapitalDirection, ComponentMetric, ConcentrationTrend } from "@/types/v2/capital";

export type SignalTone = "positive" | "negative" | "neutral" | "mixed" | "unknown";

// Maps to the app's existing --color-movement-positive/negative/neutral tokens (globals.css) -- no new hues
// introduced. "mixed" and "unknown" (insufficient_data) each get their OWN treatment, never folded into
// positive/negative/neutral, so a genuine disagreement or a lack of evidence is never visually confused with an
// ordinary, settled reading.
export const DIRECTION_TONE: Record<CapitalDirection, SignalTone> = {
  strong_increase: "positive",
  increase: "positive",
  stable: "neutral",
  decrease: "negative",
  strong_decrease: "negative",
  mixed: "mixed",
  insufficient_data: "unknown",
};

// A restrained arrow glyph per direction -- never an emoji, never an exclamation mark. Decorative; always paired
// with the text label below, never used alone (see DirectionBadge.tsx's aria handling).
export const DIRECTION_SYMBOL: Record<CapitalDirection, string> = {
  strong_increase: "↑↑",
  increase: "↑",
  stable: "→",
  decrease: "↓",
  strong_decrease: "↓↓",
  mixed: "◆",
  insufficient_data: "—",
};

// Short, deterministic, past-tense labels -- describing what the comparison FOUND, never predicting anything.
export const DIRECTION_LABEL: Record<CapitalDirection, string> = {
  strong_increase: "Sharply higher than usual",
  increase: "Higher than usual",
  stable: "Historically typical",
  decrease: "Lower than usual",
  strong_decrease: "Sharply lower than usual",
  mixed: "Mixed signals",
  insufficient_data: "Not enough history yet",
};

// One sentence of plain-language context per direction -- reused wherever a direction is shown, so the meaning
// never drifts between the hero and the component detail sections. Deliberately never uses "exploding",
// "crashing", "opportunity", or any evaluative/forecasting language.
export const DIRECTION_EXPLANATION: Record<CapitalDirection, string> = {
  strong_increase:
    "Current activity stands at or above the top of this market's own last 8 historical periods -- a genuinely unusual position, not a small change.",
  increase: "Current activity is running above what this market has typically shown over its recent history.",
  stable: "Current activity is within the ordinary range this market has shown over its recent history.",
  decrease: "Current activity is running below what this market has typically shown over its recent history.",
  strong_decrease:
    "Current activity stands at or below the bottom of this market's own last 8 historical periods -- a genuinely unusual position, not a small change.",
  mixed:
    "Some Capital measures moved up while others moved down over the same period, so no single direction fairly describes this market right now.",
  insufficient_data:
    "VentureGPS has not yet observed enough historical periods for this market to compare current activity against -- this is not the same as zero activity.",
};

export const METRIC_LABEL: Record<ComponentMetric, string> = {
  financing_activity: "Financing Activity",
  companies_funded: "Companies Funded",
  capital_deployed: "Verified Capital",
};

export const METRIC_EXPLANATION: Record<ComponentMetric, string> = {
  financing_activity:
    "How many distinct, canonical financings VentureGPS has verified for this market in a given period. One financing counts once, no matter how many sources reported it.",
  companies_funded:
    "How many distinct companies had at least one verified financing in a given period. A company with three rounds in one period still counts once.",
  capital_deployed:
    "The sum of verified round amounts VentureGPS has accepted for this market, kept separate by currency -- amounts are never converted or combined across currencies.",
};

// A SEPARATE vocabulary from CapitalDirection on purpose: "more concentrated" is a fact about how capital was
// distributed, not a positive or negative judgement about the market. See docs/v2/CAPITAL_METHODOLOGY.md.
export const CONCENTRATION_LABEL: Record<ConcentrationTrend, string> = {
  more_concentrated: "More concentrated than usual",
  less_concentrated: "Less concentrated than usual",
  stable: "Typically concentrated",
  insufficient_data: "Not enough history yet",
};

export const CONCENTRATION_EXPLANATION: Record<ConcentrationTrend, string> = {
  more_concentrated:
    "The largest single financing accounted for a bigger share of verified capital than this market's own recent history -- capital was more concentrated in fewer, larger rounds. This is a description of distribution, not a judgement.",
  less_concentrated:
    "The largest single financing accounted for a smaller share of verified capital than this market's own recent history -- capital was spread across more financings. This is a description of distribution, not a judgement.",
  stable: "The largest single financing's share of verified capital was within this market's ordinary historical range.",
  insufficient_data: "Not enough historical periods with verified capital exist yet to compare concentration.",
};
