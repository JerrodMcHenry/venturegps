# VentureGPS Market Page V1 — Increment 15

Status: implemented, unit-tested, typechecked, linted, production-built, and verified against a disposable
Postgres cluster seeded with real canonical fixtures (see Section 9). **Not committed, not pushed** — the user
reviews and handles Git manually for this repo.

The first public, mobile-first VentureGPS surface: `/markets/[slug]`, built on top of Increment 14's read-only
Capital Intelligence API. "VentureGPS — Navigate the Startup Economy," built for a visitor arriving from a video
link (YouTube/Shorts/TikTok/Reels) who has never seen the product before.

## 1. Routing and slug resolution

- Route: `dashboard/app/markets/[slug]/page.tsx`. `params` is `Promise<{ slug: string }>` (Next 16 App Router).
- No slug→UUID endpoint existed before this increment. Rather than resolving a slug by fetching the whole
  market list client-side, `GET /api/v2/markets` gained an optional `slug` query parameter
  (`app/v2/api.py`, `docs/v2/CAPITAL_API.md`) that resolves server-side, reusing
  `markets_repo.get_market_by_slug` — the one backend change in this increment. An unknown slug returns
  `{"markets": [], "total": 0}` (HTTP 200), never a 404 — that endpoint lists, it never asserts existence.
  `dashboard/lib/api/v2/markets.ts`'s `getMarketBySlug()` turns that into `MarketOut | null`.
- Taxonomy version: no per-visitor selection mechanism exists yet (there is exactly one registered taxonomy in
  practice). Per the increment's "smallest explicit config" instruction, added
  `dashboard/lib/api/v2/taxonomyVersion.ts`: `getConfiguredTaxonomyVersion()` reads
  `NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION`, defaulting to `venturegps_taxonomy.v1`.
- Unknown/unavailable markets are handled inline (`MarketNotAvailable.tsx`), following the existing
  `/v/[publicId]` precedent of an on-brand inline card rather than Next's generic `notFound()` boundary. Two
  distinct states, not one: `reason="unknown"` (the slug didn't resolve to any market — a bad/stale link) vs.
  `reason="unavailable"` (the market exists but its Capital Signal couldn't be fetched — a service/config
  problem). Both return HTTP 200 with friendly copy, matching the existing public-page convention in this repo.

## 2. Data integration

- `dashboard/types/v2/capital.ts` mirrors `app/v2/api_schemas.py` by hand (existing repo convention — no
  OpenAPI-to-TS pipeline). Every exact-value field (`minor_units`, `numerator`/`denominator`, counts inside
  Capital Signal components) is typed `string`, never `number`.
- `dashboard/lib/api/v2/client.ts` (pre-existing from Increment 14, extended this increment) is the one V2
  transport: typed `V2ApiError` with `.status`, `isV2NotFound`/`isV2ServiceUnavailable` helpers, a 10s timeout.
  Added an optional `revalidateSeconds` parameter (forwarded from `getMarketBySlug`/`getCapitalSignal`/
  `listMarkets`) so this public page can opt into Next's Data Cache — a market's Capital Signal is reused for 5
  minutes across visitors (`MARKET_REVALIDATE_SECONDS`), the discovery nav's market list for 15 minutes. No
  other caller's behavior changed (the parameter is optional and unused elsewhere).
- **One fetch, not two, for the page's main content.** `CapitalSignalResponse.current_window.metrics` already
  carries the full current-period `CapitalMetricsBodyOut` (financing activity, companies funded, capital
  deployed, concentration, stage distribution, diagnostics) — the same shape the separate `/capital/metrics`
  endpoint returns. The page uses that embedded window instead of making a second, redundant request to
  `/capital/metrics` for the same period. `getCapitalMetrics()` remains in `markets.ts` for any future caller
  that needs an arbitrary custom date range; this page doesn't need one.
- `generateMetadata` and the page component both need the same market+signal data; `loadMarketPageData` is
  wrapped in React's `cache()` (per Next's own "memoizing data requests" guidance) so they share one request,
  not two.
- No OpenAI/LLM calls anywhere in this page's request path — every number is a direct, unmodified read from the
  V2 Capital Intelligence API.

## 3. Exact-value handling

