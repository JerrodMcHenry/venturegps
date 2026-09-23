// VentureGPS Increment 16, Section 4E -- "The Brief," the editorial/video connective-tissue surface. Every card
// here is explicitly `status: "planned"` (sampleData.ts) -- Jerrod has not published VentureGPS video content
// yet, so this section is rendered in a visibly muted, disabled-looking treatment (dashed borders, no hover
// affordance, a "Planned" chip) rather than styled identically to real, working content. This is the "distinguish
// current from future functionality" instruction applied to an entire section, not just a nav item.
import type { SampleStory } from "./sampleData";

type BriefSectionProps = {
  stories: SampleStory[];
};

export default function BriefSection({ stories }: BriefSectionProps) {
  return (
    <section aria-labelledby="brief-heading" className="border-b border-border py-10 sm:py-14">
      <div className="mx-auto max-w-3xl px-4 sm:px-6">
        <div className="flex items-center gap-2">
          <h2 id="brief-heading" className="text-2xl font-bold text-text-primary sm:text-3xl">
            The VentureGPS Brief
          </h2>
          <span className="rounded-full border border-dashed border-border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            Planned
          </span>
        </div>
        <p className="mt-2 max-w-xl text-base leading-7 text-text-secondary">
          Videos, shorts, and written market breakdowns, each connected to the real market page behind them. No
          content has been published yet &mdash; these are placeholders showing the intended shape.
        </p>

        <ul className="mt-5 space-y-2.5">
          {stories.map((story) => (
            <li key={story.title} className="flex items-start gap-3 rounded-xl border border-dashed border-border bg-surface-subtle p-4">
              <span className="mt-0.5 shrink-0 rounded-full border border-border px-2 py-0.5 text-[11px] font-semibold text-text-muted">
                {story.format}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-text-secondary">{story.title}</p>
                {story.marketSlug ? (
                  <p className="mt-0.5 text-xs text-text-muted">Would connect to: {story.marketSlug}</p>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
