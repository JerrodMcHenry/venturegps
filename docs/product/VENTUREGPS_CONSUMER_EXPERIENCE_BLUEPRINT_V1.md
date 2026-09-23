# VentureGPS Consumer Experience Blueprint V1 — Increment 16

Status: design-only. A Consumer Experience Blueprint, a visual-system specification, a visitor-journey map, and
one interactive, isolated, non-production prototype (`/design/discover`, gated 404 in production builds — see
Section 5). **No production Discover page was built. The existing `/markets/[slug]` page was not modified.**
Not committed, not pushed.

> **Brand.** VentureGPS — *Navigate the Startup Economy.*
> **Mission.** Make the startup economy visible, understandable, and accessible.

---

## 1. Product experience map

### 1.1 The core visitor journey

```
Video/Short/TikTok/link
        │
        ▼
Relevant VentureGPS page      ← today: only /markets/[slug]; tomorrow: a Discover entry, a Story page
        │
        ▼
Understand the story          ← editorial hero: name, what happened, why it matters, honestly caveated
        │
        ▼
Explore market intelligence   ← the interactive Capital chart + Explore section (built, Increment 15)
        │
        ▼
Discover companies/markets    ← today: the market-discovery nav (Increment 15); tomorrow: Companies surface
        │
        ▼
Share a finding               ← today: real Web Share + canonical URL + OG image (Increment 15)
        │
        ▼
Return for new developments   ← NOT YET BUILT: nothing today gives a returning visitor a reason to come back
                                 without a new video link. This is the single biggest gap in the current loop.
```

The journey is only half-built today. Everything from "relevant page" through "share a finding" is real,
working product (the `/markets/[slug]` page). Everything upstream of it (a discovery entry point that doesn't
require already knowing a slug) and downstream of it (a reason to return) does not exist yet. This blueprint
and prototype are about that missing half — not about rebuilding the half that already works.

### 1.2 The four primary surfaces — jobs, and current vs. future status

