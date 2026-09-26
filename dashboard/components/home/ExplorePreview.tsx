import Link from "next/link";

import Badge from "@/components/ui/Badge";
import BaseCard from "@/components/ui/BaseCard";
import Button from "@/components/ui/Button";

import { getTopStartups } from "@/lib/api";

// Phase 10.5, Part 9. "Instead of generic testimonials we do not have,
// use the actual product." An async Server Component (same convention
// already used by /rankings, /search, /startup/[id] -- see lib/api/
// client.ts's own comment on server-side callers) hitting the SAME public
// GET /top-startups endpoint TopStartupsTable already used on the old
// Home -- no new backend work, no fabricated company data. If the fetch
// fails, this section quietly renders nothing rather than showing an
// error banner on what's meant to be an inviting, low-friction page --
// the real Rankings page (linked right below) already owns error
// handling for this same data.
export default async function ExplorePreview() {
  let startups: Awaited<ReturnType<typeof getTopStartups>> = [];

  try {
    startups = await getTopStartups();
  } catch (error) {
    console.error("Explore preview: failed to load top startups:", error);
  }

  const preview = startups.slice(0, 3);

  if (preview.length === 0) {
    return null;
  }

  return (
    <section className="mx-auto max-w-4xl">
      <h2 className="text-center text-2xl font-bold tracking-tight text-text-primary sm:text-3xl">
        See how real startups stack up
      </h2>

      <p className="mx-auto mt-3 max-w-xl text-center text-base leading-7 text-text-secondary">
        Real, public VentureGPS Scores — not illustrations.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {preview.map((startup) => (
          <Link key={startup.company_name} href={`/startup/${encodeURIComponent(startup.company_name)}`}>
            <BaseCard className="p-5 transition-colors hover:border-primary/40">
              <p className="truncate text-sm font-semibold text-text-primary">
                {startup.company_name}
              </p>

              <div className="mt-2 flex items-center justify-between">
                <Badge tone="neutral">{startup.industry || "—"}</Badge>
                <span className="text-lg font-bold text-primary">
                  {startup.overall_score.toFixed(1)}
                </span>
              </div>
            </BaseCard>
          </Link>
        ))}
      </div>

      <div className="mt-8 flex justify-center">
        <Link href="/rankings">
          <Button variant="secondary">Explore Startups</Button>
        </Link>
      </div>
    </section>
  );
}
