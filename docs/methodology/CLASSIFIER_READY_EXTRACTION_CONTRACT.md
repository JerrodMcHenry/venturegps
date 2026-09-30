# Classifier-Ready Structured Evidence Extraction Contract

**Task 27.** This document is the canonical reference for `app/evidence_engine/acquisition/
fact_contracts.py` — the one place every fact kind's required fields, categorical vocabulary, and
downstream deterministic consumer are named, derived directly from re-reading each pillar's own
classifier/parser code, never inferred from documentation or from what "seems reasonable."

## 1. The problem this closes

`docs/methodology/LIVE_EVALUATION_COHORT_001.md` §7's Finding S1, confirmed across five real live
runs (Linear ×2, Stripe, Notion, Fish Audio): structured facts were increasingly **grounded**
(genuinely supported by their excerpt), **typed** (a real, recognized `kind`), and, after Task 25,
correctly **routed** (reaching an eligible dimension) — and *still* could not score, because the
fact's own field **values** did not match the exact vocabulary/shape each dimension's real classifier
requires. Concrete, cited examples:

- `metric` populated as `"annual revenue"` instead of the recognized `"revenue"`.
- `value_type` never populated at all (required to literally equal `"actual"`).
- `financing_type` populated with the round **label** (`"Seed"`) instead of the legal financing
  **structure** (`"equity"`) — two different concepts the model was conflating into one field.
- `founding_year`'s value populated under the key `"amount"` instead of the `"value"` key
  `stage.py::determine_stage()` actually reads — a mismatch that recurred independently across
  Linear 002, Notion, and Fish Audio.
- Categorical `value` fields (`founder_experience`, `track_record`, `retention_signal`,
  `capital_efficiency_signal`) correctly typed and routed, but simply never populated.

This is **one unifying root cause, not five separate bugs**: the extraction prompt asked for
descriptive fields (amount, named_entity, period_date) the model reliably populates, without clearly
enough distinguishing the small set of **categorical** fields each classifier gates on by exact
string equality.

## 2. Two distinct measurements — do not conflate them

- **`structured_fact` population** (already measured by prior tasks): did the model attach *any*
  typed fact to the claim at all? The cohort's rate here was already high.
