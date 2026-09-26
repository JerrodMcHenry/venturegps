import { SPSRing } from "@/components/sps";

import type { SPSV3Assessment } from "@/types";

type SPSV3ScoreSectionProps = {
  sps: SPSV3Assessment;
};

// Phase 10.9, Part 14/16/17 -- shared, jargon-free copy for Coverage and
// Confidence, reused by every V3 state below so the two concepts are
// always explained the same way regardless of which state a startup
// lands in.
function CoverageConfidenceBadges({ sps }: { sps: SPSV3Assessment }) {
  return (
    <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs">
      <span
        className="rounded-full border border-border px-3 py-1 font-medium text-text-secondary"
        title="Coverage shows how much of the startup we know enough about to evaluate. It is not a quality score -- a higher number just means we could responsibly assess more of the company."
      >
        Coverage {sps.coverage_pct.toFixed(0)}%
      </span>
      <span
        className="rounded-full border border-border px-3 py-1 font-medium text-text-secondary"
        title="Confidence reflects the quality, recency, and corroboration of the evidence behind this assessment -- not the likelihood the company succeeds."
      >
        {sps.confidence} confidence
      </span>
    </div>
  );
}

// Phase 10.9, Part 2 -- SUFFICIENT: the full ring, exactly like the V2.1
// hero, just driven by sps.overall_score instead of
// startup_intelligence_score. overall_score is guaranteed non-null here
// (SPSV3Assessment's own invariant: assessment_state === "sufficient"
// always pairs with a real overall_score -- enforced server-side by
// app/ai/sps_v3_engine/aggregation.py's SPSResult).
function SufficientScore({ sps }: { sps: SPSV3Assessment }) {
  return (
    <div className="flex flex-col items-center">
      <SPSRing score={sps.overall_score} confidence={sps.confidence} size="xl" />
      <CoverageConfidenceBadges sps={sps} />
    </div>
  );
}

// Phase 10.9, Part 2/14 -- LIMITED: no giant fake overall score. Leads
// with "Limited public assessment," lists whichever pillars ARE
// individually publishable with their own strength, and clearly names
// the ones that aren't -- never silently omitted.
function LimitedScore({ sps }: { sps: SPSV3Assessment }) {
  const pillars = Object.values(sps.pillars);
  const publishable = pillars.filter((p) => p.publishable);
  const unavailable = pillars.filter((p) => !p.publishable);

  return (
    <div className="w-full max-w-xs text-center">
      <p className="text-sm font-semibold text-text-primary">Limited public assessment</p>
      <p className="mt-1 text-sm text-text-secondary">
        Not enough public evidence yet for a full VentureGPS Score -- here&rsquo;s what we could
        responsibly assess.
      </p>

      {publishable.length > 0 ? (
        <dl className="mt-4 space-y-1.5 text-left">
          {publishable.map((pillar) => (
            <div key={pillar.pillar} className="flex items-center justify-between text-sm">
              <dt className="text-text-secondary">{pillar.pillar}</dt>
              <dd className="font-semibold text-text-primary">{pillar.strength?.toFixed(0)}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {unavailable.length > 0 ? (
        <dl className="mt-2 space-y-1.5 text-left">
          {unavailable.map((pillar) => (
            <div key={pillar.pillar} className="flex items-center justify-between text-sm">
              <dt className="text-text-muted">{pillar.pillar}</dt>
              <dd className="text-xs text-text-muted">Not enough evidence</dd>
            </div>
          ))}
        </dl>
      ) : null}

      <CoverageConfidenceBadges sps={sps} />
    </div>
  );
}

// Phase 10.9, Part 2/14 -- INSUFFICIENT: no empty ring at all. A plain
// explanation plus Coverage, so the number always has context even when
// there's nothing else to show.
function InsufficientScore({ sps }: { sps: SPSV3Assessment }) {
  return (
    <div className="w-full max-w-xs text-center">
      <p className="text-sm font-semibold text-text-primary">Not enough evidence yet</p>
      <p className="mt-1 text-sm text-text-secondary">
        We don&rsquo;t have enough public evidence yet to evaluate this company&rsquo;s fundamentals.
      </p>
      <CoverageConfidenceBadges sps={sps} />
    </div>
  );
}

export default function SPSV3ScoreSection({ sps }: SPSV3ScoreSectionProps) {
  if (sps.assessment_state === "sufficient") {
    return <SufficientScore sps={sps} />;
  }

  if (sps.assessment_state === "limited") {
    return <LimitedScore sps={sps} />;
  }

  return <InsufficientScore sps={sps} />;
}