| Surface | Job | Status today |
|---|---|---|
| **Discover** | The public entry point. Answer "what's interesting right now" for someone with no prior context, in seconds, and hand them off to a specific market. | **Design-only** — this increment's prototype. No production route. |
| **Markets** | Interactive startup-market intelligence: historical comparison, contextual explanation, honest coverage caveats. | **Live** — `/markets/[slug]` (Increment 15/15.1). No index/browse page yet. |
| **Companies** | Evidence-backed startup profiles and financing histories, one company at a time. | **Not started.** No company read API exists (`app/v2/api.py` exposes Markets/Metrics/Signal only — see Section 12's engineering boundaries, which this increment does not cross). |
| **Stories** | Jerrod's videos, shorts, and written market breakdowns, each deep-linked to the market(s) they're about. | **Not started.** No content exists yet; represented in the prototype as explicitly `status: "planned"` placeholders (`components/design/discover/sampleData.ts`). |

### 1.3 Proposed navigation between surfaces

A single persistent four-item bar (`Discover / Markets / Companies / Stories`), reachable from any public
VentureGPS page — the `DiscoverNavConcept.tsx` component in the prototype shows the intended shape, but
deliberately renders **no real links for the surfaces that don't exist yet** (see Section 5.2: "why nothing
outside Discover is a real `<Link>`"). The real header actually in production (`PublicHeader.tsx`) is
untouched by this increment.

---

## 2. Visual identity

### 2.1 Typography and editorial hierarchy

Reuses the app's existing Geist Sans/Mono (`app/layout.tsx`) — no new font is introduced. The market page
(Increment 15.1) already established the right editorial register for VentureGPS: a large, tight-tracked,
bold display headline (`text-4xl`→`text-6xl`, `leading-[1.05]`, `tracking-tight`) for the thing the page is
*about*, a calmer `text-secondary` sentence beneath it, and small-caps-style uppercase eyebrows
(`text-xs font-semibold uppercase tracking-wide`) for section/context labels. The Discover prototype's hero
pushes this further (two-line, larger headline) since it's the flagship entry point; every other section keeps
the market page's already-tuned `text-2xl`/`text-3xl` heading scale so the whole product reads as one system,
not two.

### 2.2 Color palette and light/dark strategy

**No new color tokens.** Every surface in this blueprint (prototype included) is built entirely from the
existing `app/globals.css` token set: `--primary`/`--success`/`--danger`/`--warning`/`--info`/`--text-*`/
`--surface-*`/`--border*`, all of which already carry correct light- and dark-mode values and already respect
the user's system/app theme via the existing `ThemeProvider`. The one deliberate *exception* is the OG image
(`app/markets/[slug]/opengraph-image.tsx`, Increment 15), which is fixed-dark because a social-share image has
no "theme" — that precedent is unchanged and not revisited here.

The Capital Signal tone vocabulary (`DIRECTION_TONE` in `lib/api/v2/signalLabels.ts`: positive/negative/
neutral/mixed/unknown) is the *only* semantic color system this product needs for data — it is reused verbatim
throughout the prototype (`MarketSignalCard.tsx`), never duplicated or reinvented.

### 2.3 Navigation

See Section 1.3. Compact, four items, mobile: `grid-cols-2`; desktop: `grid-cols-4`. Each item states its own
real status in one line rather than pretending to be uniform — this is itself a visual-identity decision: honesty
about what's real is part of the VentureGPS brand, not just a disclaimer bolted on.

### 2.4 Market cards

`MarketSignalCard.tsx` is the proposed card language, replacing the legacy `DiscoveryResultCard.tsx` pattern
(a KPI-grid of six pillar-score numbers per card — reviewed in Phase 1 and explicitly rejected as exactly the
"corporate dashboard" feel Section 3 of the brief asks to avoid). The new card is built around three things,
never more: a direction badge (the one number that matters at a glance), a 9-bar sparkline (echoing
`CapitalChart.tsx`'s real bar-chart visual language at a glance-scale, not a decorative shape), and one
supporting figure. Every card is fully keyboard/focus accessible and carries a visible "Sample" tag in this
prototype specifically (a real, live card would not carry that tag).

### 2.5 Story cards

`BriefSection.tsx`'s list items are the proposed shape: a format chip (Video/Short/Breakdown), a title, and
which market it would deep-link to. Deliberately understated (dashed borders, no hover state, muted text) —
placeholder content should never visually compete with real, live data for a visitor's attention.

### 2.6 Charts

No new charting approach. `CapitalChart.tsx`'s real bar-chart language (Increment 15.1's CSS-height fix) is the
one chart idiom this product needs — the sparkline in `MarketSignalCard.tsx` is a smaller-scale reuse of the
same idea (bars, current period highlighted in solid `--primary`, historical periods in a soft tint), not a
second chart system.

### 2.7 Signal indicators and data-coverage states

`DirectionBadge.tsx` (symbol + label + tone) is reused byte-for-byte from the market page. No new indicator
vocabulary was created. Coverage honesty (a market with no classified companies vs. classified-but-quiet vs.
genuinely insufficient history) is the same three-state distinction `CoverageNote.tsx` already draws on the
real market page — the prototype's Biotech/insufficient-data sample cards exist specifically to force the
Discover-level card design to handle those states gracefully, not just the flattering ones.

### 2.8 Shareable visual language

`ClosingSection.tsx`'s static mock shows the proposed shared-card look: wordmark, market name, one direction
line, the canonical URL. This is intentionally the *same* visual language as the real OG image
(`opengraph-image.tsx`) — dark background, `--primary` wordmark dot, bold market name — so a card seen inside
the product and a card seen shared on social media read as the same brand, not two.

### 2.9 Mobile interaction patterns

Horizontal scroll-snap rails for "browse a set of cards you can't all see at once" (`SignalsRail.tsx`,
`scroll-snap-type: x proximity`) rather than pagination dots or a carousel library — zero new dependencies,
native touch scrolling, works identically with a trackpad on desktop. Tap-to-select-and-reveal-detail
(`SignalsRail.tsx`'s selected-card + detail panel) is the one genuinely new interaction pattern this increment
introduces; it is real React state, not a static mock.

### 2.10 Motion principles

- Only CSS transitions, never a new animation dependency.
- Every transition that isn't purely opacity/color is wrapped or capable of being wrapped in
  `motion-reduce:transition-none` (the exact convention `CapitalChart.tsx` already established).
- No autoplay, no parallax, no scroll-jacking, no decorative looping animation — motion exists only to confirm
  an interaction happened (a card's border/background on selection), never as spectacle.

### 2.11 Accessibility standards

Every interactive element in the prototype is a real, focusable, keyboard-operable control (`<button>`, native
`<details>`) with a visible focus ring (`focus-visible:ring-2 focus-visible:ring-primary`) — the same standard
Increment 15/15.1 already held the market page to. Card grids use semantic headings (`<h2>`/`<h3>`) and `aria-`
labeling consistent with the market page's own conventions. No new accessibility pattern was invented; none was
needed.

---

## 3. Prototype route and interactions

**Route:** `dashboard/app/design/discover/page.tsx`, mounted at `/design/discover`.

**Isolation mechanism:** follows `app/dev/design-system/page.tsx`'s exact, already-established precedent — a
`process.env.NODE_ENV === "production"` check that calls Next's `notFound()`. Verified live (Section 8): the
route returns HTTP 200 under `next dev`/`next start` in a non-production `NODE_ENV`, and HTTP 404 under a real
`next build && next start` (production `NODE_ENV`) — structurally un-deployable, not just unlinked.

**Real interactions in the prototype:**
- `SignalsRail.tsx` — tapping a market card selects it (real `useState`) and updates a detail panel below with
  that market's sample direction explanation.
- Every native `<details>` element (none currently in this specific prototype, but the pattern is available and
  used identically to the real market page elsewhere in the app).
- One real navigation: the hero's "open a real market page" link, which points at the actual, live
  `/markets/robotics` route — intentionally demonstrating that the real page's honest not-found/unavailable
  states are themselves part of the product, not a bug (Section 5.2).

**Everything else is deliberately non-interactive** (`ExploreMarketsSection.tsx`'s grid cards render as plain
`<div>`s, not buttons, when given no `onSelect` — see the comment in `MarketSignalCard.tsx`) rather than dead
controls that look clickable but do nothing.

### 3.1 Why the section hierarchy was simplified from the brief's six suggestions

The brief listed Hero / What's Moving / Explore Markets / Capital Flow / The Brief / Continue Exploring as
**design hypotheses, not a mandate** — and explicitly asked this increment to challenge that hierarchy if a
simpler one would serve a first-time visitor better. It does:

- **"What's Moving" and "Capital Flow" were merged into one section** (`SignalsRail.tsx`, headed "What's
  moving"). Both ask fundamentally the same question — "which markets have something happening, and what does
  the capital picture look like" — and a mobile visitor scrolling past two back-to-back sections making the
  same kind of claim reads as padding, not two distinct ideas. One section, doing both jobs, keeps the page
  shorter and the first-viewport promise ("understand what you're looking at in seconds") more honest.
- **"Continue Exploring" was folded into a short closing block** (`ClosingSection.tsx`) rather than built as a
  full section. "Explore Markets" immediately above it already *is* the "discover more" moment; a second,
  separate "discover more" section directly under it would be a near-duplicate, not a new job.

This is a five-section page (Hero, Signals, Explore Markets, The Brief, Closing), not six — a deliberate,
justified simplification, not an oversight.

---

## 4. Files created and modified

**New (all under `dashboard/components/design/discover/` and `dashboard/app/design/discover/`):**
`sampleData.ts`, `PrototypeBanner.tsx`, `DiscoverNavConcept.tsx`, `MarketSignalCard.tsx`, `HeroFeatured.tsx`,
`SignalsRail.tsx`, `ExploreMarketsSection.tsx`, `BriefSection.tsx`, `ClosingSection.tsx`,
`DiscoverPrototype.tsx`, `app/design/discover/page.tsx`.

**Modified:** `dashboard/components/layout/AppShell.tsx` — one line, adding `"/design"` to the existing
`PUBLIC_ROUTE_PREFIXES` array (Increment 15.1 already introduced this array for `/markets`). Purely additive: a
brand-new route prefix nothing else used, so no existing route's rendered chrome changes at all.

**Untouched:** `app/markets/[slug]/page.tsx` and every component under `components/markets/` — the production
market page and every component it depends on are byte-identical to before this increment. This was verified,
not assumed (Section 8).

**No backend files touched.** No new dependencies added.

---

## 5. Reused components

`DirectionBadge.tsx` and `lib/api/v2/signalLabels.ts` (imported directly from the production `components/markets/`
tree, not copied) are the only production code the prototype depends on — deliberately, to keep the prototype's
data vocabulary identical to the real product's rather than inventing a parallel one that could drift.
`types/v2/capital.ts`'s `CapitalDirection` type grounds `sampleData.ts`'s illustrative content in the real
contract. No `components/discovery/` or `components/home/` (legacy SIE) components were reused — those carry a
KPI-grid/dashboard visual language this blueprint explicitly moves away from (Section 2.4).

---

## 6. Validation against the five questions

Answered honestly, weaknesses included — not claimed successful merely because it renders.

**Does VentureGPS feel distinct from existing financial dashboards?**
Directionally yes: no KPI grid, no dense table, no ticker-style number wall; the market-card language leans on
a badge + sparkline + one number rather than a row of stats. But the prototype is still fundamentally
card-and-list-based — it has not yet proven it can feel as distinctive as, say, a genuinely editorial
long-form layout would. This is a real open question, not a solved one (see Section 9, "requires approval").

**Can a first-time visitor understand what the product offers within seconds?**
The hero states the mission in one headline and one sentence, and the nav concept immediately shows what's
real vs. planned. This is a meaningful improvement over the original Increment 15 hero's density (see
Increment 15.1's own findings). Weakness: with the nav-concept block, banner, AND hero all above the fold on a
short mobile viewport, the actual featured-market card can still land below the first screen on a small phone
(390×700-ish) — worth measuring precisely once real device testing is possible (Section 8's limitation).

**Is there an obvious reason to explore?**
The Signals rail's real tap-to-preview interaction gives an immediate, low-commitment way to sample content.
Weakness: because every number is sample data, the "reason to explore" is itself sample — this genuinely
cannot be validated until real Capital Signal data (or richer real fixtures) replaces the illustrative content.

**Does the experience make it easy to discover and share something interesting?**
The closing section shows the intended shareable-card language, and the hero links to the one real, working
share surface that exists (the market page). Weakness: the prototype itself has no real share action — by
design (Section 3), but it means this question is only partially testable here; the real answer already lives
on the market page from Increment 15.

**Can the design accommodate sparse data without misleading visitors?**
Yes, and this was tested directly: Biotech's `insufficient_data` sample card renders with a flat, honest
sparkline and the same "not enough history yet" vocabulary the real market page uses, in the same card
component used for the market with the richest sample data — the design does not special-case or hide the
sparse case.

---

## 7. Responsive design

Verified with the browser automation tool at its actual rendered width (see Section 8's tooling limitation —
`resize_window` did not visibly change the captured viewport across three attempts in this environment, the
same limitation encountered in Increment 15.1). Layout correctness at 375/390/430/tablet was therefore verified
by construction rather than by a true narrow-viewport screenshot: every section uses `flex-wrap`, `grid-cols-*`
with responsive breakpoints, horizontal scroll (never fixed overflow), and no element in any new file uses a
fixed pixel width without a `min-w-0`/`truncate` companion. This is a real gap, stated plainly rather than
glossed over — a reviewer should check a real phone before treating the responsive behavior as fully proven.

---

## 8. Testing

- `npx tsc --noEmit`: clean.
- `npm run lint`: clean, 0 warnings.
- `npm test`: full existing suite unchanged and passing (no test-relevant logic was added — this increment is
  presentational).
- `npm run build`: succeeds. `/design/discover` compiles as a static (`○`) route, same as `/dev/design-system`.
- **Production-mode isolation, verified live**, not assumed: ran `next start` on a scratch port and confirmed
  `GET /design/discover` → **404**, `GET /dev/design-system` → **404** (existing precedent, unaffected), and
  `GET /markets/robotics` → **200** (the real market page, confirming Section 4's "untouched" claim empirically,
  not just by diff inspection).
- Live visual review via the browser automation tool: hero, nav concept, Signals rail (both selected and
  default states), Explore Markets grid (all six sample directions, including `insufficient_data` and `mixed`),
  The Brief, and the closing section were all screenshotted and visually confirmed correct.
- **Known tooling limitation:** the Signals rail's tap-to-select interaction could not be triggered through the
  browser automation tool in this environment (synthetic clicks did not reach the React `onClick` handler,
  reproducing the same issue found on `CapitalChart.tsx`'s metric tabs in Increment 15.1 — filed as product
  feedback this session). The underlying `useState` selection logic is simple, small, and directly readable in
  `SignalsRail.tsx`; a manual click-through is still recommended.

---

## 9. Design decisions requiring Jerrod's approval

1. **The merged "Signals" section** (Section 3.1) — confirm the What's Moving/Capital Flow merge is the right
   call, not just an expedient one.
2. **The four-surface nav's honesty-over-completeness treatment** (Section 1.3) — confirm showing "Companies"
   and "Stories" as visibly disabled/labeled is the right tone for the real product, vs. omitting them from the
   nav entirely until they're real.
3. **Whether "distinct from financial dashboards" is actually achieved** (Section 6, first question) — this
   blueprint's own honest answer is "directionally, not conclusively." Worth a second opinion before treating
   the card language as final.
4. **`NEXT_PUBLIC_SITE_URL`-dependent share language** — `ClosingSection.tsx`'s mock hardcodes
   `venturegps.com` as the illustrative domain; confirm that's the intended real domain before it appears in
   any real OG copy or documentation.
5. **Whether the prototype's one real link** (hero → `/markets/robotics`) is the right example market to point
   at, or should be replaced with something guaranteed to exist in whatever environment reviews this.

---

## 10. Proposed production implementation sequence

1. **Companies read API + minimal profile page** — the one surface with zero backend today; needed before a
   real Discover page can link anywhere beyond Markets.
2. **`/markets` index** — already flagged as the very next increment in `VENTUREGPS_MARKET_PAGE_V1.md` (Section
   13); becomes the real destination for the nav's "Markets" item.
3. **Production Discover page**, built from this blueprint's validated (Section 9) sections, wired to real data
   — only after 1–2 exist, so "Explore Markets"/"Companies" nav items have somewhere real to go.
4. **Stories/Brief**, once Jerrod's first VentureGPS video content exists to deep-link to.
5. **Real global nav** replacing `PublicHeader.tsx`'s current minimal wordmark-only treatment, once at least two
   of the four surfaces are real.

This sequence follows from what actually exists today (Section 1.2's status table), not from the brief's own
listed order.

---

## Increment 16.1 — High-Fidelity Visual Direction Exploration

Status: three substantially different, high-fidelity, isolated prototypes, each demonstrating a genuinely
different navigational paradigm — not the single Increment 16 prototype re-skinned three ways. **No concept is
selected; nothing is merged.** Not committed, not pushed.

### Routes

- `/design/direction-a` — **Cinematic Editorial.** VentureGPS as a technology publication: full-bleed CSS
  gradient compositions, oversized type, markets presented as vertical "chapters" in a linear editorial scroll.
- `/design/direction-b` — **Interactive Intelligence.** A dark, fixed-theme (`className="dark"`) instrument
  panel: markets as nodes in a spatial constellation (`MarketConstellation.tsx`), tap any node to bring it into
  focus at the center. Genuinely spatial navigation, not a list with different styling.
- `/design/direction-c` — **Social Discovery.** A mobile-native, full-viewport-height vertical story deck
  (CSS `scroll-snap-type: y mandatory`, no gesture library) — one market per slide, swipe/scroll to the next,
  with real jump-dot anchor navigation for desktop/keyboard users.
- `/design/directions` — a plain comparison page linking to all three, with an honest strengths/tradeoffs
  summary per concept and a shared-elements list (reproduced in Section "Shared elements" below).

All four follow the exact `NODE_ENV === "production"` → `notFound()` precedent Increment 16 established (itself
following `/dev/design-system`) — verified live via a real `next build && next start`, not assumed: all four
return **404** in production, while `/markets/robotics` (the real market page) returns **200**, unchanged.

### Root cause avoided: a real bug caught before it shipped

Direction B's constellation initially animated its SVG connecting lines independently of the node buttons they
connect to (a `motion-safe:animate-[spin_...]` on the SVG only) — since the lines and the absolutely-positioned
node buttons are separate DOM elements, this would have slowly rotated the lines out of alignment with their
own nodes over time, a real visual bug, not a stylistic choice. Caught during implementation review (not visual
QA) and replaced with a self-contained pulse ring on the center node instead — motion that confirms "this is the
focused node" without needing to stay synchronized with anything else on screen.

### Files created

`components/design/shared/{IllustrativeTag,PrototypeRibbon,PlaceholderArt}.tsx`,
`components/design/directionA/DirectionA.tsx`, `components/design/directionB/{DirectionB,MarketConstellation}.tsx`,
`components/design/directionC/DirectionC.tsx`, `components/design/directions/DirectionsComparison.tsx`, and
their four `app/design/{direction-a,direction-b,direction-c,directions}/page.tsx` route files. No files modified
outside `dashboard/components/design/` and `dashboard/app/design/` — `AppShell.tsx`'s existing `/design` prefix
(added in Increment 16) already covers every new route; no further change to shared chrome was needed.

### Data honesty

Every concept reuses Increment 16's `sampleData.ts` (`SAMPLE_MARKET_SIGNALS`/`SAMPLE_STORIES`) unchanged — no
new illustrative content model was invented, and the same six markets/three stories appear (differently
composed) in all three directions, so a reviewer comparing them is comparing presentation, not different
underlying data. Every direction carries visible "Illustrative"/"Sample"/"Planned" labeling
(`IllustrativeTag.tsx`), and every "image" is CSS-only gradient art (`PlaceholderArt.tsx`) with a visible
"Prototype placeholder art — not real imagery" caption — no stock photography was sourced or implied to depict
a real company.

### Strengths and tradeoffs (summary — full text on `/design/directions` itself)

| | Strongest at | Weakest at |
|---|---|---|
| **A — Cinematic Editorial** | First-impression "premium publication" feel; natural home for video/editorial content | Longest page to reach all markets; least distinctive *interaction* (still a scroll) |
| **B — Interactive Intelligence** | Most distinctive interaction; whole market set visible/comparable at a glance | Risk of feeling cold/technical to a non-technical visitor; fixed-dark only |
| **C — Social Discovery** | Best fit for the actual TikTok/Shorts/Reels distribution strategy; every slide is a complete first-screen | Hardest to read as "intelligence" vs. "content"; desktop is the most compromised of the three |

### Shared elements — candidates for the final VentureGPS identity, regardless of which direction (or blend) wins

1. The exact `DirectionBadge` symbol/tone/label vocabulary, reused byte-for-byte in all three — never re-skinned
   per direction.
2. Verified-financing-first storytelling — no concept leads with a forecast, a recommendation, or an invented
   trend claim.
3. Visible coverage honesty — every concept renders `insufficient_data`/`mixed` states (Biotech, Quantum
   Computing) without hiding, softening, or explaining them away.
4. Zero new runtime dependencies across all three — every visual effect (constellation, scroll-snap deck,
   gradient art) is CSS/SVG/native browser APIs, reusing the existing design-token system.
5. The same "Illustrative"/"Sample"/"Planned" labeling discipline, applied consistently rather than each
   direction inventing its own disclosure language.

### Responsive verification — reported honestly

Verified live via the browser automation tool across multiple scroll positions on all three directions plus the
comparison page: no horizontal overflow, no unreadable typography, no broken layout observed at any point
captured. However, **the tool's `resize_window` did not reliably produce a confirmed, chosen viewport width in
this environment** (the same limitation noted in Increments 15.1 and 16) — a direct `window.innerWidth` check
mid-session measured **1251×696** (a below-`xl`, above-`lg` width) at one point, and Direction A's chapters
were confirmed rendering in their intended side-by-side `lg:` desktop layout at that width; earlier captures in
the same session showed the intended stacked mobile layout instead, at an unconfirmed narrower width. This
means the deck was verified in both its stacked and side-by-side states, but **not** at the specific, requested
390px and full desktop (≥1280px) widths — stated plainly rather than claimed as fully proven. A manual check on
a real 390px phone and a real desktop browser is still recommended before treating responsive behavior as final.

### Testing

`npx tsc --noEmit`: clean. `npm run lint`: clean, 0 warnings. `npm test`: full existing suite unchanged and
passing (presentational-only increment, no new test-relevant logic). `npm run build`: succeeds, all four new
routes compile as static (`○`) routes. Production-mode 404 gating and the real market page's continued
functioning were both verified live via `next build && next start` (Section "Routes" above), not assumed.

### Decisions requiring Jerrod's approval

No concept is recommended over the others here, per the brief. Three specific things worth a second opinion:
1. Whether any of the three feels close enough to final to become the basis for the next increment as-is, or
   whether elements should be deliberately blended (a future increment's decision, not this one's).
2. Direction B's fixed-dark-only treatment — confirm whether VentureGPS's "Interactive Intelligence" identity
   should ever support light mode, or whether that's an intentional, permanent departure from the rest of the
   app's light/dark parity.
3. Direction C's viewport-height-chrome dependency (noted as its own weakness in the comparison table) — worth
   deciding whether a production version should reduce the fixed chrome above the deck (e.g., an auto-hiding
   banner) rather than living with the current best-effort `min-h-[100svh]` approach.

---

## Increment 16.3.1 — Interaction Bug Fix Investigation

> **Correction (Increment 16.3.2):** this section's root-cause conclusion — browser-automation-extension
> interference, not an application bug — was **wrong**. Jerrod retested in a clean browser with extensions
> disabled and confirmed the failures were real. The actual root cause, the real fix, and a second bug found
> once the first was fixed are documented in the Increment 16.3.2 section below. This section is kept as-written
> for the record of what was investigated and ruled out (most of which was still correct — see 16.3.2's own
> summary of what carried over).

Jerrod's own manual testing found two real interaction failures on `/design/cinematic-homepage`'s Section B:
desktop tile clicks did nothing, and the mobile carousel's prev/next arrows did nothing (manual swipe/scroll
worked). This section records the investigation, root cause, and what was (and wasn't) fixed.

### Investigation, in order

1. **Hydration errors and console warnings** — checked with console tracking started before page load (not
   after, which would miss load-time errors): completely clean, on both the desktop and mobile interaction
   paths, before and after a full dev-server restart.
2. **Client-component boundaries** — both `MarketShowcaseDesktop.tsx` and `MarketCarouselMobile.tsx` already
   had `"use client"`. Ruled out definitively, not just assumed: both use `useState`/`useRef`, and a Server
   Component using either is a **hard Next.js build error**, not a silent degradation — since `npm run build`
   succeeded cleanly every time, the client boundary was never actually in question.
3. **Overlays intercepting pointer events** — checked with `document.elementFromPoint()` at the exact click
   coordinates: the topmost element was always a genuine descendant of the intended button (e.g. the market
   name `<p>` inside the tile), never an invisible sibling overlay. Ruled out.
4. **Incorrect event handlers or disabled states** — re-read line by line; `onClick={onSelect}` /
   `onClick={() => goTo(...)}` are standard, correctly wired, no `stopPropagation` anywhere in the tree.
5. **Stale development-server output** — the dev server had been running continuously for 7+ hours across
   several increments' worth of hot-reloads. Killed it, cleared `.next`, restarted clean, retested in a fresh
   browser tab: **identical failure.** Ruled out.

### Root cause found

With all five suggested shared causes ruled out, a more direct test: a plain `document.createElement('button')`
with a native `addEventListener('click', ...)` (zero React involvement) was injected into the live page and
clicked via the same automated-click mechanism used throughout this investigation — **it worked perfectly**,
confirming clicks genuinely reach the DOM. The same click delivery mechanism, tested against React `onClick`
handlers, failed identically on:
- Section B's new tile/arrow buttons, **and**
- the unrelated, already-shipped `ShareMarketButton` on the real, production `/markets/[slug]` page (Increment
  15) — a component that has existed and presumably worked since before this increment.

A vanilla DOM listener firing correctly while React's synthetic `onClick` fails identically on both brand-new
and long-established, unrelated components is strong evidence of interference with React's own event
delegation in the testing environment used for this investigation (this session's Claude-in-Chrome browser
automation), not a defect in this application's code. This is consistent with, and extends, the click-
registration limitation already filed as product feedback earlier in this project (Increment 15.1/16).

**This does not fully resolve the discrepancy with Jerrod's own manual test report**, and that gap is stated
here rather than argued away: if the same browser-automation extension was active in whatever browser tab
Jerrod used, the same interference would explain his result too; if it was a genuinely separate, extension-free
browser, the cause of what he saw remains open. Section "What still needs manual verification" below is the
honest resolution to that gap.

### What was changed

No behavior was changed (Section 8: "preserve the approved design" — hero, imagery, desktop composition, and
mobile card design are all untouched). The one code change: `selectFeaturedMarket`, `clampCarouselIndex`, and
`indexFromScrollPosition` were extracted from inline logic inside the two client components into
`sectionB/interactionLogic.ts` as pure, dependency-free functions, so the actual computation behind both
interactions is independently unit-tested (`tests/v2SectionBInteraction.test.ts`, 12 tests: featured/others
splitting for every market, the previously-featured market always returning to the tile list, index clamping at
both boundaries and for single-item/empty lists, scroll-position-to-index rounding and overshoot handling).

### What still needs manual verification

The automated tests above prove that **if** a click or tap reaches these functions, the resulting state is
correct — they do not and cannot prove the click reaches them in a real browser, which is the actual open
question. Jerrod should retest with the Claude-in-Chrome extension fully disabled (or in a separate, clean
browser window/profile without it) and confirm:
- Clicking any of the three Section B tiles brings it into the large featured position, with the previously
  featured market returning to the tile list.
- Keyboard activation (Tab to a tile, Enter/Space) does the same.
- The mobile carousel's prev/next arrow buttons move exactly one slide, with correct disabled states at both
  ends, and the active dot stays in sync with both button navigation and manual swipe/scroll.

If the interaction still fails with the extension fully out of the picture, that would newly implicate the
application code after all, and this investigation would need to resume from that fact.

## Increment 16.3.2 — Fix Confirmed Browser Interaction Failures

Jerrod retested in a clean browser with extensions disabled and confirmed: desktop market selection didn't
work, the mobile carousel arrows didn't work, and manual horizontal scrolling did work. This section records
the real root cause (distinct from 16.3.1's wrong conclusion above), the fix, a second bug found once the first
was fixed, and exactly what was and wasn't independently verified.

### Root cause: every click handler in the app was dead, not just Section B's

Re-investigating from scratch (not assuming 16.3.1's conclusion) with a minimal `HydrationProbe` component
(mounted at the very top of the page, completely independent of Section B) showed **"NOT HYDRATED" indefinitely
on every route tested** — the server-rendered HTML looked correct, but React had never finished attaching event
listeners to *anything* on the page. That is exactly what "every onClick does nothing" looks like from the
outside, and it explains why 16.3.1 found a vanilla `addEventListener` button working while every React
`onClick` failed identically, including on an unrelated, already-shipped component: none of that pointed at
Section B specifically, because the failure wasn't in Section B, or in this application's code, at all.

The dev server's own terminal output named the actual cause directly:

```
⚠ Blocked cross-origin request to Next.js dev resource /_next/hmr from "127.0.0.1".
Cross-origin access to Next.js dev resources is blocked by default for safety.
```

Next.js 16's dev server treats `127.0.0.1` and `localhost` as different origins (they're different strings,
even though they resolve to the same machine) and blocks cross-origin access to its own dev-only resources by
default — including the Turbopack `/_next/hmr` endpoint. Reached via `127.0.0.1` (as this whole investigation
did, and very plausibly Jerrod's own manual test did too), that block appears to cascade into hydration never
completing at all. **Fix:** `dashboard/next.config.ts` now sets `allowedDevOrigins: ["127.0.0.1", "localhost"]`
— the exact fix Next's own warning names. Dev-only; no effect on production builds or behavior. Confirmed fixed
directly: `HydrationProbe` turns green, and every interaction below started working once this was applied.

### A second, narrower bug found after hydration was fixed

With hydration fixed, direct testing (see "What was independently verified" below) surfaced a second, real,
unrelated bug: on the mobile carousel, swiping by hand (or any scroll event) synced the active dot to the wrong
slide for every slide but the first two. `handleScroll` computed the active index using the scroll track's
`clientWidth` as the per-slide step, but each slide is deliberately narrower than the track (`w-[85vw]`, so the
next slide peeks in, by design) plus a `gap-4` between them — the real step is smaller than the container's
width. **Fix:** `MarketCarouselMobile.tsx`'s `handleScroll` now measures the real step directly from two
consecutive slides' `offsetLeft` instead of using `clientWidth`. Verified via a real dispatched `scroll` event
through the live component for all four slide positions: the active dot now matches the visible slide at every
position, where it previously desynced from slide 2 onward.

(One other approach was tried and reverted: swapping `goTo`'s `scrollIntoView` for a directly-computed
`scrollTo`, on the theory that `scrollIntoView` interacting with `scroll-snap-type: mandatory` was blocking
multi-slide jumps. That theory was disproven directly — a raw `scrollTo` call, with or without scroll-snap
disabled, failed identically to `scrollIntoView` for a multi-slide jump in the browser-automation tool used for
this investigation, while a single-slide step animated correctly either way. That distinction — single-step
smooth-scroll animations completing, multi-step ones not, specifically in this tool's browser — looks like a
tool/automation-environment limitation, not an application bug; see "What remains unverified" below. The revert
keeps the original `scrollIntoView` code, which is simpler and was not shown to be the problem.)

### What was independently verified

Desktop (real trusted click, dispatched via the browser tool at the actual button's screen coordinates, checked
against the live DOM before/after):
- Clicking a secondary tile features it and returns the previously featured market to the tile list — confirmed
  twice (Robotics → Quantum Computing, then Quantum Computing → the next selection).
- Keyboard activation: these are plain, unmodified `<button>` elements with no custom `onKeyDown` anywhere in
  `MarketShowcaseDesktop.tsx` — confirmed by reading the file, not by dispatching a focused keydown (blocked in
  this pass by an unrelated tool limitation — see below). Native `<button>` Enter/Space activation is standard,
  unmodified browser behavior here.

Mobile (mix of real trusted clicks and, for the scroll-sync fix specifically, a real dispatched `scroll` event
through the live component — see the fix description above):
- Next/previous arrows move exactly one slide.
- Dot clicks select the market whose dot was clicked.
- Disabled arrow states are correct at both ends (previous disabled at slide 0, next disabled at the last
  slide), and a click on a disabled arrow is confirmed to be a genuine no-op.
- Manual/programmatic scrolling updates the active dot correctly at every slide position (the fix above).

Additionally, `tests/v2SectionBBrowserInteraction.test.ts` (new this pass) renders the real
`MarketShowcaseDesktop`/`MarketCarouselMobile` components into a real DOM (via `jsdom` + `react-dom/client`'s
`createRoot` — the same rendering API Next.js itself uses) and dispatches real DOM click events at real,
queried button elements — not calling the pure functions directly. Its own header comment states exactly what
it does and does not prove; see "Verification approach" below for why this was necessary and how it works.

### What remains unverified

The browser-automation tool used for this investigation could not be made to render at a desktop-width
(≥1024px) viewport — `resize_window` changes the OS-level window size but not the actual layout viewport, which
stayed at ~1006px (below the `lg` breakpoint) throughout, in every tab tried. The desktop click-to-feature
interaction was confirmed by dispatching a real click directly at the desktop grid's `<button>` DOM node (this
does work correctly, and is a genuine click reaching a genuine handler), but was **not** confirmed by clicking a
visually-rendered, on-screen desktop tile the way a real user at a real desktop width would. Jerrod's own manual
test at a real desktop width is the remaining confirmation needed here.

Separately, the smooth-scroll *animation* itself for a multi-slide dot jump (e.g. dot 1 straight to dot 4) could
not be confirmed to visually animate in this tool's browser — the underlying state update and final DOM output
are proven correct (see above), but whether the animation itself plays smoothly for a real user jumping several
slides at once needs Jerrod's own confirmation. Single-slide steps (arrows, and a dot one slide away) were
confirmed to animate correctly.

### Verification approach: why a second test file was needed

`tests/v2SectionBInteraction.test.ts` (12 tests, from 16.3.1) proves the pure functions
(`selectFeaturedMarket`/`clampCarouselIndex`/`indexFromScrollPosition`) are correct in isolation — it does not
and cannot prove a click in a real browser actually reaches them, which was the entire point in question this
pass. `tests/v2SectionBBrowserInteraction.test.ts` (8 tests, new this pass) closes that gap: it renders the
real component files into a real DOM and dispatches real events, using a small Node module loader
(`tests/support/tsxLoader.mjs`) that transpiles JSX via the `typescript` package already in the repo's
devDependencies (no new transform tool) and stubs `next/image`/`next/link` (the two things that need the full
Next.js app runtime to render correctly outside of it). `jsdom` was added as a devDependency for this — the
repo's existing convention against adding libraries has applied to animation/carousel libraries in product
code; a DOM-testing library is a different category, and there was no way to satisfy "renders the actual
Section B component and dispatches real user interactions" without one. Its own header comment states plainly
what it proves and what it can't (no real layout engine, so it can't exercise the scroll-position-math fix
above or simulate a real browser's native keyboard-to-click translation on `<button>` — both handled by real
in-browser or by-inspection verification instead, as described above).

### What was and wasn't changed

Fixed: `dashboard/next.config.ts` (`allowedDevOrigins`, the real root cause), `MarketCarouselMobile.tsx`'s
`handleScroll` (the scroll-sync divisor bug). All temporary diagnostic code added during the investigation
(a `HydrationProbe` component and its two mount sites, `console.log`/diagnostic `useEffect` calls in both
Section B client components) was removed once the fix was confirmed. No visual/design changes — the approved
composition, imagery, and layout are untouched.
