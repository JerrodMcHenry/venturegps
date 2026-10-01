# Screenshot / Demo Asset Checklist

No screenshots are currently committed to this repository as portfolio assets (`dashboard/public/design-
references/` holds early visual-direction mockups, not real product screenshots, and is unrelated to this
checklist). This is a checklist of what to capture, not manufactured images — every item below should be a
real screenshot of the live application, not a mockup.

**Source already available, no new analysis needed:** the production smoke test
(`docs/validation/EVIDENCE_V1_PRODUCTION_SMOKE_001.md`) already produced and persisted a real analysis —
`https://app.venturegps.ai/evidence/3d7f9b043f7f44788e4507c4ee1d36c9` (Notion). Reloading this URL costs
nothing and re-runs no pipeline, so most of the items below can be captured from it directly at any time,
without a new paid analysis.

| # | Asset | Where to capture it | Notes |
|---|---|---|---|
| 1 | Analyze page (with the "evidence-first (beta)" checkbox visible) | `app.venturegps.ai/analyze`, authenticated | Shows the discoverability checkbox and the narrower (website-only) input shape |
| 2 | Loading state | Mid-submission, if running a live demo | Shows the honest, non-fake-progress stage copy — do not trigger this solely to screenshot it; capture it naturally if a demo is already running |
| 3 | Report overview | The existing persisted Notion report | Evidence Coverage / Confidence / Pillars Assessed header, no overall score |
| 4 | A published pillar | Same report — "Product & Technology" (the one published pillar in the existing record) | Shows a real scored dimension (e.g. "8.0 / 10") alongside an unscored one |
| 5 | A withheld pillar | Same report — any of the five withheld pillars | Shows the "Assessment withheld… not a negative assessment" disclosure — the single most important screenshot for explaining the architecture |
| 6 | Evidence disclosure | Same report, "All evidence" expanded | Shows real excerpts with publisher, source type, and "View source" links |
| 7 | My Analyses | `app.venturegps.ai/my-analyses`, authenticated | Shows the "Evidence-based" badge distinct from legacy numeric-score rows |
| 8 | Architecture diagram | Rendered Mermaid diagram from `docs/portfolio/EVIDENCE_ENGINE_V1_ARCHITECTURE.md` §1–2 | Render via any Mermaid-compatible viewer (GitHub renders it natively) rather than a screenshot of raw source |

## What to never include in a captured screenshot

- The real signed-in user's email address or avatar (crop or obscure the account menu)
- Any bearer token, cookie value, or `Authorization` header (never visible in normal UI use, but be
  deliberate if DevTools is open in the shot)
- Environment variable values, `.env` contents, or any Render/Vercel dashboard configuration screen
- Internal database ids beyond the one public analysis id already referenced in committed validation docs
  (e.g. never screenshot a `render psql` session or raw `owner_user_id` value)
- Production database connection strings or dashboard URLs
