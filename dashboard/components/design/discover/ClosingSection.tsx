// VentureGPS Increment 16, Section 4F ("Continue exploring") + Section 6 (sharing language) -- deliberately
// small. The Blueprint doc explains why "Continue Exploring" isn't a full separate section here: Explore Markets
// above already IS the "discover more" moment, so a second one immediately below would repeat it. This closing
// block instead does two things a full section shouldn't need: names the one still-missing surface (Companies)
// honestly, and shows the proposed shareable-card visual language as a static mock (not a real share action --
// the real ShareMarketButton component already exists and is exercised on the real market page, not duplicated
// here).
export default function ClosingSection() {
  return (
    <section aria-labelledby="closing-heading" className="py-10 sm:py-14">
      <div className="mx-auto max-w-3xl px-4 sm:px-6">
        <h2 id="closing-heading" className="text-xl font-bold text-text-primary">
          Built for sharing
        </h2>
        <p className="mt-2 max-w-xl text-sm leading-6 text-text-secondary">
          Every market page has a canonical URL, real Open Graph metadata, and a real share action today (see the
          production <code className="rounded bg-surface-muted px-1 py-0.5">/markets/[slug]</code> page). The mock
          below shows the intended visual language for a shared card &mdash; not a functional share control.
        </p>

        <div aria-hidden="true" className="mt-5 max-w-sm rounded-2xl border border-border bg-surface p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-primary" />
            <span className="text-sm font-bold text-text-primary">VentureGPS</span>
          </div>
          <p className="mt-3 text-lg font-bold text-text-primary">Robotics</p>
          <p className="mt-1 text-sm text-text-muted">Sharply higher than usual &middot; venturegps.com/markets/robotics</p>
        </div>

        <p className="mt-8 text-sm leading-6 text-text-muted">
          Companies (evidence-backed startup profiles and financing histories) is the fourth planned surface --
          no company read API exists yet, so it has no representation on this page beyond the navigation concept
          above.
        </p>
      </div>
    </section>
  );
}
