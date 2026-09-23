// VentureGPS Increment 16.3 -- Section B's editorial introduction. Typography/spacing deliberately echoes the
// hero (CinematicHero.tsx): the same dot-marker eyebrow device, the same tight-tracked black display weight for
// the headline, the same `max-w-md` measure for supporting copy -- so Section B reads as a continuation of the
// same page, not a different application bolted on underneath it (Section 7: "follows the hero naturally").
// This section lives on the app's normal light/dark background (not the hero's fixed-dark photo treatment), so
// colors here use the ordinary text-primary/secondary tokens, not hardcoded white.
export default function SectionBIntro() {
  return (
    <div className="mx-auto max-w-2xl px-4 pb-10 pt-16 text-center sm:px-6 sm:pt-20">
      <div className="mx-auto inline-flex w-fit items-center gap-2">
        <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
        <span className="text-xs font-semibold uppercase tracking-[0.25em] text-text-muted">Discover the markets</span>
      </div>

      <h2 id="section-b-heading" className="mt-4 text-4xl font-black leading-[1.05] tracking-tight text-text-primary sm:text-5xl">
        Explore the Startup Economy
      </h2>

      <p className="mx-auto mt-4 max-w-md text-base leading-7 text-text-secondary sm:text-lg">
        Discover the technologies and industries shaping what&rsquo;s next.
      </p>
    </div>
  );
}
