// Increment 15.1 -- an isolated public-facing header for VentureGPS routes (currently just /markets/[slug]),
// rendered by AppShell.tsx INSTEAD of the legacy TopNav/MobileTabBar for that route prefix only -- every other
// route keeps the existing "Startup Intelligence Engine" chrome completely unchanged. This is deliberately NOT a
// nav menu: today there is exactly one public VentureGPS surface (an individual market page) and no `/markets`
// index, no `/discover`, no `/companies`, no `/the-brief` -- adding links to any of those would be exactly the
// "dead navigation link" / "unfinished page to fill the header" this increment's instructions forbid. This is
// branding only: the wordmark is plain text, not a <Link>, since there is no VentureGPS home to send it to yet.
// Revisit this file the moment a second real public route exists (see docs/product/VENTUREGPS_MARKET_PAGE_V1.md's
// "known limitations").
export default function PublicHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-2 px-4 sm:px-6 lg:px-10">
        <span aria-hidden="true" className="size-2 shrink-0 rounded-full bg-primary" />
        <span className="text-base font-bold tracking-tight text-text-primary">VentureGPS</span>
        <span className="hidden text-sm text-text-muted sm:inline">— Navigate the Startup Economy</span>
      </div>
    </header>
  );
}
