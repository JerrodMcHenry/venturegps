# Live Evaluation — Fish Audio (Run 002)

Task 28 — the first live run against Task 27's classifier-ready structured extraction contract.
Baseline: `LIVE_EVALUATION_FISH_AUDIO_001.md` (unmodified). Input:
`CompanyAnalysisInput(company_name="Fish Audio", website_url="https://fish.audio")` — same canonical
URL as run 001, reused unchanged, not re-derived. Same unmodified `AcquisitionBudget()`, same unmodified
research plan, same unmodified pipeline, same unmodified 6-pillar methodology. Run exactly once;
provider-internal retries (configured, bounded) allowed. **Primary metric: classifier-ready rate, not
Coverage or pillar publication.**

## 1. Run completion and timing

Completed successfully, one run, no fatal errors. **42.27s total** (vs. 25.77s for 001 — the increase
tracks the larger claim count this run extracted, not a slowdown per claim). Stage breakdown:
research_planning ~0s, source_discovery_and_retrieval 13.19s (21 sources, up from 20), evidence_extraction
29.07s (27 claims accepted, up from 18), contradiction_detection/ledger_construction/pillar_evaluation
all sub-millisecond, as expected for deterministic stages.

## 2. Provider measurements

| | Tavily | HTTP | OpenAI (gpt-4.1-mini) |
|---|--:|--:|--:|
| Calls | 12 | 27 | 6 |
| Succeeded | 12 | 21 | 6 |
| Failed | 0 | 6 (all HTTP 403/202, unrelated to Task 27) | 0 |
| Provider attempts beyond first | 0 | 0 | 1 (one batch needed a validation-feedback retry, succeeded) |

Tokens: **40,421 total** (35,764 input / 4,657 output) vs. 001's 26,358 (23,382/2,976) — a real
increase, attributable to (a) the longer system prompt (Task 27's routing-guidance rewrite, already
documented as a deliberate, measured tradeoff in `PROVIDER_ADAPTERS_AND_CALL_BUDGET.md`), and (b) more
claims extracted this run (27 vs 18) requiring more output tokens. 5 of 6 batches truncated on input
(vs. 4/5 for 001) — consistent with the longer prompt leaving less room per batch, not a new defect.
0 output truncation, 0 content-filter failures, 0 sources excluded for budget — the schema/prompt
changes caused no provider-level failure mode.

## 3. Evidence measurements

**27 claims accepted, 0 rejected** (vs. 18/0 for 001 — genuinely more evidence found this run, real
search-result variance, not a Task 27 effect). **Structured-fact rate: 12/27 = 44.4%** — identical to
001's 44.4%, confirming Task 27 did not change how OFTEN the model attaches a typed fact, only what
those facts contain.

### The primary metric: classifier readiness

| | Run 001 (reconstructed*) | Run 002 (measured directly) |
|---|--:|--:|
| Relevant typed claims (kind has a deterministic consumer) | 7 | 12 |
| Classifier-ready claims | **0** | **4** |
| **Classifier-ready rate** | **0.0%** | **33.3%** |

*Run 001 predates `check_classifier_readiness()`; reconstructed here by applying that same unmodified
function to 001's preserved `ledger_claims`, without touching `LIVE_EVALUATION_FISH_AUDIO_001.md`
itself. Labeled reconstructed throughout.

**This is a real, material, positive change** — Fish Audio went from zero classifier-ready relevant
evidence to 4 claims a real deterministic classifier can now correctly consume, with no increase in
rejected claims (0 both runs) and no new provider failure mode.

## 4. Categorical semantic correctness (§5) — the funding validation (§6)

**`financing_type` conflation is fixed, confirmed directly.** All 5 `funding_round` candidates this
run carry `financing_type="equity"` — **never `"Seed"`**, the exact Task 26 finding. Real excerpts
checked: "Fish Audio, the Palo Alto-based AI voice-generation startup, closed a $52 million seed round
on Aug 5, 2026..." → `financing_type="equity"`, `amount="52 million"`, `round_date="2026-08-05"`,
`status="completed"`, `currency="USD"` — the legal-structure/round-label distinction the prompt now
teaches is being followed correctly.

**But no `funding_round` claim is classifier-ready this run, for a different, new reason: `amount`
format.** `funding_round_fields_are_sufficient()` requires `amount` to parse as a bare `float()`. Every
one of the 5 real `amount` values this run is `"52M"` or `"52 million"` — neither parses. This is **not**
the conflation bug Task 27 targeted (that bug is confirmed fixed); it is a related but distinct gap
Task 27's contract does not address: the model was never told the amount field itself must be a bare
number.

