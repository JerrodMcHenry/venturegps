import Link from "next/link";
import { auth } from "@clerk/nextjs/server";

import { getSPSHistory, getStartupProfile } from "@/lib/api";

import BaseCard from "@/components/ui/BaseCard";
import StartupHeroV2 from "@/components/startup/StartupHeroV2";
import HowThisAnalysisWasGenerated from "@/components/startup/HowThisAnalysisWasGenerated";
import SPSHistory from "@/components/startup/SPSHistory";
import IntelligencePillars from "@/components/startup/IntelligencePillars";
import ClaimStartupButton from "@/components/startup/ClaimStartupButton";
import SaveStartupButton from "@/components/startup/SaveStartupButton";

import type { SPSHistoryPoint, StartupProfileResponse } from "@/types";

type Props = {
  params: Promise<{
    id: string;
  }>;
};

function isNotFoundError(error: unknown): boolean {
  return error instanceof Error && /\(404\)/.test(error.message);
}

// Rankings/Search build this route's href with
// encodeURIComponent(companyName) (required — company names can contain
// spaces/&/etc. that aren't valid unencoded in a URL). getStartupProfile /
// getSPSHistory also encode when constructing the backend request (required
// — that's the actual outgoing HTTP call). Decoding exactly once here,
// where the raw path segment enters application code, is what keeps that
// pair of encodes to a net single encoding pass end-to-end; skipping this
// step is what previously left the API call encoding an already-encoded
// value (e.g. "Ramp%20Business%20Corporation" -> "Ramp%2520..."), which the
// backend could never match against a stored company_name. Safe for names
// that were never encoded to begin with — decodeURIComponent on a string
// with no percent-sequences is a no-op — and guarded against a malformed
// sequence rather than letting the page crash on one.
function decodeCompanyNameParam(id: string): string {
  try {
    return decodeURIComponent(id);
  } catch {
    return id;
  }
}

async function loadStartupProfile(
  id: string,
  token: string | null
): Promise<StartupProfileResponse | null> {
  try {
    return await getStartupProfile(id, token);
  } catch (error) {
    if (isNotFoundError(error)) {
      return null;
    }

    throw error;
  }
}

// SPS History is supplementary to the profile, not core to it — any
// failure here (network hiccup, etc.) degrades to an empty history rather
// than breaking the page.
async function loadSPSHistory(id: string, token: string | null): Promise<SPSHistoryPoint[]> {
  try {
    return await getSPSHistory(id, token);
  } catch {
    return [];
  }
}

export default async function StartupProfilePage({ params }: Props) {
  // Portfolio Release Task 3B -- Secure Analysis Visibility: this route was
  // fully public (no auth at all) -- confirmed by the read-only audit as
  // the headline leak vector (a signed-in user's uploaded pitch deck could
  // end up quoted, verbatim, in methodology evidence, returned here to
  // anyone, no login required). auth.protect() is the real, resource-based,
  // server-side gate (redirects a signed-out visitor to /sign-in itself);
  // GET /startup/{name} on the backend enforces its own auth AND the real
  // submitter/member/admin visibility rule independently (app/auth.py,
  // app/database/db.py's _analysis_visibility_clause()) -- this page-level
  // check alone cannot and does not decide who may see which analysis.
  //
  // This stays a Server Component (unlike Founder Workspace's client-side
  // useAuth().getToken() pattern, which exists because that page has its
  // own separate interactive-client reasons) -- Clerk's own server-side
  // auth().getToken() is the correct, idiomatic way for a Server Component
  // to obtain a token to forward to an external API call.
  await auth.protect();
  const { getToken } = await auth();
  const token = await getToken();

  const { id } = await params;
  const companyName = decodeCompanyNameParam(id);

  // MVP hardening: these two requests don't depend on each other (both
  // only need companyName), so run them in parallel rather than paying
  // two sequential network round trips for every profile load. The one
  // trade-off is that a "not found" company also fires (and discards) an
  // SPS-history request it didn't need -- a small, one-time cost on a
  // rare path, in exchange for materially faster loads on the common one.
  const [startup, history] = await Promise.all([
    loadStartupProfile(companyName, token),
    loadSPSHistory(companyName, token),
  ]);

  if (!startup) {
    return (
      <BaseCard variant="glass" className="p-10 text-center">
        <h1 className="text-2xl font-bold text-text-primary">
          Startup not found
        </h1>

        <p className="mt-3 text-text-secondary">
          No startup profile was found for &ldquo;{companyName}&rdquo;. It may
          need to be analyzed first, or the name may not match exactly.
        </p>

        <Link
          href="/search"
          className="mt-6 inline-flex text-sm font-semibold text-primary hover:text-primary-hover"
        >
          Back to search →
        </Link>
      </BaseCard>
    );
  }

  // Phase 37E -- Company Lifecycle + Public Identity Convergence, Section
  // 6. Distinguishes "this company does not exist" (the !startup branch
  // above) from "this company exists but SIE hasn't analyzed it yet" --
  // previously indistinguishable, both rendering the same "Startup not
  // found" message even though the second case has a real, canonical
  // company behind it (e.g. a freshly created company profile). Only
  // genuinely public facts render here -- the company's own name and
  // when it was added -- never a fabricated score, pillar, or
  // confidence value for a company with no analysis at all.
  if (!startup.has_analysis || !startup.methodology) {
    return (
      <div className="space-y-8">
        <BaseCard variant="glass" className="p-10">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <h1 className="text-4xl font-bold text-text-primary">{startup.canonical_name}</h1>

            {startup.startup_id != null ? (
              <div className="flex flex-col items-end gap-2">
                <ClaimStartupButton startupId={startup.startup_id} />
                <SaveStartupButton startupId={startup.startup_id} />
              </div>
            ) : null}
          </div>

          <p className="mt-4 max-w-prose text-base leading-7 text-text-secondary">
            VentureGPS has not analyzed {startup.canonical_name} yet — there is no VentureGPS Score,
            pillar breakdown, or evidence to show. This page will update automatically once an
            analysis exists.
          </p>
        </BaseCard>
      </div>
    );
  }

  const methodology = startup.methodology;

  return (
    <div className="space-y-8">
      {/* Portfolio Release Task 6, Step 3 -- Simplify the Report: one
          coherent CURRENT-analysis view first (hero/score/summary/risks,
          the six pillar sections, then expandable evidence/methodology),
          with historical trend information (Score History) moved BELOW
          all of it -- previously it sat between the hero and the pillar
          detail, ahead of the actual current-report content it's a
          supplement to. Nothing about SPSHistory's own data or behavior
          changed, only where it renders on the page. */}
      <StartupHeroV2
        methodology={methodology}
        createdAt={startup.created_at}
        startupId={startup.startup_id}
      />

      <IntelligencePillars methodology={methodology} />

      <HowThisAnalysisWasGenerated analysisContext={methodology.analysis_context} />

      <SPSHistory history={history} />
    </div>
  );
}
