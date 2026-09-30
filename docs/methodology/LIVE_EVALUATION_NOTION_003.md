# Live Evaluation — Notion (Run 003)

Task 30 — the final planned pre-integration live validation, against the full Task 27-29 contract
(canonical structured extraction + deterministic canonicalization + semantic-fit validation).
Baselines (unmodified): `LIVE_EVALUATION_NOTION_001.md`, `LIVE_EVALUATION_NOTION_002.md`. Input:
`CompanyAnalysisInput(company_name="Notion", website_url="https://www.notion.com")` — the same canonical
URL reused unchanged across all three runs. Same unmodified `AcquisitionBudget()`, research plan,
pipeline, 6-pillar methodology. Run exactly once; provider-internal retries (configured, bounded)
allowed. **This is not a scoring exercise — the question is whether legitimate evidence survives while
unsupported interpretations do not.**

## 1. Freeze confirmation

Commit `f75e8a3` ("fix: enforce semantic evidence contract"), working tree clean before, during, and
after this run. Confirmed present and active: `fact_contracts.py` (20 kinds), `canonicalization.py`
(wired before routing applicability), `semantic_fit.py` (`UNROUTED_SEMANTICALLY_UNSUPPORTED` status
present in `RoutingStatus`), `routing.py`/`claim_identity.py`/`person_identity.py`/`relevance.py`
unchanged since their own last commits. `parameters.py`/`research_plan.py`/`AcquisitionBudget` defaults
confirmed byte-identical to Notion 001/002's own run (`AcquisitionBudget()` printed and compared
directly). Isolation boundary 3/3. No legacy scoring path reachable. `OPENAI_API_KEY`/`TAVILY_API_KEY`
confirmed present (length-only). **Nothing was changed before, during, or after this run.**

## 2. Run completion and timing

Completed successfully, one run, no fatal errors. 32.82s total (vs. 27.71s / 34.02s for 001/002). Stage
breakdown: source_discovery_and_retrieval ~13s (23 sources, unchanged across all 3 runs),
evidence_extraction the majority of the time (16 claims accepted, 0 rejected).

## 3. Provider measurements

| | Tavily | HTTP | OpenAI (gpt-4.1-mini) |
|---|--:|--:|--:|
| Calls | 12 | 25 | 6 |
| Succeeded | 12 | 23 | 6 |
| Failed | 0 | 2 (HTTP 403, unrelated to the engine) | 0 |
| Retries beyond first attempt | 0 | 0 | 2 (two batches needed a validation-feedback retry, both succeeded) |

Tokens: **44,617 total** (41,743 input / 2,874 output) — comparable to 002's 45,865, both materially
above 001's 32,551 (the same, already-documented longer-system-prompt tradeoff). 6/6 batches truncated
on input, 0 output truncation, 0 content-filter failures, 0 sources excluded for budget — no new
provider-level failure mode.

## 4. Evidence counts and the readiness funnel (the primary measurement)

**16 claims accepted, 0 rejected.**

```
16  accepted, grounded claims
 8  structured        (50.0%  -- 8 carry a structured_fact)
 5  relevant typed     (62.5% of structured -- 3 context_only [team_identity] excluded)
 1  classifier-compatible (20.0% of relevant typed)
 4  semantically not-rejected (1 correctly rejected -- see below)
 0  methodology-usable (0.0% of relevant typed)
```

**Attrition, by cause, at each transition:**

- **structured → relevant typed** (8→5): 3 `team_identity` claims are context-only by design (identity
  resolution, never a scored dimension) — expected, not attrition to a real gap.
- **relevant typed → classifier-compatible** (5→1): 4 `traction_metric` claims (revenue $400M, ARR
  $600M, active users 100M, paying customers 4M) all correctly typed (`metric` exact-match: `revenue`,
  `arr`, `active_users`, `paying_customers`; `value_type="actual"` populated; `amount` a clean, bare
  parseable number in all 4) — **blocked solely by `period_date`**: the real values are `"2024"`,
  `"2025"`, `"2025"`, `"2026-01"` — bare years or year-months, none a fully explicit calendar date.
  Per Task 29's own explicit design, these correctly remain incomplete (never fabricated) rather than
  guessed into a full ISO date. This is the SAME, already-documented, not-yet-closed completeness gap
  Task 28/29 found for Notion before — genuinely not observed to be fixed by canonicalization, because
  it was never in canonicalization's own narrow scope (only fully explicit dates qualify).
