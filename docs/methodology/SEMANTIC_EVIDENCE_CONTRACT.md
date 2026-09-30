# Semantic Evidence Contract (Task 29)

Task 28's live validation found that Task 27's structural contract was necessary but not sufficient: a
fact could be grounded, schema-valid, correctly typed, and correctly routed, and still not be what it
claimed to be. This document defines the full boundary this task builds, and the terminology every
later task should use when talking about "how ready" a piece of evidence is.

## 1. The production boundary (this task's own success criterion)

```
grounded -> canonical -> structurally compatible -> semantically supported -> deterministically routed -> methodology-consumable
```

Six stages, five real gates, each independently named and independently testable:

| Stage | Gate | Where | Introduced |
|---|---|---|---|
| grounded | excerpt genuinely supports claim_text | `extraction.py::validate_candidate()` | Task 20 |
| canonical | fields deterministically derivable from what's grounded are in their canonical representation | `canonicalization.py::canonicalize_structured_fact()` | **Task 29** |
| structurally compatible | required fields present, values in the allowed vocabulary | `fact_contracts.py::check_classifier_readiness()` | Task 27 |
| semantically supported | the excerpt supports the SPECIFIC categorical value chosen | `semantic_fit.py::check_semantic_fit()` | **Task 29** |
| deterministically routed | the dimension this fact could reach exists and is reachable | `routing.py::route_candidate()` | Tasks 23/25, extended Task 29 |
| methodology-consumable | all of the above, combined | `semantic_fit.py::check_methodology_readiness()` | **Task 29** |

Anything weaker than all six fails closed — the claim remains in the ledger (grounding/provenance are
never discarded), but its `assessment_criteria` simply never reaches the dimension the missing stage
would have unlocked.

## 2. Structural vs. semantic validity — two different questions

**Structural validity** (`check_classifier_readiness()`, unchanged since Task 27): is this field
present, and is its value a member of the allowed enum? A pure shape check — it has no access to, and
never reads, the claim's own `claim_text`/`excerpt`.

**Semantic validity** (`check_semantic_fit()`, new this task): does the excerpt the claim cites actually
support the SPECIFIC value chosen, as opposed to some other value in the same enum? A content check —
it never reads `Strength`/`Coverage`/company identity, only the fact's own `kind`/`value` and the
claim's own text.

A value can be structurally valid and semantically wrong — `retention_signal="STRONG"` and
`competitive_structure="fragmented"` were both, in Task 28's real live data, exactly this: present,
correctly-vocabulary'd, and not supported by what the cited excerpt actually said.

## 3. Canonicalization — the ordering fix (items 2-5)

