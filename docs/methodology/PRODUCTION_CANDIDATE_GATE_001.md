# Production Candidate Gate 001 (Task 30)

The final pre-integration engineering decision for the Evidence Engine, built across Tasks 20-29 and
validated live across Tasks 22, 24, 26, 28, and this task. Full run detail: `LIVE_EVALUATION_NOTION_003.md`.
Baselines: `LIVE_EVALUATION_NOTION_001.md`, `LIVE_EVALUATION_NOTION_002.md`.

**The one question this task answers:** can the legitimate extraction improvements from Tasks 27-29
survive a real live run while the known Task 28 false-positive and lost-evidence paths are eliminated?
**Yes — directly confirmed.**

## 1. The central result

A real, unprompted, independent live run reproduced Notion 002's own exact false-positive pattern
(`competitive_structure="fragmented"` inferred from a bare competitor list) — and Task 29's semantic-fit
gate caught and correctly contained it, live, with no manual intervention:

```
status: unrouted_semantically_unsupported
final_criteria: []
```

No legitimate evidence was blocked anywhere in this run (§8 of the live-evaluation report — the
false-negative check found nothing). **The success criterion this task names — "legitimate evidence
survives, unsupported interpretations do not" — held.**

## 2. Reading Coverage correctly (the trap this task explicitly warns against)

Company Coverage fell from 17.0% (Notion 002) to 9.0% (Notion 003) — the SAME number Notion 001 produced
before any of these fixes existed. **This is not a regression.** 002's 17.0% was built from two
dimensions scoring on evidence this validation confirms was semantically unsupported. 003's 9.0% is the
correct, trustworthy number for what was genuinely, safely usable this run. A system that makes Coverage
LOWER by correctly refusing bad evidence is doing its job — the opposite of what a naive "did Coverage
go up" read would reward.

**Do not choose A because Coverage improved. This gate is not choosing A because Coverage improved — it
fell, correctly, and that is part of the evidence for A.**

## 3. Production-candidate safety invariants — all 10 checked directly (§11 of the live report)

1. Unsupported semantic categories cannot affect scoring — confirmed.
2. Malformed structure cannot crash stage/pillar evaluation — confirmed, full run completed cleanly.
3. Invalid model routing cannot broaden deterministic routing — confirmed, every routing decision this
   run only ever removed a proposed tag.
4. Canonicalization cannot invent evidence — confirmed, no non-qualifying field was ever completed.
5. Missing data remains missing — confirmed (4 non-qualifying period_dates, correctly incomplete).
6. Company identity/prestige does not affect evidence validation — structurally guaranteed by
   `semantic_fit.py`'s own signature (verified in Task 29), and behaviorally confirmed this run.
7. Duplicates do not create false independence — mechanism unchanged, exercised and confirmed correct in
   Task 29's own regression suite (not independently re-exercised by this specific run's data).
8. Provenance remains attached — confirmed, including on the one semantically-rejected claim.
9. Context-only evidence remains non-scoring — confirmed, all 3 `team_identity` claims.
10. No legacy scoring path participates — confirmed, isolation boundary 3/3.

## 4. Coverage of the five primary validation targets, across the full campaign

Not every gate was independently re-exercised by THIS specific run — that is honestly reported, not
glossed over. The cumulative picture across every live run this engine has had since Task 27:

| Gate | This run (Notion 003) | Prior live confirmation |
|---|---|---|
| A. Person ordering | Not observed (no founder/track-record claim extracted) | **Confirmed live**, `LIVE_EVALUATION_FISH_AUDIO_002.md` §5 (the original motivating defect) + Task 29's own exact-shape regression test |
| B. Numeric normalization | Not observed for funding (no funding_round claim); traction amounts already clean | **Confirmed live**, Fish Audio 002's own `"52M"` shape + Task 29's own exact-shape regression test |
| C. Period/date handling | **Confirmed live, this run** — 4/4 non-qualifying periods correctly left incomplete | Consistent with Task 29's own regression coverage |
| D. Retention semantic fit | Not observed (no retention_signal claim extracted) | **Confirmed live**, Notion 002's own exact false positive + Task 29's own regression test with the same real excerpt |
| E. Competitive-structure semantic fit | **Confirmed live, this run** — the central finding, §1 | Also confirmed in Notion 002 (pre-fix) and Task 29's own regression test |