- `dashboard/lib/api/v2/money.ts`: BigInt-only parsing (`parseMinorUnits`), exact string formatting
  (`formatExactAmount`, always shown), and exactly one documented lossy step (`bigIntToChartNumber`) used only
  for SVG bar-height pixel coordinates. The abbreviated display form (`formatAbbreviatedAmount`, e.g. "$20.0M")
  is always paired with the exact form somewhere reachable (a detail row below the chart, a tooltip-equivalent
  aria-label, or a plain-language Explore-section sentence) — never shown alone.
- `formatRatioAsPercent` renders a `RatioOut` (percentile rank, concentration share) as a percentage using the
  same exact BigInt rounding as money, never `Number()`/`parseFloat()`.
- Two different currencies are never summed or converted. `CapitalChart` renders one series per currency;
  `CapitalSignalExplore`'s Verified Capital and Capital Concentration panels list one line per currency.
- `null` (`percentile_rank`, `current_share`) is rendered as "not enough history," never coerced to zero —
  enforced by rendering only when the field is present, with no fallback default of `0`.

## 4. Editorial hero (`MarketHero.tsx`)

Answers, in the first mobile viewport and without scrolling: which market (`display_name`), what VentureGPS can
tell about it (the `overall` Capital Signal direction, in `DIRECTION_LABEL`'s deliberately past-tense,
non-forecasting vocabulary), over what time period (the current 30-day window's dates, plus how many prior
periods back), and whether there's enough history for a historical read (the `insufficient_data`/`mixed` states
render with their own distinct copy, never silently folded into "stable"). `CoverageNote.tsx` states plainly
that these are *verified, VentureGPS-observed* financings, not a census — reused in both the hero and the
Explore section so the caveat is never a one-off aside.

## 5. Signature Capital chart (`CapitalChart.tsx`)

One interactive chart, metric-switchable (Financing Activity / Companies Funded / Verified Capital), with a
currency switcher that only appears when `capital_deployed` has more than one currency. Deliberately built as a
row of real `<button>` elements rather than clickable SVG shapes — every bar is a proper 44px touch target,
keyboard-focusable, with its own accessible name (`"Aug '26: 3 financings"` / the exact currency amount). The
selected bar's exact value is always shown as visible text below the chart, never only as a bar's rounded pixel
height. An `insufficient_data` direction renders a banner and disables the "how this compares" badge, but the
underlying counts/amounts still render (never invented, never hidden) — a lack of statistical confidence is not
the same as a lack of data. `prefers-reduced-motion` is honored via Tailwind's `motion-reduce:transition-none`
on the one CSS transition (bar height).

## 6. Explore the market (`CapitalSignalExplore.tsx`)

Six `Disclosure` panels (native `<details>`, zero extra JS, the existing design-system primitive): Financing
Activity, Companies Funded, Verified Capital, Stage Distribution, Capital Concentration, and a separate "How
this compares historically" panel covering all three Capital Signal components' directions plus concentration
trends together. The first five answer "what happened this period" (from `current_window.metrics`); the sixth
answers "is that unusual for this market" (from the Signal's own component/concentration data) — kept apart
deliberately, per Part 4's progressive-disclosure instruction, rather than merged into one paragraph per metric.
`ConcentrationTrend` gets its own symbol/label vocabulary (`CONCENTRATION_SYMBOL`/`CONCENTRATION_LABEL`), never
reusing `CapitalDirection`'s — concentration moving is not the same axis as activity increasing.

## 7. Market discovery (`MarketDiscoveryNav.tsx`)

A small `listMarkets()`-backed pill list of up to 8 other markets, explicitly not a feed, not personalized, not
a heatmap. An async server component rendered directly in JSX inside `page.tsx`; a discovery-fetch failure is
swallowed (returns `null`, no error surfaced) since it's a secondary affordance — the page's own content already
rendered by the time this runs.

## 8. Sharing and social metadata

- `dashboard/lib/site.ts` is new, small, explicit config (`getSiteUrl()`/`absoluteUrl()`, reading
  `NEXT_PUBLIC_SITE_URL`, defaulting to `http://localhost:3000`) — nothing in this app built canonical/absolute
  URLs before this increment (every existing page is relative-link-only, reached through gated navigation).
  Set `NEXT_PUBLIC_SITE_URL` to the real public origin before deploying.
- `generateMetadata` builds `title`, `description` (built from `DIRECTION_LABEL[signal.overall]` — the same
  vocabulary the page itself renders, never separately-authored marketing copy), `alternates.canonical`,
  `openGraph`, and `twitter` fields — verified live (Section 9) to render correctly, including a canonical
  `og:description` that read *"Sharply higher than usual: Robotics on VentureGPS..."* for seeded fixture data
  showing a real increase.
- `dashboard/app/markets/[slug]/opengraph-image.tsx` uses `next/og`'s `ImageResponse` (the sanctioned dynamic-OG
  file convention, not a custom image-generation service) — a dark, on-brand 1200×630 PNG with the market's real
  `display_name` and the VentureGPS wordmark/tagline, nothing fabricated. Verified live: renders a real
  39KB PNG (Section 9).