**The "propose two candidates" guidance was not exercised this run.** No `funding_round_type` candidate
(the separate round-label kind) was proposed at all, despite every excerpt explicitly saying "seed."
Net effect versus 001: the round label is no longer **wrongly conflated** into `financing_type` — it is
simply **dropped**. A real, meaningful improvement (no false `equity`≠`"Seed"` string ever reaches
`funding_history`'s own admissibility check incorrectly) but not yet the full two-candidate behavior
item 4 envisioned.

**Traction metrics — vocabulary fixed, two new, different blockers found.** Of 6 `traction_metric`
claims: `metric` is correctly `"arr"` or `"active_users"` in every case (a real fix — 001 never used the
correct enum value at all); `value_type="actual"` is correctly populated in every case. But 3/6 still
fail `check_classifier_readiness()`: two on unparseable `amount` (`"21 million"`, `"8 million"`), one on
a malformed `period_date` (`"2026"` — not a full ISO date, fails `date.fromisoformat()`). The other 3
(bare `amount="13"`/`"21"`/`"21"`, full ISO `period_date`) are classifier-ready and correctly reach
`growth_trajectory`.

**`founder_experience` — correctly typed, value populated, semantically debatable.** One claim:
`named_entity="Shijia Liao"`, `value="DIRECT"`, citing "co-founder and Chief Scientist Shijia Liao, a
former NVIDIA video researcher." Schema-valid and classifier-ready. Semantically: video ML research is
adjacent to, not identical to, voice/audio AI — `"ADJACENT"` would arguably be the more defensible
label than `"DIRECT"` here. Not as clear-cut a misclassification as the Notion findings (§ below, see
`LIVE_EVALUATION_CONTRACT_VALIDATION_001.md` §5), but worth flagging as a borderline case.

## 5. A newly-discovered real defect — person_id backfill runs after routing's applicability check

The `founder_experience` claim above is genuinely classifier-ready (`check_classifier_readiness()`
returns `True` on its final, ledger-stored `structured_fact`) — **but its `assessment_criteria` is
`[]`**, meaning no dimension can ever cite it. Direct inspection of its routing decision:

```
status: unrouted_insufficient_structure
reason: kind='founder_experience': proposal ['founder_relevant_experience'] named an eligible
        dimension, but the fact's own fields do not meet that dimension's evidence contract
```

**Root cause, confirmed by reading the pipeline's own call order** (`pipeline.py::_extract_claims()`):
`extraction.py`'s routing/applicability check (`_sanitize_assessment_criteria()` → `route_candidate()`
→ `check_classifier_readiness()`) runs **before** `claim_identity.py::finalize_claim()`'s deterministic
`person_id` backfill. `founder_experience`'s contract requires `person_id` — at routing time the raw
model output had none (the model is never trusted to invent one — `_backfill_person_id()`'s own
docstring), so the applicability check correctly, honestly failed **at that moment** — but the fact
*does* get a `person_id` moments later, once `finalize_claim()` runs, silently making the already-locked
routing decision stale. This is a real, previously-undetected pipeline-ordering defect, not a false
positive: the fact is genuinely usable by the time it reaches the ledger, but is permanently excluded
because the applicability check ran on an earlier, incomplete version of it. **Undetectable by Task 27's
own unit tests** (which called `check_classifier_readiness()` directly on already-complete fact dicts,
never through the full extraction→routing→finalize pipeline order) — found here only because this is a
real live run against the real, ordered pipeline. See
`docs/methodology/LIVE_EVALUATION_CONTRACT_VALIDATION_001.md` §7 for the full cross-company account and
decision-gate implications. **Not fixed in this task, per its own explicit "no fixes" rule.**

## 6. Fail-closed behavior

0 claims rejected. Routing status distribution: `routed` 18, `unrouted_insufficient_structure` 9,
`rejected_invalid_routing` 0, `context_only` 0. Every one of the 9 unrouted claims has a specific,
inspectable reason (§4-5 above account for all of them: 5 funding-amount-format, 3
traction-amount/date-format, 1 the person_id-ordering defect). **No fabrication observed anywhere**:
every non-ready claim was correctly, honestly excluded from citability rather than guessed into a score.

## 7. Pillar results

| Pillar | Published | Strength | Coverage | Confidence | Scored dimensions |
|---|---|--:|--:|---|---|
| Market Opportunity | No | — | 0.0% | Low | none |
| Product & Technology | **Yes** | 7.67 | 75.0% | High | product_existence_maturity, differentiation_claim_corroboration, defensibility_signal |
| Team & Leadership | No | — | 0.0% | Low | none |
| Commercial Traction | No | — | 0.0% | Low | none (growth_trajectory correctly, legitimately withheld — §8) |
| Execution & Momentum | No | — | 0.0% | Low | none |
| Financial & Funding Signals | No | — | 0.0% | Low | none |

Company Coverage 13.5% (unchanged from 001), Confidence High, not publishable. **Identical pillar-level
outcome to 001** — the classifier-readiness gains this run (§3) did not yet translate into a newly
scored dimension, for the specific, named, non-mysterious reasons in §8.

## 8. Why classifier-readiness gains did not yet move a pillar score

- **`growth_trajectory`** (3 classifier-ready points, correctly routed): genuinely, correctly withheld.
  `_qualifying_scale_points()` finds a real 2-point pair (ARR $13M @ 2026-05-05, $21M @ 2026-07-28), but
  the window is 84 days — below `GROWTH_MIN_WINDOW_DAYS = 180`. This is the methodology's own real,
  unmodified structural floor working exactly as designed, not a defect.
- **`funding_history`**: blocked by the amount-format gap (§4).
- **`founder_relevant_experience`**: blocked by the person_id-ordering defect (§5).
- **`disclosed_scale`**: never reached at all — the model's own proposed `assessment_criteria` for the
  qualifying traction claims named `growth_trajectory`/`commercial_validation` but never
  `disclosed_scale`; routing narrows to the model's own proposal (never adds beyond it, except the
  verified 3-kind fallback), so a single-point disclosure that could have qualified for Disclosed Scale
  was simply never offered that dimension. Unchanged, pre-existing routing behavior (Task 25), not a
  Task 27 effect.

## 9. Comparison against LIVE_EVALUATION_FISH_AUDIO_001.md

See `docs/methodology/LIVE_EVALUATION_CONTRACT_VALIDATION_001.md` §4 for the full 001→002 comparison
table (both companies) and the consolidated cross-company analysis. Summary: classifier-ready rate rose
from 0% to 33.3%; financing_type conflation confirmed fixed; two new, different structural gaps found
(amount format, the person_id-ordering defect); zero claims rejected either run; pillar-level outcome
unchanged.
