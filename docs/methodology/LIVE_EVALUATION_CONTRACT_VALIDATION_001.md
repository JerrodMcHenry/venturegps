# Contract Validation 001 — Live Classifier-Ready Extraction Validation (Task 28)

Consolidated cross-company analysis of Task 28's two controlled live runs (Fish Audio, Notion) against
Task 27's canonical classifier-ready structured extraction contract. Full per-company detail:
`LIVE_EVALUATION_FISH_AUDIO_002.md`, `LIVE_EVALUATION_NOTION_002.md`. Baselines (unmodified):
`LIVE_EVALUATION_FISH_AUDIO_001.md`, `LIVE_EVALUATION_NOTION_001.md`.

**The one question this document answers:** does the canonical structured-fact contract materially
increase classifier-ready evidence in real acquisition runs, without increasing unsupported or
incorrectly classified evidence? **Short answer: partially yes on the first half, no on the second —
see §5 and §18.**

## 1. System freeze confirmation

Before either run: confirmed present and active — `fact_contracts.py` (20 fact kinds, importable, `git
log` shows Task 27's commit `a9a5e3f` as HEAD, working tree clean); `_StructuredFactSchema`'s
`financing_type`/`value_type` real enums (`inspect.signature` confirmed); `_APPLICABILITY_CHECKS`
covering 18 kinds (confirmed via import); Tasks 23-25's routing/relevance/identity modules unchanged
since their own last commits (`git log` on `routing.py`/`claim_identity.py`/`person_identity.py`/
`relevance.py` shows no commit after Task 27's); `parameters.py`/`research_plan.py`/`pipeline.py`/
`models.py` (`AcquisitionBudget` defaults) last touched at or before Task 25/26 — byte-identical to
what Task 26's own cohort run used; isolation boundary 3/3; no legacy scoring path reachable (unchanged
`app.evidence_engine` import boundary, re-verified). `OPENAI_API_KEY`/`TAVILY_API_KEY` confirmed present
(length-only, never printed). **Nothing was changed before, between, or after the two runs.**

## 2. Both runs completed

Fish Audio: completed, 42.27s, 21 sources, 27 claims accepted, 0 rejected. Notion: completed, 34.02s,
23 sources, 13 claims accepted, 0 rejected. No fatal implementation problem appeared after Fish Audio —
Notion ran against the identical, unmodified implementation, as required.

## 3. Exact version/config

Commit `a9a5e3f` ("fix: build classifier-ready evidence extraction contract"), clean working tree, both
runs. `AcquisitionBudget()` defaults unchanged since before Task 26 (`max_queries_per_topic=2,
max_topics=6, max_sources_per_query=3, max_total_sources=24, max_extraction_calls=24,
max_sources_per_batch=4, max_chars_per_source=6000, max_total_input_chars_per_batch=20000, ...`).
Research plan: 12 queries/company, unchanged wording since Task 23. Model: `gpt-4.1-mini`, temperature
0, `client.chat.completions.parse()` (Task 21A), unchanged.

## 4. 001 → 002 comparison

| Metric | Fish Audio 001 | Fish Audio 002 | Change | Notion 001 | Notion 002 | Change |
|---|--:|--:|--:|--:|--:|--:|
| Runtime (s) | 25.8 | 42.3 | +16.5 | 27.7 | 34.0 | +6.3 |
| Sources retrieved | 20 | 21 | +1 | 23 | 23 | 0 |
| Accepted claims | 18 | 27 | +9 | 23 | 13 | −10 |
| Rejected claims | 0 | 0 | 0 | 0 | 0 | 0 |
| Structured-fact rate | 44.4% | 44.4% | 0 | 47.8% | 61.5% | +13.7pp |
| Relevant typed claims | 7 | 12 | +5 | 8 | 5 | −3 |
| Classifier-ready claims | 0* | 4 | +4 | 0* | 2 | +2 |
| **Classifier-ready rate** | **0.0%\*** | **33.3%** | **+33.3pp** | **0.0%\*** | **40.0%** | **+40.0pp** |
| Routed claims | 13 | 18 | +5 | 18 | 7 | −11 |
| Published pillars | 1/6 | 1/6 | 0 | 1/6 | 1/6 | 0 |
| Company Coverage | 13.5% | 13.5% | 0 | 9.0% | 17.0% | +8.0pp |
| Company Confidence | High | High | — | High | High | — |
| Company publishable | No | No | — | No | No | — |
| Total tokens | 26,358 | 40,421 | +14,063 | 32,551 | 45,865 | +13,314 |
| Validation retries | 0 | 1 | +1 | 0 | 2 | +2 |

\* Reconstructed by applying the real, unmodified `check_classifier_readiness()` to 001's preserved
`ledger_claims` — labeled reconstructed, `LIVE_EVALUATION_FISH_AUDIO_001.md`/`_NOTION_001.md` themselves
untouched.

## 5. Categorical semantic correctness — the central finding

Structural/vocabulary correctness genuinely improved (§6-7 below). Semantic correctness did not
uniformly follow it. Two of the newly classifier-ready claims (both Notion, both newly reaching a
scored dimension) are schema-valid and evidence-unsupported:

- `competitive_structure="fragmented"` inferred from a bare, uncharacterized competitor list — the
  contract's own notes explicitly prohibit exactly this inference, and it happened anyway.
- `retention_signal="STRONG"` assigned to a "90% multiplayer usage" adoption statistic — not retention,
  renewal, or churn evidence by any reading, and explicitly excluded by both the contract's notes and
  Task 28's own §9 instruction.

**This is not a defect in the contract's own logic** — `check_classifier_readiness()` and the real
classifiers did exactly what they have always been designed to do: verify a field is present and its
value is in the allowed vocabulary. Neither has ever attempted to verify that the excerpt actually
entails the SPECIFIC value chosen (a materially harder problem — natural-language entailment — that no
dimension in this engine has ever attempted for any kind). What changed is that Task 27's prompt now
successfully gets the model to populate these fields far more often (the whole point, and the reason
classifier-readiness rose) — and, as an unavoidable side effect, also raises the rate at which a
schema-valid but wrong choice reaches a scored dimension where it previously would have stayed correctly
Unscored (because the field was simply never populated before). **A pre-existing validation gap, made
newly consequential by Task 27's own success, not a new defect Task 27 introduced.**

Fish Audio's one borderline case (`founder_experience.value="DIRECT"` for a "former NVIDIA video
researcher" joining a voice-AI company — arguably `ADJACENT`) is less clear-cut but points the same
direction: schema/vocabulary validity is not semantic validity.

## 6. Funding validation — Fish Audio (§6)

`financing_type` conflation (Task 26's Fish Audio finding: `"Seed"` populated where `"equity"` was
required) is **confirmed fixed** — all 5 real `funding_round` candidates this run correctly carry
`financing_type="equity"`. The round label ("seed") is no longer wrongly conflated into that field —
but it is also not yet captured as a separate `funding_round_type` candidate (the two-candidate
instruction was not exercised this run; the label was simply dropped). **A new, different, still-open
gap found**: `amount` is populated as `"52M"`/`"52 million"` in all 5 real candidates — never a bare
parseable number — so despite the conflation fix, zero funding_round claims are classifier-ready this
run. Amount/currency themselves are otherwise correctly preserved (currency="USD" in all 5; the
disclosed figure is consistently $52M across every source, correctly recognized as the same real event).
Deterministic routing reaches only the legitimate consumer (`funding_history`) — no misrouting observed.

## 7. Metric validation — Notion (§7)

Metric-vocabulary paraphrasing (Task 26's Notion finding: `"annual revenue"`, `"annual recurring
revenue"`, `"users"`, `"paying customers"`, none matching the required enum) is **confirmed fixed** for
2 of 3 real traction claims this run: `metric="revenue"` and `metric="active_users"`, both exact
matches, both correctly paired with `value_type="actual"` (001 populated `value_type` on zero claims).
A new, different, still-open blocker was found: `period_date` is absent from both, so neither is
classifier-ready despite the vocabulary fix. The third traction claim (`metric="valuation"`) was
correctly, appropriately excluded — not a real traction metric at all. The source genuinely states each
figure (grounding intact); the downstream classifier genuinely could consume metric+value_type+amount
correctly; only the date field blocks it.

## 8. Team / retention / release validation

**Team (§8):** `person_id` backfill confirmed correct and consistent (Notion's 3 Ivan Zhao claims all
share one id). Prestige never became a quality signal in either run (no `founder_experience` claim
scored this run with a prestige-driven rationale). The pre-existing `team_identity.role`-exact-match gap
(documented in Task 27's own contract doc) is confirmed still present, unchanged. Tasks 14/23-25's
identity behavior is not weakened.

**Retention (§9):** Fish Audio acquired no retention evidence this run (correctly Unscored — no
fabrication). Notion's one retention_signal claim is the §5 semantic-accuracy finding — schema-valid,
not genuine retention evidence. **Where genuine retention evidence did not exist, the system did not
invent it**; where a real gap existed (customer-count/adoption text mistaken for retention), the *model*
mischaracterized it, and the *contract* had no mechanism to catch that mischaracterization.

**Release (§10):** No `product_release` claims were extracted in either run this task, so release
validation could not be exercised live. Not observed, not a Task 27 failure.

## 9. Fail-closed behavior (§11)

Both runs: **0 claims rejected.** Routing status distribution (combined): `routed` 25, `context_only`
3, `unrouted_insufficient_structure` 12, `rejected_invalid_routing` 0. Every unrouted claim traces to a
specific, inspectable, honest reason (amount format, missing period_date, or — Fish Audio only — the
person_id-ordering defect, §7 below). **The system consistently preferred withholding over inventing a
missing field, in every case checked.** The one place fail-closed behavior became a genuine liability
(not a fabrication risk, but a real-evidence-blocked risk) is the person_id-ordering defect.

## 10. A newly-discovered pipeline-ordering defect (Fish Audio only, but architecturally general)

`pipeline.py::_extract_claims()` calls `finalize_claim()` (which backfills `person_id`,
`claim_identity.py::_backfill_person_id()`) **after** `extraction.py`'s routing/applicability check has
already run and locked in `assessment_criteria`. For any kind whose contract requires `person_id`
(`founder_experience`, `track_record`), a fact the model did not itself supply a `person_id` for — the
normal case, since the extractor is never trusted to invent one — is judged "insufficient structure" at
routing time and permanently stripped of its dimension, even though the SAME fact becomes genuinely
classifier-ready moments later once `person_id` is backfilled. Confirmed directly in Fish Audio's
`founder_experience` claim about Shijia Liao: `check_classifier_readiness()` on the FINAL, ledger-stored
fact returns `True`; its `assessment_criteria` is nonetheless `[]`. Full detail:
`LIVE_EVALUATION_FISH_AUDIO_002.md` §5. **This is the one specific, narrow, code-locatable defect this
validation found that materially blocks real evidence from reaching a real classifier.**

## 11. Regressions checked (§14)

- Fewer legitimate claims: no — both runs' claim counts moved with normal search variance (Notion down,
  Fish Audio up), never below what routing/extraction itself could support; 0 rejected either run.
- Structured-output provider failures: none (0 content-filter, 0 output-truncation events either run).
- Increased validation retries: yes, small (0→1 Fish Audio, 0→2 Notion) — all succeeded on retry, within
  the existing 2-attempt-per-batch budget (Task 21A), not a new failure mode.
- Increased token usage materially: yes (+14.1K Fish Audio, +13.3K Notion) — attributable to the longer
  system prompt (a known, already-documented Task 27 tradeoff), not a surprise.
- Legitimate facts rejected because enums are too narrow: not observed as an outright rejection (0
  rejected claims either run) — but the amount-format and period_date gaps (§6-7) function similarly,
  excluding otherwise-legitimate facts from classifier readiness for reasons outside Task 27's own scope.
- False categorical mappings: **yes, confirmed** — §5.
- Duplicated facts from funding candidate splitting: not observed — splitting did not occur this run
  (the model never proposed a separate `funding_round_type` candidate), so this specific risk was not
  exercised.
- Incorrect increases in Coverage: Notion's Coverage rose 9.0%→17.0% on the two §5 claims — given their
  semantic-accuracy issue, this increase should be read with real skepticism, not celebrated as
  unqualified progress.

## 12. Prior Task 26 failures — fixed / still broken / not observed (§13)

| Prior finding | Status |
|---|---|
| Fish Audio: `financing_type="Seed"` (round label, not legal structure) | **Fixed** — confirmed, all 5 candidates this run |
| Fish Audio: `founding_year` field-name mismatch (`amount` vs `value`) | Not observed — no `founding_year` claim extracted this run |
| Notion: `metric` paraphrasing (`"annual revenue"` etc.) | **Fixed** — 2/3 claims now exact-match |
| Notion: `value_type` never populated | **Fixed** — populated on 2/3 claims this run |
| Notion: `funding_round` missing financing_type/round_date/status | Not observed — no `funding_round` claim extracted this run |
| Notion: `founding_year` field-name mismatch | Not observed — no `founding_year` claim extracted this run |
| Stripe: `founder_experience`/`track_record` never populate categorical `value` | Not directly re-tested (Stripe not run this task) — Fish Audio's own `founder_experience.value` IS populated this run, a positive proxy signal |
| **New, not a prior finding**: funding `amount` format ("52M"/"52 million") | **Still broken** — newly identified, not previously documented |
| **New, not a prior finding**: `traction_metric.period_date` missing | **Still broken** — newly identified |
| **New, not a prior finding**: person_id-ordering defect | **Still broken** — newly identified, §10 |
| **New, not a prior finding**: schema-valid but semantically wrong categorical values | **Still broken** — newly identified, §5, the most important one |

## 13. Six-pillar results (secondary metric)

See `LIVE_EVALUATION_FISH_AUDIO_002.md` §7 and `LIVE_EVALUATION_NOTION_002.md` §8 for the full
per-dimension tables. Summary: Fish Audio unchanged (1/6 published, Coverage 13.5%); Notion's Market
Opportunity and Commercial Traction each gained one scored (but semantically questionable) dimension,
Coverage rose 9.0%→17.0%, still 1/6 published, still not company-publishable in either case. No overall
company score exists or was computed — unchanged.

## 14. Did Task 27 work? (§17)

1. **Did classifier-ready rate improve?** Yes, materially, both companies (0%→33.3%, 0%→40.0%).
2. **Did semantic accuracy remain acceptable?** No — two confirmed schema-valid, evidence-unsupported
   categorical labels reached scored dimensions (§5).
3. **Did fail-closed behavior remain intact?** Mostly — 0 fabrications, 0 rejections either run — but
   one real defect (§10) causes genuinely-ready evidence to be wrongly withheld, a different failure
   mode than fabrication but still a functional defect.
4. **Did Task 27 cause any false evidence?** Not by itself — the contract layer never fabricates a
   field. But it did make the model's own pre-existing tendency to mis-assign a categorical value more
   consequential, by getting more categorical fields populated at all (§5).
5. **Did more legitimate evidence reach deterministic classifiers?** Yes, confirmed, both companies —
   the `financing_type` and `metric`/`value_type` fixes are real and directly verified against real
   excerpts.

**Across both companies: is the canonical extraction contract validated strongly enough to become the
production evidence interface?** **Not yet, as-is.** The structural/vocabulary half of the contract
works exactly as designed and measurably improved real classifier readiness. Two real, specific,
code-locatable gaps remain: the person_id-ordering defect (§10, blocks legitimate evidence) and the
absence of any semantic-fit check on categorical fields (§5, lets wrong-but-valid evidence through). Both
are narrow and well-understood, not systemic contract-design failures.

## 15. Decision gate

**B — One narrow contract defect remains.**

Not A: classifier-ready rate rose, but a real, confirmed defect (§10) still prevents legitimate evidence
from reaching a deterministic classifier, and a real semantic-accuracy gap (§5) was found — "no serious
regression" does not hold.

Not C: the false categorization found (§5) is not a flaw in the contract's own design (its job —
structural/vocabulary validation — was performed correctly and consistently); revisiting the contract's
own schema/vocabulary would not fix it, since the gap is a different, orthogonal layer (excerpt-to-value
semantic entailment, never attempted anywhere in this engine). The specific, narrow §10 defect is a
pipeline-ordering bug, not a schema-design flaw.

Not D: this experiment was conclusive. Both companies were run, both exercised the relevant Task 27
mechanisms directly and repeatedly (financing_type, metric vocabulary, value_type, categorical value
fields), and produced clear, specific, actionable, code-citable findings — not inconclusive variance.

**The specific defect to fix before integration:** the person_id-backfill-ordering defect (§10) —
routing's applicability check must either run after `finalize_claim()`'s backfill, or itself defer the
person_id-dependent portion of the check until after backfill. **The specific concern to address as an
immediate follow-up, given its severity:** §5's semantic-accuracy gap — recommended as the single next
task below.

## 16. Recommended single next task

**Fix the person_id-backfill/routing-ordering defect (§10), and add a semantic-fit spot-check for
categorical fields whose correct value depends on interpreting what the excerpt actually says (starting
with `retention_signal` and `competitive_structure`, the two kinds this validation found concretely
wrong) — most likely by tightening the extraction prompt with explicit negative examples (adoption ≠
retention; a bare competitor list ≠ a structural read) and, if that alone proves insufficient on a
follow-up run, evaluating whether `validate_candidate()`'s existing grounding check can be extended to
verify the excerpt supports the SPECIFIC categorical value chosen, not merely that some claim it
supports.** Do not attempt this by loosening evidence standards, redesigning methodology, or tuning
scores — both fixes are narrow, code-locatable, and consistent with every prior task's own discipline in
this engine.

## 17. What this task did not do

No code, prompt, schema, query, or budget change was made. No rerun. No fix. No production API
integration. `LIVE_EVALUATION_FISH_AUDIO_001.md` and `LIVE_EVALUATION_NOTION_001.md` are unmodified.
`parameters.py` untouched. No commit, no push.