- `ShareMarketButton.tsx` (client component): Web Share API where supported (the primary path for mobile
  in-app browsers), falling back to clipboard copy with a visible link if `navigator.share`/`clipboard` are
  unavailable or denied. A user dismissing the native share sheet (`AbortError`) is not treated as a failure.

## 9. Testing

### Unit / pure-logic tests (`npm test`)

All hand-rolled (`expect()`/`PASS`/`FAIL`, this repo's existing convention — no jest/vitest). New this
increment: `v2Money` (16), `v2SignalLabels` (7), `v2TaxonomyVersion` (4), `v2ChartData` (7), `v2MarketSlug` (6),
`site` (5) — 45 new tests, all passing, plus the full pre-existing suite (200+ tests) still green.

### Static checks

- `npx tsc --noEmit`: clean. Required bumping `tsconfig.json`'s `target` from `ES2017` to `ES2020` — BigInt
  literals (`0n`, `1n`, ...) in `money.ts` aren't legal syntax below ES2020 under `tsc`'s own downlevel check.
  This only affects type-checking; Next's actual build output is governed by its own compiler target, not this
  field, and `npm run build` (below) confirms nothing regressed.
- `npm run lint`: clean (0 errors, 0 warnings after cleanup).
- `npm run build`: succeeds. `/markets/[slug]` and `/markets/[slug]/opengraph-image` both compile as dynamic
  (`ƒ`) routes, as expected for request-time data.

### Fixture-based verification against a disposable backend — distinct from the above

Per the increment's own instruction to test against a disposable backend "if practical," and clearly
distinguished here as **not** real production coverage:

1. Reused the scratch Postgres cluster already running from this increment's earlier DB work
   (`/tmp/v2pgu.l3bg`, port 54329) and ran `alembic upgrade head` against it (`V2_DATABASE_URL` set explicitly —
   never `DATABASE_URL`, never the real `.env`).
2. Seeded three real canonical markets using the *same* fixture-building helpers the automated V2 DB test suite
   itself uses (`app/v2/tests/db/{taxonomy_fakes,financing_fakes,capital_api_fakes}.py` — candidate → human
   `ResolutionDecision` → canonical `Company`/`FinancingEvent`, the only way a canonical record can exist):
   - `robotics` — 2 companies, 16 financing events across the full 9-window history plus a concentrated,
     currency-mixed (USD + EUR) current period, producing a real `strong_increase` overall Capital Signal.
   - `quantum-computing` — 1 company classified, zero financings: the "companies are classified but nothing
     observed this period" honesty state.
   - `biotech` — registered, nothing classified at all: the `classified_company_count == 0` honesty state.
3. Ran the real backend (`uvicorn app.api:app`) with `DATABASE_URL`/`V2_DATABASE_URL` pointed at the scratch
   cluster and dummy `OPENAI_API_KEY`/`TAVILY_API_KEY` values (never invoked by these read-only routes), and the
   real dashboard (`next dev`) with `NEXT_PUBLIC_API_URL` pointed at that backend.
4. Verified via direct HTTP requests against the running dev server (`curl`):
   - `/markets/robotics` renders real content (`Financing Activity`, `Companies Funded`, `Verified Capital`,
     `Stage distribution`, `Other markets`, `Share this market`) with no genuine error boundary triggered (the
     only "error" substrings present are Next's standard global-error-boundary scaffolding, present on every
     page).
   - `/markets/quantum-computing` renders the "Not enough history yet" insufficient-data state without the
     "no companies classified" copy (correct — a company *is* classified there).
   - `/markets/biotech` renders the "No companies are classified into this market yet" zero-coverage copy.
   - `/markets/totally-unknown-market` renders the `MarketNotAvailable reason="unknown"` card.
   - `<head>` carries a correct `canonical` link, `og:title`/`og:description`/`og:image`/`twitter:description`,
     with `og:description` reading real, non-fabricated copy driven by the actual computed direction.
   - `GET /markets/robotics/opengraph-image` returns a real `image/png`, 39,440 bytes — visually inspected and
     confirmed to show "Robotics," the VentureGPS wordmark, and the tagline on a dark branded background.
5. A live in-browser (Claude-in-Chrome) screenshot was attempted for full visual verification but the connected
   browser could not reach this machine's local dev server (a cross-machine/session limitation, not a defect in
   the page) — the HTML-content and OG-image checks above are the visual/functional verification available for
   this report.
