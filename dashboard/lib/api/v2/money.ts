// Exact money and ratio handling for the VentureGPS V2 Capital Intelligence API.
//
// The backend serializes every minor-unit amount and every Fraction numerator/denominator as a DECIMAL STRING
// (see docs/v2/CAPITAL_API.md's precision section) specifically because large amounts can exceed
// Number.MAX_SAFE_INTEGER and a Fraction cannot be represented exactly by a float. This file is the ONE place
// those strings are parsed -- with BigInt, never Number()/parseFloat() -- and the ONE place an approximate,
// human-readable display string is derived from them. The canonical string value is always still available to
// the caller (never discarded), for tooltips/exact display; only the abbreviated label is approximate, and
// this file is exactly the "explicit isolation" boundary Increment 15 asks for.
//
// This mirrors app/v2/domain/financing.py's CURRENCY_MINOR_UNIT_EXPONENTS exactly (a hand-kept mirror, same
// discipline as types/v2/capital.ts) -- extend it only if the backend's own allowlist grows.
const CURRENCY_MINOR_UNIT_EXPONENTS: Record<string, number> = {
  USD: 2, EUR: 2, GBP: 2, CAD: 2, AUD: 2, CHF: 2, SEK: 2, SGD: 2, INR: 2, ILS: 2, CNY: 2, JPY: 0,
};

function minorUnitExponent(currencyCode: string): number {
  return CURRENCY_MINOR_UNIT_EXPONENTS[currencyCode] ?? 2;
}

// Exact, BigInt-only rounding: round half away from zero. Never uses a float, so "half" is decided by exact
// integer comparison (2 * remainder vs. denominator), not by any approximate representation.
function divRoundBigInt(numerator: bigint, denominator: bigint): bigint {
  if (denominator === 0n) return 0n;

  const negative = (numerator < 0n) !== (denominator < 0n);
  const n = numerator < 0n ? -numerator : numerator;
  const d = denominator < 0n ? -denominator : denominator;
  const quotient = n / d;
  const remainder = n % d;
  const rounded = 2n * remainder >= d ? quotient + 1n : quotient;

  return negative ? -rounded : rounded;
}

export function parseMinorUnits(value: string): bigint {
  return BigInt(value);
}

// The exact value as a plain "whole.fraction" string in the currency's own units (e.g. "20000000.00" for
// minor_units="2000000000", currency "USD") -- no grouping, no symbol, no rounding: every digit the backend sent
// is preserved. Callers combine this with a currency code/symbol for display (see formatExactAmount).
export function minorUnitsToExactUnitString(minorUnitsStr: string, currencyCode: string): string {
  const exponent = minorUnitExponent(currencyCode);
  const minorUnits = parseMinorUnits(minorUnitsStr);
  const negative = minorUnits < 0n;
  const abs = negative ? -minorUnits : minorUnits;

  if (exponent === 0) {
    return `${negative ? "-" : ""}${abs.toString()}`;
  }

  const scale = 10n ** BigInt(exponent);
  const whole = abs / scale;
  const fraction = (abs % scale).toString().padStart(exponent, "0");

  return `${negative ? "-" : ""}${whole.toString()}.${fraction}`;
}

