import Link from "next/link";

import BaseCard from "@/components/ui/BaseCard";
import { SPSRing } from "@/components/sps";

import { isSpsTooCloseToRank } from "@/lib/compareInsights";
import { gridColsClass } from "./gridCols";

import type { ComparisonStartup } from "@/types";

type ComparisonHeaderProps = {
  startups: ComparisonStartup[];
  onRemove: (startupId: number) => void;
};

// Part 8: SPS stays visually prominent (the ring, same component every
// other canonical surface uses) but the numbers themselves are never
// altered -- this only adds restrained language when the whole selected
// set is within SPS_CLOSE_THRESHOLD of each other, so a 78.8-vs-78.7 gap
// doesn't read as "Ramp is the stronger company."
export default function ComparisonHeader({
  startups,
  onRemove,
}: ComparisonHeaderProps) {
  const tooClose = isSpsTooCloseToRank(startups);

  return (
    <div>
      <div className={`grid gap-4 ${gridColsClass(startups.length)}`}>
        {startups.map((startup) => (
          <BaseCard key={startup.startup_id} className="flex flex-col items-center gap-3 p-5 text-center">
            <button
              type="button"
              onClick={() => onRemove(startup.startup_id)}
              aria-label={`Remove ${startup.company_name} from comparison`}
              className="self-end text-xs font-medium text-text-muted hover:text-danger"
            >
              Remove ×
            </button>

            <Link
              href={`/startup/${encodeURIComponent(startup.company_name)}`}
              className="group"
            >
              {/* Phase 10.9 verification fix: when this startup has a V3
                  assessment, its overall SPS ring must reflect the SAME
                  number the Startup Profile page shows -- not V2.1's
                  overall_score, which stays a real, unrelated number
                  even when sps_v3.assessment_state is limited/insufficient
                  (i.e. "no comparable SPS"). Showing V2.1's number here
                  would imply a false numerical comparability the profile
                  page itself explicitly refuses to show. SPSRing's own
                  null-safety (Phase 10.9, Part 15/21) still applies for
                  the no-sps_v3 (V2.1-only) case below. */}
              {startup.sps_v3 && startup.sps_v3.assessment_state !== "sufficient" ? (
                <div
                  role="img"
                  aria-label={`${startup.company_name}: ${startup.sps_v3.assessment_state === "limited" ? "Limited assessment" : "Not enough evidence"}`}
                  className="flex h-[120px] w-[120px] shrink-0 flex-col items-center justify-center gap-1 rounded-full border-2 border-dashed border-border text-center"
                >
                  <span className="text-xs font-semibold text-text-muted px-3">
                    {startup.sps_v3.assessment_state === "limited" ? "Limited" : "Not enough"}
                  </span>
                  <span className="text-xs text-text-muted px-3">
                    {startup.sps_v3.assessment_state === "limited" ? "assessment" : "evidence"}
                  </span>
                </div>
              ) : (
                <SPSRing
                  score={startup.sps_v3 ? startup.sps_v3.overall_score : startup.overall_score}
                  size="sm"
                  showDetails={false}
                />
              )}

              <h2 className="mt-3 text-base font-semibold text-text-primary transition-colors group-hover:text-primary">
                {startup.company_name}
              </h2>
            </Link>

            <div className="flex flex-wrap justify-center gap-1.5 text-xs text-text-muted">
              {startup.industry ? <span>{startup.industry}</span> : null}
              {startup.industry && startup.company_stage ? <span>·</span> : null}
              {startup.company_stage ? <span>{startup.company_stage}</span> : null}
            </div>

            <Link
              href={`/startup/${encodeURIComponent(startup.company_name)}`}
              className="text-xs font-semibold text-primary hover:text-primary-hover"
            >
              View profile →
            </Link>
          </BaseCard>
        ))}
      </div>

      {tooClose ? (
        <p className="mt-3 text-center text-sm text-text-secondary">
          These startups have very close VentureGPS Scores — treat this
          as roughly tied, not a clear leader.
        </p>
      ) : null}
    </div>
  );
}