6. Tore down the fixture backend, dev server, and scratch Postgres cluster after verification (Section 11).

**This is fixture verification against a disposable, throwaway database — it is not production coverage.** No
real canonical data was read, written, or touched at any point.

## 10. Non-goals (explicitly out of scope for this increment)

No native app, no PWA/service worker, no push notifications, no accounts/follows/watchlists, no social feed, no
founder tools, no AI chat, no 5-dimension Market Pulse, no Radar, no video hosting, no newsletter platform, no
new backend intelligence calculations, no full homepage redesign, no `/markets` index/browse page (the
discovery nav lives only inside an individual market page, per Part 5's "not a full discovery feed").

## 11. Known limitations

- `NEXT_PUBLIC_SITE_URL` must be set to the real public origin before this page's canonical/OG URLs are correct
  in production; it currently falls back to `http://localhost:3000`.
- The taxonomy version is a single global default (`NEXT_PUBLIC_VENTUREGPS_TAXONOMY_VERSION`), not a per-market
  or per-visitor selection — acceptable while exactly one taxonomy version is registered in practice; revisit if
  that changes.
- No live in-browser visual verification was possible from this session's environment (Section 9.5) — a
  reviewer should still open the page in a real mobile browser before shipping.
- The chart shows exactly 9 windows (8 historical + current) with no zoom/pan — matches the API's own fixed
  historical-window contract; there is no way to request a longer or shorter history from this page.

## 12. Future component reuse

`DirectionBadge.tsx`, `CoverageNote.tsx`, and the money/signal-label formatting modules
(`lib/api/v2/{money,signalLabels,chartData}.ts`) are written generically enough to be reused by a future
per-startup or per-founder Capital view, not just this market page. `CapitalChart.tsx`'s
button-row-as-bar-chart pattern is a reasonable starting point for any future V2 time-series visualization that
needs the same touch-target/keyboard-accessibility properties.

## 13. Proposed next increment

A `/markets` lightweight index (or a "browse markets" entry point from the main nav) so a visitor who arrives
without a specific slug — organic search, the homepage — can discover VentureGPS's markets at all; this
increment deliberately scoped discovery to *within* an already-loaded market page only.

---

## Increment 15.1 — Consumer Experience Refinement

Status: implemented, typechecked, linted, production-built, and visually reviewed live against the same
disposable-fixture backend as Increment 15. Frontend-only — no V2 canonical models, Capital Metrics, Capital
Signal methodology, migrations, ingestion, resolution, or API response contracts were touched. **Not committed,
not pushed.**

Triggered by a visual review of the live Increment 15 page that found three real problems: legacy Startup
Intelligence Engine navigation bleeding into a VentureGPS public page, a hero that pushed the chart below the
fold, and a Capital chart that rendered nearly empty regardless of the underlying data.

### Root cause: the "empty" chart

`CapitalChart.tsx`'s bar row had a definite height (`h-44`), but `items-end` sizes flex children to their own
content height, not the row's height — so each bar `<button>` had no definite height of its own. The colored bar
inside it was styled `height: {percent}%`, and a percentage height against an indefinite-height containing block
computes to effectively nothing per the CSS spec — every bar rendered at ~0px regardless of its real value. This
was a pure CSS/layout defect, not a data, scaling, or fixture problem (confirmed: the same fixture data, once the
CSS was fixed, renders bars with clearly correct relative heights — see the live screenshot evidence gathered
during this increment). Fixed by giving each bar's button a real, definite height (`h-full` against the row's own
fixed height) and moving period labels into a separate row below the bars, so a label's height can never compete
with a bar's percentage-height calculation. Genuine zero-value periods now render as a small deliberate dot
marker (ringed on the current period) rather than a bar at ~0px — a real zero must look distinct from "nothing
rendered," which is exactly what the original bug made indistinguishable.

### Public navigation isolation

