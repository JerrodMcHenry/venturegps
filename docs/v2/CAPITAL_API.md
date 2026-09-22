# VentureGPS V2 Capital Intelligence API

Read-only HTTP access to the Capital vertical built in Increments 10–13: canonical FinancingEvents, primary
Market classification, Capital Metrics and Capital Signal. Mounted at `/api/v2` on the existing FastAPI
application (`app/api.py`), alongside the legacy V1 routes, which are unaffected.

For what these numbers *mean* — the methodology itself — see `docs/v2/CAPITAL_METHODOLOGY.md`. This document is
the HTTP contract only.

## Public and read-only

Every endpoint here is a public market-intelligence read: no Clerk authentication is required, matching the
existing app's own public endpoints (`/discover`, `/rankings`). No request to this API can create, change or
delete any canonical record — there is no write path reachable from it at all (enforced by an architecture test,
`app/v2/tests/architecture/test_capital_api_boundaries.py`).

## Endpoints

### `GET /api/v2/markets`

List registered Markets, or resolve one by slug.

| Query param | Type | Default | Notes |
|---|---|---|---|
| `limit` | int | 50 | 1–200. Ignored when `slug` is set. |
| `offset` | int | 0 | ≥ 0. Ignored when `slug` is set. |
| `slug` | string | — | Increment 15: exact slug lookup (e.g. a public `/markets/{slug}` page resolving its Market's UUID). Returns at most one market; an unknown slug returns `{"markets": [], "total": 0}`, never a 404 — this endpoint always lists, it never asserts a specific market must exist (use `GET /markets/{market_id}` for that). |

```json
{
  "markets": [{"id": "b3f4...", "slug": "robotics", "display_name": "Robotics"}],
  "limit": 50, "offset": 0, "total": 1
}
```

### `GET /api/v2/markets/{market_id}`

```json
{"id": "b3f4...", "slug": "robotics", "display_name": "Robotics", "taxonomy_versions": ["venturegps_taxonomy.v1"]}
```

`taxonomy_versions` lists every taxonomy version registered **system-wide** — not scoped to this Market. A
taxonomy version applies to any Market; the Metrics/Signal endpoints report honestly whether this Market
actually has classified companies under a given version (see Coverage, below).

### `GET /api/v2/markets/{market_id}/capital/metrics`

| Query param | Required | Notes |
|---|---|---|
| `taxonomy_version` | yes | e.g. `venturegps_taxonomy.v1` |
| `start_date` | yes | ISO date, period start (**inclusive**) |
| `end_date` | yes | ISO date, period end (**exclusive**); must be strictly after `start_date` |

```json
{
  "market": {"id": "b3f4...", "slug": "robotics", "display_name": "Robotics"},
  "taxonomy_version": "venturegps_taxonomy.v1",
  "period": {"start": "2026-01-01T00:00:00Z", "end": "2027-01-01T00:00:00Z"},
  "financing_activity": 3,
  "companies_funded": 2,
  "capital_deployed": [{"currency_code": "USD", "minor_units": "2500000000"}],
  "capital_concentration": [{"currency_code": "USD", "largest_minor_units": "2000000000", "total_minor_units": "2500000000"}],
  "stage_distribution": {"pre_seed": 0, "seed": 1, "series_a": 1, "series_b": 0, "growth": 0, "unknown": 1},
  "diagnostics": {
    "events_considered": 4, "events_included": 3, "events_excluded_missing_date": 1, "events_excluded_outside_period": 0,
    "events_without_verified_amount": 1, "events_without_known_stage": 1, "classified_company_count": 2
  },
  "methodology": {"methodology_version": "capital_metrics.v1", "date_policy": "...", "attribution_policy": "...", "verified_amount_policy": "...", "currency_policy": "..."}
}
```

### `GET /api/v2/markets/{market_id}/capital/signal`

| Query param | Required | Notes |
|---|---|---|
| `taxonomy_version` | yes | e.g. `venturegps_taxonomy.v1` |
| `as_of` | yes | ISO date; the current 30-day window ends here (interpreted as UTC midnight) |

```json
{
  "market": {"id": "b3f4...", "slug": "robotics", "display_name": "Robotics"},
  "taxonomy_version": "venturegps_taxonomy.v1",
  "as_of": "2026-09-21T00:00:00Z",
  "methodology_version": "capital_signal.v1",
  "current_window": {"start": "2026-08-22T00:00:00Z", "end": "2026-09-21T00:00:00Z", "metrics": { "...same shape as the Metrics body..." }},
  "historical_windows": [ { "start": "...", "end": "...", "metrics": {"..."} }, "... x8, oldest first" ],
  "financing_activity": {
    "metric": "financing_activity", "currency_code": null, "current_value": "3",
    "historical_values": ["2", "2", "1", "0", "3", "1", "2", "2"], "historical_nonzero_windows": 7,
    "percentile_rank": {"numerator": "3", "denominator": "8"}, "direction": "increase", "votes": true
  },
  "companies_funded": { "...same shape..." },
  "capital_deployed": [ { "...same shape, one entry per currency, currency_code set..." } ],
  "capital_concentration": [
    {"currency_code": "USD", "current_share": {"numerator": "4", "denominator": "5"},
     "historical_shares": [{"numerator": "1", "denominator": "2"}, null, "... x8"], "trend": "more_concentrated"}
  ],
  "overall": "increase",
  "methodology": {"methodology_version": "capital_signal.v1", "...": "...", "limitations": "..."}
}
```

## Exact number formats — read this before writing a client

- **Every count and every currency amount** (`current_value`, `historical_values`, `minor_units`,
  `largest_minor_units`, `total_minor_units`) is a **JSON string**, never a JSON number, even for a small count.
  This is one uniform rule, not a per-field decision the client has to remember — parse every one of these
  fields as a big integer / `BigInt` / `Decimal`, never `Number()`/`parseFloat`.
- **`{"numerator": "...", "denominator": "..."}`** is an exact `fractions.Fraction`, never a rounded decimal.
  Both fields are strings for the same reason as above. A client wanting a display percentage computes
  `numerator / denominator` itself, with whatever precision it needs — the API never pre-rounds it.
- **Money is currency-scoped, never summed.** `capital_deployed` is a **list**, one entry per currency that had
  verified capital; there is no combined total. Two different currencies are never added together anywhere in
  this API (no FX).
- **Dates/timestamps** are ISO 8601 (`...Z` UTC). UUIDs serialize as their canonical hyphenated string form.
- **`stage_distribution`** always lists all six canonical stages (`pre_seed`, `seed`, `series_a`, `series_b`,
  `growth`, `unknown`), zero-filled — a client never has to guess whether a missing key means zero or means the
  field was omitted.
- The API is **deterministic**: identical canonical data and identical request parameters always produce
  identical JSON.

## Frontend consumption notes

- Treat `direction`/`overall`/`trend` as opaque enum strings from a **fixed, versioned vocabulary**
  (`strong_increase | increase | stable | decrease | strong_decrease | insufficient_data | mixed` for Capital
  Signal direction; a separate `more_concentrated | less_concentrated | stable | insufficient_data` vocabulary
  for concentration `trend` — never render these two vocabularies as if they were the same scale). Render them,
  do not reinterpret them.
- `insufficient_data` and `stable` are **not the same thing** — see Coverage below. Never collapse one into the
  other in the UI.
- `capital_deployed`/`capital_concentration`/`capital_deployed` inside `financing_activity`/`companies_funded`'s
  siblings are **lists that can be empty** (no currency had qualifying activity) — never assume at least one
  entry.
- `percentile_rank`/`current_share` can be `null` — render that as "not enough history," never as zero.

## Coverage and honesty

**An empty or zero-valued response never means "verified zero real-world activity."** It can mean:

| Observation | What it actually tells you |
|---|---|
| `financing_activity == 0` and `diagnostics.classified_company_count == 0` | No Company is even classified into this Market yet under this taxonomy version. There is no basis to say anything about this Market's activity. |
| `financing_activity == 0` and `classified_company_count > 0` | Companies are classified here, but none had a qualifying financing in this exact period. This could be genuine quiet, or incomplete source coverage — the API does not and cannot distinguish those from Postgres row counts alone. |
| `diagnostics.events_excluded_missing_date > 0` | Canonical financings exist for this Market/period but had no usable date and are excluded, never fabricated. |
| `diagnostics.events_without_verified_amount > 0` | Canonical financings count toward `financing_activity` but contributed nothing to `capital_deployed` — they have no accepted verified amount. |
| Capital Signal component `direction == "insufficient_data"` | Fewer than 3 of the last 8 historical 30-day windows had any activity for that specific metric — there is not enough history to say `stable` (which means "ordinary," not "unknown"). |

This API never invents a coverage percentage, a completeness estimate, or a confidence score. Every number
above is a real, deterministic count from canonical data — nothing is estimated.

## Error behavior

| Status | Meaning |
|---|---|
| 404 | The Market or the taxonomy version does not exist. |
| 400 | `start_date` is not strictly before `end_date`. |
| 422 | Structural query validation failed (malformed UUID, malformed date, malformed `taxonomy_version` pattern, missing required parameter, out-of-range `limit`/`offset`). |
| 503 | The database is unreachable. The response never includes a hostname, credential, table name or stack trace. |
| 500 | An unexpected internal error. Logged server-side (and to Sentry, when configured); the response body never includes exception text. |

No response body from this API ever contains a database URL, a credential, a raw SQL statement or a Python
traceback.

## Methodology references

- `docs/v2/CAPITAL_METHODOLOGY.md` — the full Capital Signal methodology (window policy, minimum history,
  percentile-rank comparison, concentration's non-voting status, `mixed`/`insufficient_data` semantics).
- Every response also carries its own `methodology`/`methodology_version` block, so a consumer never has to look
  anything up out-of-band to know which rules produced a given number.
