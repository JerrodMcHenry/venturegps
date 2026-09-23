// VentureGPS Increment 16, Section 2 -- illustrates the proposed four-surface primary navigation (Discover /
// Markets / Companies / Stories) and, just as importantly, which of those are real today. Deliberately NOT built
// from real <Link> elements pointing at guessed destinations: there is no `/markets` INDEX yet (only individual
// `/markets/[slug]` pages), no company read API, and no Stories content -- a nav item that LOOKED clickable but
// led nowhere real, or to a guessed URL that might 404, is exactly the "dead link disguised as functional
// navigation" this increment's instructions forbid. So every item here states its own real status in one line,
// and only "Discover" (this page, current) is actually the current location.
type NavConceptItem = {
  label: string;
  status: string;
  current?: boolean;
};

const ITEMS: NavConceptItem[] = [
  { label: "Discover", status: "This page", current: true },
  { label: "Markets", status: "Individual pages live today (see below) — index page not yet built" },
  { label: "Companies", status: "Coming soon — no company read API yet" },
  { label: "Stories", status: "Coming soon — no video content published yet" },
];

export default function DiscoverNavConcept() {
  return (
    <nav aria-label="Proposed VentureGPS primary navigation (concept)" className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Proposed navigation (concept, not live)</p>
      <ul className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {ITEMS.map((item) => (
          <li
            key={item.label}
            className={[
              "rounded-xl border px-3 py-2.5",
              item.current ? "border-primary/50 bg-primary/5" : "border-dashed border-border bg-surface-subtle",
            ].join(" ")}
          >
            <p className={["text-sm font-semibold", item.current ? "text-primary" : "text-text-primary"].join(" ")}>{item.label}</p>
            <p className="mt-0.5 text-[11px] leading-4 text-text-muted">{item.status}</p>
          </li>
        ))}
      </ul>
    </nav>
  );
}