- **Classifier readiness** (this task's new measurement, `check_classifier_readiness()`): does that
  fact's own field values actually satisfy its kind's real downstream consumer? The cohort's rate
  here was the gap — Finding S1's whole point.

`classifier_ready_claims / accepted_claims_with_relevant_fact_kind` (item 14) is reported
**separately** from raw structured-fact population precisely because a claim can score 100% on the
first measurement and 0% on the second, exactly as the cohort did.

## 3. One canonical place, not five (or twenty) scattered ones

`fact_contracts.py` centralizes all 20 fact kinds' contracts in one module — a deliberate scale
decision, not a departure from Task 25's own principle ("derive from real code, reuse rather than
re-derive"). Task 25 added one small `*_fields_are_sufficient()` function per pillar file for the 3
kinds LINEAR_002 evidenced a problem for; extending that same pattern to all 15 additional kind-gated
kinds would mean five pillar files each growing a handful of new, related-but-scattered functions.
One well-organized module, reusing Task 25's own three functions directly rather than re-deriving
them, is more maintainable at this scale. Every categorical vocabulary a classifier checks by exact
string equality is named **once**, as a real Python `Enum`, cited to the exact classifier line it
mirrors.

## 4. Schema-level vs. deterministic-only enforcement — the documented tradeoff (item 10)

Two kinds of fields exist in `_StructuredFactSchema` (`providers_live.py`):

- **Fields that mean exactly one thing regardless of `kind`** — `financing_type`, `value_type` — are
  real, OpenAI-structured-output-enforced Pydantic `Enum`s. The model cannot even *propose* an
  out-of-vocabulary value for these; the API itself rejects it.
- **Fields used by multiple kinds with different, kind-specific vocabularies under the same name** —
  `value` (`customer_band.value` means SMALL/MODERATE/LARGE; `founder_experience.value` means
  ADJACENT/DIRECT; `capital_efficiency_signal.value` and `retention_signal.value` both mean
  WEAK/MODERATE/STRONG but for different dimensions), `metric`, `status` — deliberately stay
  `str | None` at the schema level. OpenAI's structured-output schema has no built-in way to make one
  field's enum depend on a **sibling field's own value** without a full discriminated-union schema per
  kind — judged, for this task, a materially larger and harder-to-maintain change than the value it
  would add, given the deterministic check one step later in the pipeline (`routing.py`'s existing
  applicability mechanism, Task 25) already enforces the *right* vocabulary just as strictly, reading
  `kind` first. This is the "smallest maintainable typed design" tradeoff item 10 explicitly asks to be
  documented, not an oversight.

## 5. The funding contract — financing-event-type vs. round/stage-label (item 4)

Two genuinely different facts, two different kinds, never conflated into one:

| | `funding_round` | `funding_round_type` |
|---|---|---|
| **What it means** | A financing EVENT: legal structure + amount raised | A STAGE/ROUND LABEL signal for `stage.py` |
| **Consumer** | `funding_history` (`financial_funding.py::funding_round_fields_are_sufficient`) | `stage_signal` (`stage.py::funding_round_type_fields_are_sufficient` / `map_round_type()`) |
| **Required fields** | `financing_type`, `status`, `currency`, `amount`, `round_date` | `value` |
| **`financing_type`'s real vocabulary** | `equity` \| `debt` \| `grant` \| `secondary` \| `tender_offer` — the **legal structure** | n/a |
| **`value`'s real shape** | n/a | free text, keyword-matched by `map_round_type()` (e.g. `"Series C"`, `"seed round"`) — not a strict enum, since the real consumer is substring-based |

Since `ExtractedClaimCandidate.structured_fact` is a single dict (one kind per candidate), a source
stating **both** an amount and a round label (e.g. "$52M Series B") requires the model to propose
**two separate candidates** from the same excerpt — this is now explicit extraction-prompt guidance
(§6 below), directly targeting the cohort's own Fish Audio finding (`financing_type="Seed"`).

Only `financing_type == "equity"` is ever counted toward Funding History
(`parameters.py::FUNDING_HISTORY_COUNTED_FINANCING_TYPES = {"equity"}`) — debt, grants, secondaries,
and tender offers are real, legitimately representable financing types this engine's own `Claim`
model retains, just never summed by this one dimension (unchanged Task 17 methodology).

## 6. The metric contract (item 5)

`traction_metric` (`commercial_traction.py::_parse_scale_point()`) requires:

- `metric` ∈ `{revenue, arr, gmv, bookings, active_users, paying_customers}` exactly — never a
  paraphrase.
- `value_type == "actual"` literally — `"projection"` is a real, representable, never-scored state.
- `amount` parseable as a bare `float()` — `"400 million"` does not parse; `"400000000"` does.
- `currency == "USD"` **only when** `metric` is a money metric (revenue/arr/gmv/bookings) — ignored
  for count metrics (active_users/paying_customers), mirroring `_parse_scale_point()`'s own exact
  branching (the one cross-field condition `fact_contracts.py::_generic_sufficiency_check()` special-
  cases explicitly, since the declarative per-field loop cannot express it).

## 7. The team contract (item 6) — preserving Tasks 23-25's identity behavior, never encoding prestige

- `team_identity` is **context-only** (`context_only=True` — never itself a scored dimension). It
  feeds `pillars/team_leadership.py::_confirmed_person_ids()`, which gates
  `founder_relevant_experience` (role must equal `"founder"` exactly) and `public_track_record` (any
  role admits). A realistic extracted role string like `"Co-Founder and CEO"` will never exactly equal
  `"founder"` — a real, confirmed, documented gap (§9 below), not silently normalized here, since doing
  so would be a methodology-adjacent change this task does not make.
- `founder_experience.value` ∈ `{ADJACENT, DIRECT}` — never a judgment of the prior employer's
  prestige. `named_entity` records **where**; `value` records **whether** that experience is relevant
  to the current company's domain — never a quality judgment of the institution itself.
- `track_record.value` ∈ `{PRIOR_EXIT, PRIOR_VENTURE_ROLE}` — a prior company that was
  acquired/IPO'd, or any other prior venture-backed role.
- `leadership_hire` / `founders_only_confirmed` require no fields beyond `kind` — presence and
  independence-group counting is the entire signal (`WellBehavedLeadershipCompositionClassifier`).

## 8. The retention/renewal contract (item 7) — preserving "unscored without real evidence"

`retention_signal.value` ∈ `{WEAK, MODERATE, STRONG}`. Never inferred from, and no code path in this
engine that could ever populate this kind from: customer logos, customer counts, testimonials,
general adoption claims, or company longevity — the classifier reads only
`structured_fact.kind == "retention_signal"`, which nothing else in this pillar ever produces. Same
exclusion list, same reasoning, for `capital_efficiency_signal` (never inferred from company age,
funding amount, headcount, revenue, customer count, or valuation).

## 9. The product/release contract (item 8) — preserving announced ≠ shipped

`product_release.status` ∈ `{announced, launched, beta, delayed, cancelled}` — a real, structured-
output-enforced enum (`ProductReleaseStatus`). Only `status == "launched"` ever counts toward
Shipping Velocity (`execution_momentum.py::_launched_releases()`); the other four values are real,
legitimately representable states this engine's own supersession logic
(`_resolve_current_release_status()`) depends on being able to see — never silently upgraded to
`"launched"`.

## 10. The market contract (item 9) — inspected, not fixed

`market_size_usd` and `category_growth_rate_pct` each require a bare numeric `value`, parseable as
`float()`, from an independently-sourced claim only (`INDEPENDENT_SOURCE_TYPES` — self-published TAM
never counts). `catalyst_name` and `competitive_structure` are presence/categorical-value contracts
respectively, unchanged from what Market Opportunity (Task 13) already established. **Recall** for
this pillar (whether the acquisition layer retrieves market-sizing evidence at all) is explicitly out
of this task's scope — item 9 asked only for inspection, not a fix, and none was made.

## 11. Fail-closed behavior (item 11)

`check_classifier_readiness(fact)` returns `False` — never `True`, never raises — on: `None`, a fact
with no `"kind"`, an unrecognized `kind`, or a context-only kind. For every real kind-gated kind, a
missing required field, an out-of-vocabulary categorical value, or an unparseable numeric/date field
all return `False`. **No code path anywhere in `fact_contracts.py` infers, guesses, or defaults a
missing field's value.** `test_fact_contracts.py` (item 12) additionally verifies this holds not just
at the contract-check boundary but at the real downstream **consumer** boundary — an insufficient fact
handed directly to a real classifier/parser is always safely ignored, never crashes, never fabricates
a label. That same test run caught and fixed one real, previously-latent instance of this boundary
being violated (§ Regression note below).

## 12. Regression note — a real bug this task's own tests found and fixed

`stage.py::determine_stage()` read `structured_fact["value"]` via direct bracket access for both
`funding_round_type` and `founding_year` facts. The `founding_year` branch had a `try/except
(TypeError, ValueError)` around the `int()` conversion, but a **missing** `"value"` key raises
`KeyError`, which that `except` clause does not catch. `test_fact_contracts.py`'s own consumer test
for `founding_year` (built the same way the calibration suite or any hand-built ledger fixture
legitimately could — bypassing extraction-time routing entirely) reproduced this crash directly. Task
25's routing/applicability layer already keeps a malformed fact like this **out** of `stage_signal` on
the normal, routed extraction path — this fix is defense-in-depth for any path that check does not
gate, not a second, competing rule. Fixed with `.get("value")` in both branches (round-type and
founding-year), preserving the exact same "fail closed to no signal from this claim" behavior the
`except` clause already established for the founding-year branch, extending it to the round-type
branch and to the missing-key case specifically. See
`docs/methodology/COHORT_001_EXTRACTION_REMEDIATION.md` for the full account.

## 13. What this task explicitly did not change

- `parameters.py` — untouched.
- Any pillar file's own scoring/gating logic — untouched, except the one narrow `stage.py` defensive
  fix in §12 above (a crash-prevention fix, not a scoring or gating change: the outcome for every
  well-formed input is byte-identical; the only behavior change is that a malformed input now returns
  `Stage.UNDETERMINED` instead of raising).
- Acquisition search/retrieval/query text/budgets — untouched.
- Any of the six historical `LIVE_EVALUATION_*.md` / `*_REMEDIATION.md` reports — untouched.
- No live/network call was made anywhere in this task.
