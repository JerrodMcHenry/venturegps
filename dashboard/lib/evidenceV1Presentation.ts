import type {
  EvidenceV1AnalysisDetail,
  EvidenceV1DimensionResult,
  EvidenceV1PillarResult,
} from "@/types";

// Final UX correction -- insight-first presentation of an Evidence-v1
// report. PURE derivation over the already-persisted artifact: no network,
// no AI call, no recomputation of any Evidence Engine value. Every number
// shown by the report is read from the artifact as-is (strength,
// coverage_pct, confidence, score); this module only decides ORDER,
// GROUPING and plain-English WORDING. Kept free of React/Next imports
// (type-only imports are erased) so tests/evidenceV1Presentation.test.ts
// can execute it directly under Node.
//
// Deliberately never produces: an overall company score, an average of
// pillar strengths, or any claim about a pillar that did not publish.

export function humanizeDimensionName(dimension: string): string {
  return dimension.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// classification_label is an engine enum (e.g. "CORROBORATED_MOAT"); shown
// to the reader only as its own words, sentence-cased -- never reworded
// into a stronger or weaker claim than the label itself makes.
export function humanizeClassificationLabel(label: string | null): string | null {
  if (!label) return null;
  const words = label.toLowerCase().replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// One plain-language reason per engine availability status. These are the
// ONLY gap explanations the report gives -- each is a direct reading of a
// dimension's persisted `availability`, never an inferred cause.
const AVAILABILITY_GAP_LABELS: Record<string, string> = {
  unscored_no_evidence: "no qualifying public evidence was found",
  unscored_stale: "the available evidence was too old to rely on",
  unscored_disputed: "available sources conflicted",
  unscored_uncorroborated: "available evidence was not independently corroborated",
  unscored_extraction_failed: "available evidence could not be read reliably",
};

export function availabilityGapLabel(availability: string): string {
  return AVAILABILITY_GAP_LABELS[availability] ?? "the available evidence did not qualify";
}

export function isScored(dimension: EvidenceV1DimensionResult): boolean {
  return dimension.score != null;
}

export type PillarGap = {
  pillar: string;
  // Persisted availability -> plain-language reason, with the dimensions
  // it applies to. Grouped so "no evidence for A, B, C" reads as one line.
  reasons: { reason: string; dimensions: string[] }[];
};

function groupUnscoredDimensions(pillar: EvidenceV1PillarResult): PillarGap["reasons"] {
  const groups = new Map<string, string[]>();
  for (const dimension of pillar.dimension_results) {
    if (isScored(dimension)) continue;
    const reason = availabilityGapLabel(dimension.availability);
    groups.set(reason, [...(groups.get(reason) ?? []), humanizeDimensionName(dimension.dimension)]);
  }
  return [...groups.entries()].map(([reason, dimensions]) => ({ reason, dimensions }));
}

export function pillarGap(pillar: EvidenceV1PillarResult): PillarGap {
  return { pillar: pillar.pillar, reasons: groupUnscoredDimensions(pillar) };
}

export type KeyFinding = {
  pillar: string;
  dimension: string;
  score: number;
  label: string | null;
};

// Strongest findings come ONLY from pillars that cleared their own
// publication gate -- a scored dimension inside a withheld pillar is still
// visible in that pillar's details, but is never promoted to the summary,
// which would bypass the gate the methodology applies.
export function strongestFindings(pillars: EvidenceV1PillarResult[], limit = 3): KeyFinding[] {
  const findings: KeyFinding[] = [];
  for (const pillar of pillars) {
    if (!pillar.publishable) continue;
    for (const dimension of pillar.dimension_results) {
      if (dimension.score == null) continue;
      findings.push({
        pillar: pillar.pillar,
        dimension: humanizeDimensionName(dimension.dimension),
        score: dimension.score,
        label: humanizeClassificationLabel(dimension.classification_label),
      });
    }
  }
  // Stable: ties keep canonical pillar/dimension order.
  return findings
    .map((finding, index) => ({ finding, index }))
    .sort((a, b) => b.finding.score - a.finding.score || a.index - b.index)
    .slice(0, limit)
    .map(({ finding }) => finding);
}

function joinList(items: string[]): string {
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

const COUNT_WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six"];

function countWord(n: number): string {
  return COUNT_WORDS[n] ?? String(n);
}

// "technical depth signal (classified as substantial)" -- the dimension in
// running-text case, plus the engine's own classification label verbatim
// when it has one. No score: scores are shown right next to the summary.
function findingPhrase(finding: KeyFinding): string {
  const name = finding.dimension.toLowerCase();
  return finding.label ? `${name} (classified as ${finding.label.toLowerCase()})` : name;
}

// The executive summary reads as prose, not serialized state: it does NOT
// restate the area count, Strength or Confidence, which the overview and
// the assessed-area card already show. Every clause is still a direct
// reading of the artifact -- which pillars published, which published
// dimensions scored highest (and their classification labels), and, when
// every gap shares one persisted availability reason, that reason.
function buildExecutiveSummary(
  company: string,
  published: EvidenceV1PillarResult[],
  withheld: EvidenceV1PillarResult[],
  findings: KeyFinding[],
  gaps: PillarGap[]
): string[] {
  const summary: string[] = [];

  if (published.length === 0) {
    summary.push(
      `The public evidence gathered for ${company} was not sufficient to evaluate any area reliably, so this report contains no assessed findings yet.`
    );
  } else {
    let first = `Public evidence was sufficient to evaluate ${joinList(published.map((p) => p.pillar))} for ${company}.`;
    if (findings.length > 0) {
      first += ` The best-supported results are ${joinList(findings.map(findingPhrase))}.`;
    }
    summary.push(first);
  }

  if (withheld.length > 0) {
    const reasons = new Set(gaps.flatMap((g) => g.reasons.map((r) => r.reason)));
    const why =
      reasons.size === 1
        ? `${[...reasons][0]} for ${withheld.length === 1 ? "it" : "them"}`
        : "the public evidence gathered did not support a reliable assessment";
    const verb = withheld.length === 1 ? "remains" : "remain";
    summary.push(
      `${joinList(withheld.map((p) => p.pillar))} ${verb} unknown — ${why}. Missing evidence is not negative evidence: these are open questions, not weaknesses.`
    );
  }

  return summary;
}

export type ReportPresentation = {
  published: EvidenceV1PillarResult[];
  withheld: EvidenceV1PillarResult[];
  // Canonical (methodology) order, untouched -- used by the overview strip.
  canonical: EvidenceV1PillarResult[];
  findings: KeyFinding[];
  gaps: PillarGap[];
  summary: string[];
  gapsLead: string;
};

export function buildReportPresentation(analysis: EvidenceV1AnalysisDetail): ReportPresentation {
  const canonical = analysis.result.pillar_results;
  // Presentation ordering only: assessed areas first, each group keeping
  // the methodology's own canonical order.
  const published = canonical.filter((p) => p.publishable);
  const withheld = canonical.filter((p) => !p.publishable);
  const findings = strongestFindings(canonical);
  const gaps = withheld.map(pillarGap);

  const summary = buildExecutiveSummary(analysis.company_name, published, withheld, findings, gaps);

  const gapsLead =
    published.length > 0
      ? `VentureGPS found enough evidence to assess ${joinList(published.map((p) => p.pillar))}. ${countWord(withheld.length)} additional ${withheld.length === 1 ? "area remains" : "areas remain"} unscored because the available public evidence did not meet the required threshold.`
      : `VentureGPS could not reliably assess any area from the public evidence gathered.`;

  return { published, withheld, canonical, findings, gaps, summary, gapsLead };
}

export function pillarAnchorId(pillar: string): string {
  return `pillar-${pillar.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")}`;
}
