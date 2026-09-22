# VentureGPS Capital Methodology

This is the product-facing methodology for the Capital vertical: what each measurement means, what it does
**not** mean, and exactly how it is computed. It is meant to be readable without reading the code. The
implementation lives in `app/v2/domain/capital_metrics.py` (Increment 12) and `app/v2/domain/capital_signal.py`
(Increment 13); the database schema is documented per-revision in `docs/v2/DATABASE_MIGRATIONS.md`.

No AI participates in anything described in this document. Every number here is either a direct count/sum from
canonical data or a deterministic function of one.

## 1. What Capital Signal is, and is not

**Capital Signal measures how current observable financing activity in a VentureGPS Market compares to that
same Market's own recent history.**

It is **not**:
- a judgement of startup quality,
- a statement about market attractiveness,
- an investment recommendation,
- a prediction of what will happen next,
- a valuation,
- a probability of success,
- a comparison between two different Markets (a Market is only ever compared against itself).

## 2. The measurement pipeline

```
Canonical Company
    -> versioned Company/Market classification (primary only; Increment 12)
    -> canonical FinancingEvent
    -> Capital Metrics (one snapshot per time window; Increment 12)
    -> Capital Signal (current window vs. the Market's own 8-window history; Increment 13)
```

Every stage above Capital Metrics is a fixed, deterministic function of canonical data. Capital Signal never
recomputes attribution, verified-amount handling, stage handling, date policy or currency policy — it calls the
same Capital Metrics engine once per time window and compares the results.

## 3. Capital Metrics (one window)

For a Market, a taxonomy version and a `[period_start, period_end)` window, Capital Metrics reports:

- **Financing Activity** — count of qualifying canonical FinancingEvents (one canonical event counts once, no
  matter how many candidates or sources support it).
- **Companies Funded** — count of *distinct* Companies among those events.
- **Capital Deployed, by currency** — sum of `verified_round_amount` only (never `offering_amount`,
  `amount_sold` or an unaccepted `announced_round_amount`), never combined across currencies (no FX).
- **Capital Concentration, by currency** — the largest single financing's share of that currency's deployed
  total, kept exact.
- **Stage Distribution** — counts by canonical accepted stage, including `unknown`.

A FinancingEvent qualifies for a window when: it is canonical, its Company holds a **primary** classification
into the Market under the requested taxonomy version, and it has a usable canonical date inside the window (see
§5). It does not need a known amount, stage or type — those may be absent and it still counts as activity.

## 4. Capital Signal: the current window and the historical baseline

**Current window.** A trailing 30-day, half-open window ending at an explicit `as_of` instant:
`[as_of − 30d, as_of)`. `as_of` is always supplied by the caller; nothing in the engine reads a wall clock, so
the same `as_of` always produces the same window.

**Historical baseline.** Exactly **8** prior windows of the same 30-day duration, immediately preceding the
current window, with no gap and no overlap:

```
H8              H7      ...      H2      H1      Current
[as_of-270d,    ...                     [as_of-60d,  [as_of-30d,
 as_of-240d)                             as_of-30d)    as_of)
```

No historical window can ever reach the current window's start, so no historical window can ever contain data
the current window also covers, and none can contain data on or after `as_of`. A Market is always compared
against its own history — never against another Market.

## 5. Financing date used for windowing

A canonical FinancingEvent may carry up to three semantic dates. The one used to place it in a window is chosen
by a fixed precedence, never averaged or invented:

1. **`announcement_date`** — the most durable public signal that a financing occurred, and roughly when.
2. **`first_sale_date`** — the most legally precise date when it exists, but Form D filings lag or are absent
   for many rounds and are not always canonically accepted.
3. **`filing_date`** — administrative/regulatory; used only as a last resort.

`Observation.observed_time` — when VentureGPS's collector happened to see the evidence — is **never** used as a
financing date. A FinancingEvent with none of the three canonical dates has no usable date and is excluded from
every period-based metric; this exclusion is visible in the diagnostics, never silently dropped.

## 6. Minimum history: telling "quiet" apart from "unknown"

A Market with one historical financing has no meaningful baseline. But a Market that genuinely sees very little
activity is still legitimate data — a sequence like `0, 0, 1, 0, 0, 1, 0, 0` is real, not missing.

The two are told apart like this:

- **8 windows is fixed structural coverage.** The engine always looks at exactly 8 historical windows,
  regardless of what is in them.
- **Within those 8 windows, a metric is only trusted for comparison if at least 3 of them are non-zero for that
  metric** (`MIN_HISTORICAL_NONZERO_WINDOWS = 3`). Fewer than 3 real observations makes an 8-bucket distribution
  too degenerate to characterize what is "typical" — a single non-zero window among seven zeros would trivially
  rank as an all-time high on the strength of one data point.

When a metric does not meet this bar, its result is `insufficient_data` — never silently downgraded to
`stable`. **`stable` means there is enough evidence, and current activity is historically ordinary.**
`insufficient_data` means there is not yet enough evidence to say either way.