Every one of the five gates has now been validated against REAL, live-extracted data at least once
(either this run or Fish Audio 002/Notion 002), in addition to Task 29's own 59-test regression suite
built directly from those real shapes. No gate remains validated only in the abstract.

## 5. Remaining limitations

### Beta limitations (reduce Coverage/usefulness, fail conservatively — not blockers)

- **Metric period-date completeness.** The single largest driver of this run's 0 methodology-usable
  claims: real source articles frequently disclose a figure without a fully explicit as-of date, and
  canonicalization correctly declines to invent one. A real, open gap — but it fails by withholding,
  never by fabricating, exactly the conservative failure mode this engine has required since Task 15.
- **Funding/market recall variance.** No `funding_round` claim was extracted this run (also true for
  Stripe/Task 26, Notion/Task 26); market-sizing recall remains a known, separately-tracked,
  unaddressed gap (Task 27 item 9, explicitly out of scope for every task since).
- **`team_identity.role` exact-match gap** (documented since Task 27): a realistic role string like
  "co-founder and CEO" does not always exactly equal `"founder"` — though this run happened to produce
  one exact match, the gap remains real and unfixed.
- **A minor semantic/structural precedence nuance**, found while reconstructing Notion 001's own
  historical claims for §9's comparison table: a `competitive_structure` fact with NO `value` at all
  (not merely a wrong one) is currently labeled `UNROUTED_SEMANTICALLY_UNSUPPORTED` rather than
  `UNROUTED_INSUFFICIENT_STRUCTURE`, since the semantic check runs before the structural one and treats
  an empty value as failing to match either accepted vocabulary word. The SAFETY property is identical
  either way (the claim is withheld from scoring regardless), but the diagnostic LABEL is imprecise for
  this one edge case — worth a small precedence fix in a future observability pass, not urgent.
- **No pre/post-canonicalization telemetry.** This run could not directly prove whether canonicalization
  fired on any funding amount, because the saved artifact only captures the final, already-canonical
  `structured_fact`. Worth adding as production observability (this task's own item 6 already
  anticipated this need).

### Production blockers

**None identified.** No crash, no fabrication, no scoring impact from unsupported evidence, no legacy
path reachable, no broadened routing, anywhere in this run or in Task 29's exhaustive regression
coverage of the real historical failure shapes.

## 6. Final decision

### **A — Evidence Engine v1 Candidate**

The evidence interface is sufficiently trustworthy to begin controlled production integration. This does
not claim the methodology or acquisition layer is complete or perfect — Coverage remains low, several
real completeness gaps remain (§5) — it claims the known DANGEROUS failure modes (fabricated categorical
values reaching a score, a crash, broadened routing, legacy-path leakage) are contained, and every
remaining limitation fails conservatively (withholding, never inventing). The single clearest piece of
evidence for this: the exact real false-positive pattern that motivated Task 29 recurred on an
independent live run and was correctly caught, with Coverage correctly falling rather than staying
artificially inflated.

## 7. Proposed candidate identifier

`evidence-engine-v1-candidate.1`

This is a proposed, documentation-only identifier — no code was changed to apply it. `parameters.py`
already carries its own `PARAMETER_VERSION = "evidence_engine.v1-provisional-11"` constant; a future
integration task can align a real version string with this identifier through that existing mechanism
(a pure label change, no behavior change) rather than inventing a second, parallel versioning concept.

## 8. Recommended next task

**Controlled VentureGPS Product Integration.** Per this task's own instruction: place the new Evidence
Engine behind an explicit boundary/feature flag, preserve the existing legacy production flow
unmodified and fully reachable, and do not delete or disable any existing behavior. Integration itself
is explicitly NOT performed in this task.