const CURRENCY_SYMBOLS: Record<string, string> = { USD: "$", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥" };

// The exact, full-precision display string for a tooltip or a detail row -- e.g. "$20,000,000.00". Grouped for
// readability; every digit is still exact (grouping a string never loses precision, unlike Number formatting).
export function formatExactAmount(minorUnitsStr: string, currencyCode: string): string {
  const [wholePart, fractionPart] = minorUnitsToExactUnitString(minorUnitsStr, currencyCode).split(".");
  const negative = wholePart.startsWith("-");
  const digits = negative ? wholePart.slice(1) : wholePart;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const symbol = CURRENCY_SYMBOLS[currencyCode];
  const amount = `${grouped}${fractionPart ? `.${fractionPart}` : ""}`;

  return symbol ? `${negative ? "-" : ""}${symbol}${amount}` : `${negative ? "-" : ""}${amount} ${currencyCode}`;
}

const ABBREVIATIONS: { threshold: bigint; suffix: string }[] = [
  { threshold: 1_000_000_000_000n, suffix: "T" },
  { threshold: 1_000_000_000n, suffix: "B" },
  { threshold: 1_000_000n, suffix: "M" },
  { threshold: 1_000n, suffix: "K" },
];

// An APPROXIMATE, human-friendly label (e.g. "$20.0M") for headline display where the exact figure would be
// visual noise. Rounds to one decimal place using exact BigInt arithmetic (divRoundBigInt) -- the approximation
// is in the CHOICE to abbreviate, never in the arithmetic itself. Always pair this with formatExactAmount
// somewhere reachable (a tooltip, an aria-label, an adjacent detail row) -- never show ONLY the abbreviated form.
export function formatAbbreviatedAmount(minorUnitsStr: string, currencyCode: string): string {
  const exponent = minorUnitExponent(currencyCode);
  const minorUnits = parseMinorUnits(minorUnitsStr);
  const negative = minorUnits < 0n;
  const abs = negative ? -minorUnits : minorUnits;
  const unitsScale = 10n ** BigInt(exponent); // minor units -> whole currency units
  const symbol = CURRENCY_SYMBOLS[currencyCode];
  const prefix = symbol ? (negative ? `-${symbol}` : symbol) : negative ? "-" : "";
  const suffixSpace = symbol ? "" : ` ${currencyCode}`;

  for (const { threshold, suffix } of ABBREVIATIONS) {
    const wholeThreshold = threshold * unitsScale;
    if (abs >= wholeThreshold) {
      // one decimal place: (abs * 10) / wholeThreshold, rounded, then re-inserted as a decimal digit
      const tenths = divRoundBigInt(abs * 10n, wholeThreshold);
      const whole = tenths / 10n;
      const tenth = tenths % 10n;
      return `${prefix}${whole.toString()}.${tenth.toString()}${suffix}${suffixSpace}`;
    }
  }

  return `${prefix}${(abs / unitsScale).toString()}${suffixSpace}`;
}

// A ratio (percentile rank, concentration share) as an exact fraction. Denominators here are always small
// (percentile rank is always /8; concentration is bounded by real minor-unit totals), but this still never uses
// a float: the displayed percentage is rounded with the same exact BigInt rounding as money.
export function formatRatioAsPercent(numerator: string, denominator: string): string {
  const n = BigInt(numerator);
  const d = BigInt(denominator);
  if (d === 0n) return "—";

  const tenths = divRoundBigInt(n * 1000n, d); // one decimal place of percent = three decimal places of ratio
  const whole = tenths / 10n;
  const tenth = tenths < 0n ? -tenths % 10n : tenths % 10n;

  return `${whole.toString()}.${tenth.toString()}%`;
}

// One of exactly two explicit, documented places an exact value becomes a JavaScript `number` in this module --
// for SVG/CSS pixel coordinates (CapitalChart.tsx), which are inherently approximate floating-point positions on
// screen, never a canonical value themselves. `precisionDigits` controls how much of the value is preserved
// before the necessarily-lossy conversion (16 is comfortably below Number.MAX_SAFE_INTEGER for any chart-scale
// ratio).
export function bigIntToChartNumber(value: bigint): number {
  return Number(value);
}

// The second (and last) such place: a ratio as an approximate 0-100 number, for a CSS bar-width percentage only
// (CapitalSignalExplore.tsx's concentration share bar) -- never for a displayed label (formatRatioAsPercent
// remains the one canonical, exact display path for the same ratio). Clamped into [0, 100] since a rendered
// width outside that range is meaningless regardless of what the ratio's raw value is.
export function ratioToPercentNumber(numerator: string, denominator: string): number {
  const d = BigInt(denominator);
  if (d === 0n) return 0;
  const n = BigInt(numerator);
  const tenths = divRoundBigInt(n * 1000n, d);
  return Math.min(Math.max(Number(tenths) / 10, 0), 100);
}
