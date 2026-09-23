// VentureGPS Increment 17.1 -- promoted verbatim (copy and structure) from the approved
// components/design/cinematicHomepage/sectionB/SectionBIntro.tsx prototype. No sample-data dependency existed
// here to begin with (this component is pure copy/typography), so nothing needed to change to make it
// production-ready.
export default function MarketDiscoveryIntro() {
  return (
    <div className="mx-auto max-w-2xl px-4 pb-10 pt-16 text-center sm:px-6 sm:pt-20">
      <div className="mx-auto inline-flex w-fit items-center gap-2">
        <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
        <span className="text-xs font-semibold uppercase tracking-[0.25em] text-text-muted">Discover the markets</span>
      </div>

      <h2 id="market-discovery-heading" className="mt-4 text-4xl font-black leading-[1.05] tracking-tight text-text-primary sm:text-5xl">
        Explore the Startup Economy
      </h2>

      <p className="mx-auto mt-4 max-w-md text-base leading-7 text-text-secondary sm:text-lg">
        Discover the technologies and industries shaping what&rsquo;s next.
      </p>
    </div>
  );
}