- **classifier-compatible → methodology-usable** (1→0): the ONE classifier-compatible claim
  (`competitive_structure="fragmented"`) is ALSO the one claim `semantic_fit.py` correctly rejects (§5).

## 5. The central finding — semantic-fit validation worked, on a genuine, unprompted live case

The model proposed `competitive_structure="fragmented"` from this real excerpt:

> "Notion competitors — View the competitive landscape for Notion, featuring companies like Microsoft,
> Atlassian, and Airtable."

**This is functionally identical to Notion 002's own confirmed false positive** — a bare competitor
list with no structural characterization — reproduced here on a genuinely independent live run, not a
hand-fed fixture. The real routing decision:

```
status: unrouted_semantically_unsupported
reason: kind='competitive_structure': no explicit market-structure characterization found -- a bare
        list of named competitors does not, by itself, establish fragmented/concentrated structure
final_criteria: []
semantic_fit_status: unsupported
```

The claim remains in the ledger, fully grounded, fully provenance-attached (`claim_text`/`excerpt`
unmutated) — only `assessment_criteria` is empty, so `resolve_dimension_evidence()` can never see it for
`competitive_landscape_position`. **This is the single most important positive confirmation of Task 30**:
the exact real-world false-positive pattern recurred on a fresh live run, and was correctly, cleanly
contained.

## 6. Gate-by-gate results

### A. Person ordering

No `founder_experience`/`track_record` claim was extracted this run (not observed). Indirect
confirmation: all 3 real `team_identity` claims (Ivan Zhao, co-founder/CEO) share one `person_id`
(`27177bab9f68d8d1`) across independent restatements, and one candidate's own `role` field is exactly
`"founder"` this run (Notion 002's 3 role strings were all near-misses like "co-founder and CEO" —
this run genuinely produced the exact match) — had a founder_experience claim about him been extracted,
identity confirmation would have succeeded. No inference from a vague title observed anywhere.

### B. Numeric normalization

**Not observed for funding** — no `funding_round` claim was extracted this run at all (the same
acquisition/retrieval-variance pattern already documented for Notion 001 and Stripe). All 4 real
traction `amount` values this run were already clean, bare, parseable numbers (`"400000000"`,
`"100000000"`, `"4000000"`, `"600000000"`) — meaning canonicalization had nothing to fix for amounts this
run. **A real observability limitation, noted honestly**: the saved artifact captures only the FINAL,
post-canonicalization `structured_fact`, so it cannot distinguish "the model produced clean numbers
directly" from "canonicalization silently fixed a shorthand form" — both outcomes are correct, but this
run's telemetry does not itself prove canonicalization fired. Worth adding pre/post canonicalization
telemetry in a future observability pass.

### C. Period/date handling

Confirmed working exactly as designed (§4 above): none of the 4 real `period_date` values this run
were fully explicit, so none were canonicalized, and none were fabricated — correctly incomplete. No
false canonicalization observed anywhere.

### D. Retention semantic fit

**Not observed** — no `retention_signal` claim was extracted this run at all.

### E. Competitive-structure semantic fit

**Confirmed working, directly, on a real live case** — §5 above.

## 7. Semantic rejections (full account)

Exactly one `UNROUTED_SEMANTICALLY_UNSUPPORTED` result this run — detailed in §5. Correct rejection,
not a system failure — the underlying claim (Notion has named competitors) remains a true, grounded,
provenance-attached fact in the ledger; only its overreaching structural interpretation
(`competitive_structure="fragmented"`) is prevented from reaching `competitive_landscape_position`.

## 8. False-negative check

No legitimate retention, competitive-structure, founder, or funding evidence was available to test this
run (none of those kinds appeared with fields that would otherwise have qualified). The 4 blocked
traction_metric claims are NOT false negatives of Task 29's own semantic-fit work — they were blocked by
the pre-existing, correctly-conservative period_date completeness gap, unrelated to the semantic-fit
gate (confirmed directly: `semantic_fit_status` for all 4 is `not_applicable`, not `unsupported`). No
claim was blocked for a reason this validation found to be incorrect.

## 9. Notion 001 / 002 / 003 comparison