**The defect.** `routing.py::route_candidate()`'s applicability check ran on the candidate's raw,
just-extracted `structured_fact` — before `claim_identity.py::finalize_claim()`'s own `person_id`
backfill, and before any cleanup of a numeric amount ("52M") or an explicit-but-non-ISO date ("Aug 5,
2026"). A fact genuinely, deterministically completable from what the model already grounded was judged
"insufficient structure" and permanently stripped of its dimension, even though the identical fact
becomes classifier-ready moments later.

**The fix.** `canonicalization.py::canonicalize_structured_fact()`, called by `extraction.py::
_sanitize_assessment_criteria()` immediately before routing — the smallest change that satisfies "fields
deterministically derivable from grounded evidence are present before routing checks that depend on
them," not a general pipeline reorder. Three canonicalizers:

- **Person identity** — reuses `claim_identity.py::backfill_person_id()` directly (made public this
  task, not re-implemented). Never infers a person from a vague title, never merges on role alone, never
  overwrites an existing `person_id`.
- **Numeric amount** — `canonicalize_numeric_amount()`. `"$52M"` / `"52M"` / `"52 million"` /
  `"1,250,000"` each unambiguously denote one real number; converted to the bare form
  `fact_contracts.py`'s own `_numeric_ok()` already expects. A range, a vague quantifier ("tens of
  millions", "over $50M"), or anything with a second number fails to match the anchored pattern and is
  returned completely unchanged — ambiguity fails closed by construction, not by a special case.
  Currency is never touched, inferred, or converted.
- **Explicit date** — `canonicalize_explicit_date()`. Only a FULLY explicit month-name date ("August 5,
  2026") or an unambiguous `YYYY/MM/DD` form is converted to ISO. A bare year, a year-month, a quarter,
  or a vague season never is — normalizing any of those would require inventing a day or month the
  source never stated.

Every canonicalizer's contract is identical: return the input unchanged whenever it doesn't
unambiguously match; never invent precision; the representation changes, the evidence never does.

## 4. Semantic-fit validation — the third, independent gate (items 6-11)

Five distinct questions, five distinct gates, never conflated:

```
JSON/schema validation  -- providers_live.py (Pydantic/OpenAI structured output)
grounding validation    -- extraction.py::validate_candidate (excerpt supports claim_text)
classifier readiness    -- fact_contracts.py (required fields present, values in vocabulary)
semantic fit            -- semantic_fit.py (does the excerpt support the SPECIFIC value)
routing/applicability   -- routing.py (does the dimension this fact could reach even exist for it)
```

**Deterministic, never probabilistic.** Every rule is a plain keyword/phrase regex over `claim_text`/
`excerpt` — no model call, no score, no threshold. A rule returns exactly one of three outcomes,
`SemanticFitStatus`:

- `SUPPORTED` — explicit, on-topic vocabulary found.
- `UNSUPPORTED` — none found; fails closed (absence of evidence is never evidence).
- `NOT_APPLICABLE` — no rule is defined for this kind at all; never conflated with either of the other
  two ("no check ran" is not "passed").

### 4a. Retention rule (item 7)

`retention_signal` requires explicit retention/renewal/churn/repeat-customer vocabulary in the claim's
own text (`retention`, `renew(al)`, `churn`, `repeat custom-`, `returning custom-`, `recurring custom-`,
`retain(ed/ing)`). A customer count, active-user figure, logo, testimonial, adoption/usage-mix
statistic, longevity claim, growth figure, or popularity claim contains none of these words and is
correctly `UNSUPPORTED` — exactly item 7's own exclusion list, and exactly Task 28's real Notion finding
(a "90% multiplayer usage" adoption statistic mistaken for `"STRONG"` retention).

### 4b. Competitive-structure rule (item 8)

`competitive_structure="fragmented"` requires explicit fragmented-market vocabulary (`fragmented`, "no
clear/dominant/single leader", "many players/competitors", "highly competitive landscape", "crowded
market"); `"concentrated"` requires the mirror vocabulary (`concentrated`, "dominated by", "market
leader", "duopoly", "monopoly", "few major players"). A bare list of named competitors, with no
structural characterization at all, matches neither and is correctly `UNSUPPORTED` — exactly Task 28's
real Notion finding (a Microsoft/Atlassian/Airtable competitor list mistaken for `"fragmented"`).

### 4c. Generalization — where a rule was and wasn't added (item 9)

Every other categorical field was inspected. A rule was added only where (1) the category has a clear
semantic contract, (2) an unsupported proxy is reliably identifiable, and (3) the rule can reject without
guessing. Only `retention_signal` and `competitive_structure` — the two kinds Task 28 found a CONFIRMED
real mismatch for — met all three. Fields left `NOT_APPLICABLE`, with the specific reason:

| Field | Why no rule was added |
|---|---|
| `financing_type` (equity/debt/grant/...) | Most real "equity round" articles never literally say "equity" — a keyword-absence rule would reject a large fraction of genuinely legitimate `funding_round` claims. Requires understanding legal/financial terminology a keyword match cannot reliably approximate. |
| `funding_round.status` (completed/announced) | "Closed"/"raised" vs. "plans to raise"/"in talks" is a real distinction, but source phrasing varies too widely (many outlets omit tense-signaling words entirely) for a low-false-reject rule. |
| `product_release.status` (launched/announced/beta/...) | Real "launched" language is highly varied ("now live", "ships today", "rolling out", "available now", "launched") — a vocabulary list broad enough to catch most legitimate cases risks also accepting weaker "announced" language. |
| `founder_experience.value` (ADJACENT/DIRECT) | Domain-relevance is a judgment about TWO domains' relationship (the person's prior work vs. the current company's business) — not expressible as a keyword match at all. |
| `track_record.value` (PRIOR_EXIT/PRIOR_VENTURE_ROLE) | "Was acquired" vs. "a prior venture-backed role" is closer to a keyword match (`acquired`, `IPO`, `sold to`) and is a plausible CANDIDATE for a future rule, but was not verified against real failure data this task — left undone rather than guessed at. |
| `capital_efficiency_signal.value` (WEAK/MODERATE/STRONG) | A judgment about financial health requires numeric/contextual reasoning ("profitable since 2021" vs. "burning $2M/month") a keyword match cannot safely tier. |
| `customer_band.value` (SMALL/MODERATE/LARGE) | Already requires a QUALITATIVE characterization, not a bare count (`fact_contracts.py`'s own contract); no CONFIRMED false-positive was found for this field in Task 28's real data, so no rule was added without evidence of a real gap. |

**This is a deliberately narrow list, not an oversight** — item 9's own "do not create an enormous new
rules engine." Extending this table later requires the same evidence-first discipline every rule in this
engine has followed since Task 23: derive the rule from a CONFIRMED real failure, never from a
hypothetical one.

## 5. Fail-closed semantic outcome (item 10)

A semantic mismatch narrows routing; it never rejects the candidate outright. `RoutingStatus` gains a
new, DISTINCT member: `UNROUTED_SEMANTICALLY_UNSUPPORTED` — deliberately separate from
`UNROUTED_INSUFFICIENT_STRUCTURE` (which means the fact's own FIELDS don't meet its consumer's
contract; this one means the fields are all present and schema-valid, but the text doesn't support the
value chosen). Two different failure classes, two different fixes (extraction completeness vs.
extraction correctness), two different, inspectable statuses — never folded into one opaque bucket.
`RoutingDecision`/`RoutingResult` also carry a separate `semantic_fit_status` field
(`not_applicable`/`supported`/`unsupported`), always set, so the two dimensions (routing outcome,
semantic-fit outcome) are never conflated even when read together. The claim itself — `claim_text`,
`excerpt`, `structured_fact`, provenance — is never mutated; only `assessment_criteria` narrows, exactly
the same mechanism every other UNROUTED status already relies on to keep a dimension structurally
invisible to `resolve_dimension_evidence()`.

## 6. `check_methodology_readiness()` — the final readiness terminology (item 15)

```
structured -> classifier-compatible -> semantically-supported -> methodology-usable
```

`classifier-compatible` is `fact_contracts.py::check_classifier_readiness()`, unchanged and unrenamed
(Task 27/28's own tests and docs stay valid without modification). `methodology-usable` is
`semantic_fit.py::check_methodology_readiness(fact, claim_text, excerpt)` — `True` only when the fact is
BOTH classifier-compatible AND (no semantic-fit rule applies, or the rule that does apply finds it
supported). A fact that is structurally ready but semantically wrong is explicitly NOT "production-ready
evidence," regardless of what `check_classifier_readiness()` alone reports — this is the precise
terminology fix item 15 asks for, without rewriting or deprecating Task 27's own function.

## 7. Invariance (item 11)

No function in `semantic_fit.py` can reach a company name, a `Strength`, or a `Coverage` value —
verified structurally (`check_semantic_fit`'s own signature is exactly `(fact, claim_text, excerpt)`,
nothing else) and behaviorally (`test_semantic_fit_decision_is_company_name_invariant` proves the
identical evidence shape produces the identical decision for Notion, Stripe, Fish Audio, and a fictional
company).

## 8. Prompt reinforcement (item 12) — secondary, not the boundary

`providers_live.py`'s system prompt gained explicit negative examples for both rules (adoption-vs-
retention, competitor-list-vs-structure) and a light preference for bare-number/ISO-date formatting.
This is reinforcement only — the deterministic `semantic_fit.py`/`canonicalization.py` gates are what
actually enforce these rules; the prompt cannot be, and is not treated as, the correctness boundary.