Root layout (`app/layout.tsx`) wraps every route in one `AppShell` unconditionally — Next.js layouts always nest
additively, so a child route cannot remove an ancestor layout's chrome without restructuring the whole route
tree into parallel root layouts (a change well outside "frontend refinement only"). Instead, `AppShell.tsx`
became a client component (`usePathname()`) that renders a new `PublicHeader.tsx` (plain "VentureGPS — Navigate
the Startup Economy" wordmark, no nav menu) for any `/markets/*` route, and the existing `TopNav`/`MobileTabBar`
unchanged for every other route — the exact same `usePathname()`-branching pattern `TopNav.tsx`/`MobileTabBar.tsx`
already use internally for active-route state, just one level up. `PublicHeader` deliberately has **no** nav
links (no Discover/Companies/The Brief) because none of those routes exist yet — only `/markets/[slug]` itself
is a real, working public route today, and the instructions explicitly forbid dead links or placeholder pages
built to fill a header.

Also fixed: `generateMetadata`'s `title` used a bare string, which the root layout's `"%s | Startup Intelligence
Engine"` template then wrapped around — the browser tab, OG title, and search-result title all still said
"Startup Intelligence Engine" even after the visible page content was correctly VentureGPS-branded. Switched to
`title: { absolute: ... }`, which Next honors as a full override, bypassing the inherited template.

### Hero redesign

Rebuilt for compactness (Section 4 above describes the original). Now: name, one signal badge + a one-line
period caption, up to four real headline stat chips (Financings, Companies funded, and one chip per verified
currency — capped at two visible plus a "+N more" chip, since currencies are never combined or ranked against
each other), a single-sentence coverage caveat (still always visible, never hidden), and the fuller direction
explanation + period detail moved into one `<details>` element ("What does '...' mean?") rather than blocking
the fold. On a live desktop-width check this puts the chart's own heading on the same screen as the hero, and
every chip value reads directly from `signal.current_window.metrics` — nothing hardcoded, confirmed by checking
the same numbers against the Financing Snapshot module deeper down the page.

### Explore section redesign

Six identical `Disclosure` accordions replaced with a tiered layout: an always-visible "Financing snapshot" card
(Financing Activity + Companies Funded + Verified Capital combined into one plain-language paragraph, with raw
diagnostics counts moved into one small nested `<details>`), always-visible "Stage distribution" and "Capital
concentration" cards (each a small visual share bar — concentration's bar uses a new `ratioToPercentNumber()`
helper in `money.ts`, the second explicit, documented lossy BigInt→`number` conversion point in that file,
alongside `bigIntToChartNumber` — the exact percentage label next to it still comes from the existing, exact
`formatRatioAsPercent`), and exactly one remaining `Disclosure` ("How this compares historically") for the most
technical content — component-level Capital Signal directions and the methodology's own limitations paragraph.

### Files changed this increment

New: `components/layout/PublicHeader.tsx`. Modified: `components/layout/AppShell.tsx`,
`components/markets/{CapitalChart,MarketHero,CapitalSignalExplore}.tsx`, `lib/api/v2/money.ts` (added
`ratioToPercentNumber`), `app/markets/[slug]/page.tsx` (`title.absolute`). No files deleted, no new
dependencies, no backend files touched.

### Known limitations (additions)

- Breakpoint testing below desktop width (320/375/390/430/tablet) was attempted via the browser automation
  tool's `resize_window`, but the tool did not visibly change the captured viewport across three attempts in
  this environment — the layout was verified by CSS reasoning instead (every new/changed element uses
  `flex-wrap`, `flex-1`, or percentage widths; nothing introduces a fixed pixel width that could overflow a
  narrow viewport), not by an actual narrow-viewport screenshot. A reviewer should still check a real phone.
- The `Tabs` component's metric-switch click (Financing Activity → Companies Funded/Verified Capital) could not
  be triggered through the browser automation tool in this environment after several attempts (a tool
  interaction limitation — the same page's native `<details>` toggles worked fine via the same tool, and no
  console errors were present). This logic itself was not modified in this increment and remains covered by
  `tests/v2ChartData.test.ts`'s existing coverage of `buildCapitalDeployedSeries`/`buildCountSeries`; a reviewer
  should still click through the three metric tabs by hand.
- `PublicHeader` has no home link and no nav menu by design (Section "Public navigation isolation" above) —
  revisit the moment a second real public VentureGPS route exists.
