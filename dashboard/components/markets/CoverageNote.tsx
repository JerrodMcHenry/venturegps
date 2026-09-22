// VentureGPS Increment 15. The one shared explanation of what VentureGPS's numbers actually mean: an observed,
// verified count of financings VentureGPS has canonicalized -- not a census of every financing that happened in
// the real world. Reused wherever a raw count could otherwise be misread as "nothing happened" (Increment 15
// instructions, Part 4: "never imply that a market with no observed financings had no real-world activity").
//
// diagnostics is optional: the hero shows a short, context-free version of this note before any metrics have
// loaded meaning; the Explore section passes the real diagnostics so classifiedCompanyCount can be shown too.
import type { CapitalMetricsDiagnosticsOut } from "@/types/v2/capital";

type CoverageNoteProps = {
  diagnostics?: CapitalMetricsDiagnosticsOut;
  className?: string;
};

export default function CoverageNote({ diagnostics, className = "" }: CoverageNoteProps) {
  return (
    <p className={["text-sm leading-6 text-text-muted", className].join(" ")}>
      These are financings VentureGPS has verified and classified into this market -- not a full census of every
      financing that happened.{" "}
      {diagnostics ? (
        <>
          {diagnostics.classified_company_count === 0
            ? "No companies are classified into this market yet, so a reading of zero here reflects VentureGPS's current coverage, not necessarily zero real-world activity."
            : `${diagnostics.classified_company_count.toLocaleString()} companies are currently classified into this market.`}
        </>
      ) : (
        "A market with no verified activity yet may still have real-world financings VentureGPS hasn't captured."
      )}
    </p>
  );
}