## 7. The comparison method: percentile rank

Each component's current value is compared to its own 8 historical values by **percentile rank** — the
fraction of historical windows the current value stands at or above, using the standard mean-rank rule for ties:

```
percentile_rank = (windows strictly below current  +  windows tied with current / 2)  /  8
```

Computed exactly with `fractions.Fraction` — never a float, never rounded.

**Why percentile rank**, over a mean/standard-deviation approach or a fixed growth-rate threshold (e.g. "+10% =
increase"):

- **Robust to outliers by construction.** A single $250M historical round only shifts where it sits in the
  *ordering*; it cannot distort the *scale* of comparison the way a mean or standard deviation would.
- **No distributional assumption.** It makes no claim that financing activity is normally distributed, which
  startup data manifestly is not.
- **Degrades gracefully on zero-variance history.** If every historical window has the same value, a current
  value equal to it lands exactly at the midpoint (stable); this never produces a divide-by-zero.
- **Directly explainable.** "Current financing activity stands above N out of the last 8 windows" *is* the
  percentile rank — there is no separate translation step, and no arbitrary percentage was invented.
- **Works identically for counts and money.** Financing Activity, Companies Funded and Capital Deployed (in
  minor currency units) are all just orderable integers to this method.

**Direction bands** (symmetric, chosen for round explainability, not tuned to any particular market):

| Percentile rank | Direction |
|---|---|
| ≥ 9/10 | `strong_increase` |
| [7/10, 9/10) | `increase` |
| [3/10, 7/10) | `stable` |
| [1/10, 3/10) | `decrease` |
| < 1/10 | `strong_decrease` |

## 8. Components and their treatment

Three components **vote** in the overall Capital Signal:

- **Financing Activity** (one component)
- **Companies Funded** (one component)
- **Capital Deployed** — **one component per currency** observed in the current or historical windows.
  A currency with insufficient history never fabricates a direction and never blocks the others; currencies are
  never combined.

**Capital Concentration is contextual only and never votes.** A rise in concentration means capital became more
concentrated among fewer, larger financings — it is not itself "positive" Capital activity, and a fall is not
"negative." Because conflating the two axes would be actively misleading, concentration uses a completely
separate vocabulary (`more_concentrated` / `less_concentrated` / `stable` / `insufficient_data`), which cannot
be confused with the Capital Signal direction vocabulary even by accident.

**Stage Distribution** remains visible context on every Capital Metrics window but does not vote on the overall
signal: it describes *what kind* of financing occurred, not *how much* changed.

## 9. Overall Capital Signal: agreement, not a weighted average

The overall signal is derived from the voting components by explicit agreement rules — **never** a weighted
average, so one very large number can never buy its way to a strong verdict on its own.

1. Components with `insufficient_data` do not vote. If **none** of the voting components has a direction, the
   overall signal is `insufficient_data`.
2. If the voting components that *do* have a direction include both an "up" (`increase`/`strong_increase`) and
   a "down" (`decrease`/`strong_decrease`), the overall signal is **`mixed`** — a genuine disagreement, never
   forced into a single fake answer.
3. If every voting component points up: the overall signal is `strong_increase` **only if every single voting
   component is itself `strong_increase`** (unanimous strong agreement); otherwise it is `increase`.
   Symmetrically for `strong_decrease` / `decrease`.
4. If every voting component is `stable` (none up, none down), the overall signal is `stable`.

**Consequence, worked example:** a single giant financing round can make Capital Deployed (USD)
`strong_increase` on its own, but if Financing Activity and Companies Funded are merely `stable`, the overall
signal is `increase`, not `strong_increase` — the unanimity requirement is not met. If Financing Activity and
Companies Funded are actually declining, the overall signal becomes `mixed`, not `increase`: a lone large round
never overrides a broader downturn.

## 10. `mixed` vs. `stable` vs. `insufficient_data`

These three are permanently distinct and never interchangeable:

- **`stable`** — there is enough evidence (every voting component met the minimum-history bar), and the Market's
  current position is historically ordinary.
- **`mixed`** — there is enough evidence, but important Capital dimensions genuinely disagree (some up, some
  down).
- **`insufficient_data`** — there is not enough historical evidence to say anything at all.

## 11. Methodology version

The methodology described here is `capital_signal.v1`. Every `CapitalSignal` result carries its
`methodology_version`. A future change to any rule above (window duration, minimum history, comparison method,
direction bands, aggregation logic) must introduce `capital_signal.v2` and compute under that new identifier —
it must never silently reinterpret what a `capital_signal.v1` result meant.

## 12. What comes next (not in this increment)

Capital Signal is one input to a future, separate **Market Pulse**, which will combine Capital with Formation,
Talent, Innovation and Attention signals. Historical Capital Signal snapshots are not persisted yet; every
`CapitalSignal` is computed on demand from canonical data. Neither exists yet, and nothing here anticipates
their shape.