| Metric | Notion 001 | Notion 002 | Notion 003 |
|---|--:|--:|--:|
| Runtime (s) | 27.7 | 34.0 | 32.8 |
| Sources retrieved | 23 | 23 | 23 |
| Accepted claims | 23 | 13 | 16 |
| Structured-fact rate | 47.8% | 61.5% | 50.0% |
| Relevant typed claims | 8 | 5 | 5 |
| Classifier-compatible claims | 0* | 2 | 1 |
| **Classifier-compatible rate** | **0.0%\*** | **40.0%** | **20.0%** |
| Semantically-unsupported claims | 2\* | 2\* | **1** |
| **Methodology-usable claims** | **0\*** | **0\*** | **0** |
| Routed claims | 18 | 7 | 8 |
| Published pillars | 1/6 | 1/6 | 1/6 |
| Company Coverage | 9.0% | **17.0%** | 9.0% |
| Company Confidence | High | High | High |
| Company publishable | No | No | No |
| Total tokens | 32,551 | 45,865 | 44,617 |

\* Reconstructed by applying the real, unmodified `check_classifier_readiness()`/`check_semantic_fit()`
to 001/002's preserved `ledger_claims` — labeled reconstructed; `LIVE_EVALUATION_NOTION_001.md`/
`_NOTION_002.md` themselves untouched.

**The most important number in this table is Company Coverage, read correctly.** 002's 17.0% was
achieved by 2 dimensions scoring on evidence this validation confirms was semantically unsupported
(retention_signal on adoption data, competitive_structure on a bare list) — an artificially inflated,
untrustworthy number. 003's 9.0% — numerically lower, matching 001 — is the CORRECT, trustworthy number:
the one candidate that would have repeated 002's exact inflation pattern was this time correctly
contained. **Methodology-usable claims are 0 in all three runs** — Notion has not yet produced a single
piece of evidence that is simultaneously structurally complete AND semantically supported, in any of the
three runs; §4's funnel shows precisely why (period_date incompleteness, and — now correctly — semantic
rejection) rather than leaving this as an unexplained zero.

## 10. Six-pillar results

| Pillar | Published | Strength | Coverage | Confidence | Scored dimensions |
|---|---|--:|--:|---|---|
| Market Opportunity | No | — | 0.0% | Low | none |
| Product & Technology | **Yes** | 8.0 | 50.0% | High | differentiation_claim_corroboration, defensibility_signal |
| Team & Leadership | No | — | 0.0% | Low | none |
| Commercial Traction | No | — | 0.0% | Low | none |
| Execution & Momentum | No | — | 0.0% | Low | none |
| Financial & Funding Signals | No | — | 0.0% | Low | none |

Company Coverage 9.0%, Confidence High, not publishable. Cross-pillar audit: no findings. No overall
company score exists or was computed — unchanged.

## 11. Production-candidate safety invariants, checked directly against this run's artifacts

1. **Unsupported semantic categories cannot affect scoring** — confirmed: the one semantically-rejected
   claim's `assessment_criteria` is empty; `Market Opportunity`'s `competitive_landscape_position`
   dimension shows `availability=UNSCORED...`/no score, not a fabricated `FRAGMENTED` label.
2. **Malformed structure cannot crash evaluation** — confirmed: the run completed end-to-end, all 6
   pillars evaluated, no exception anywhere in `telemetry.stages`/`external_calls`.
3. **Invalid model routing cannot broaden deterministic routing** — confirmed: every `removed_criteria`
   entry in this run's `claim_routing` only ever REMOVES a proposed tag, never adds one beyond what
   `eligible`/the verified fallback permits.
4. **Canonicalization cannot invent evidence** — confirmed: all 4 non-qualifying `period_date` values
   remain their real, un-fabricated bare-year/year-month form; no field appeared in any final
   `structured_fact` that wasn't already present or a pure-representation conversion of an existing one.
5. **Missing data remains missing** — confirmed, §4/§6C.
6. **Company identity/prestige does not affect evidence validation** — `semantic_fit.py`'s own signature
   (verified in Task 29's own tests) cannot read a company name; this run's one real semantic rejection
   fired on content alone.
7. **Duplicates do not create false independence** — no duplicate claim pair arose this run to test
   directly (search variance); unchanged mechanism confirmed intact in Task 29's own regression suite.
8. **Provenance remains attached** — confirmed: every claim in the ledger carries its real
   `source_url`/`source_type`/`excerpt`, including the semantically-rejected one.
9. **Context-only evidence remains non-scoring** — confirmed: all 3 `team_identity` claims route
   `context_only`, never appear in any pillar's `supporting_claim_ids`.
10. **No legacy scoring path participates** — confirmed: isolation boundary 3/3, unchanged since before
    this run.
