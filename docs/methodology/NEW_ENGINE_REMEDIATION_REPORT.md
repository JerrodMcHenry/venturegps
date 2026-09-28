# VentureGPS Evidence Engine — Live-Evidence Remediation Report (Task 12)

**Status: implemented and tested. `docs/methodology/NEW_ENGINE_LIVE_EVALUATION.md` (Task 11) is
left unchanged, exactly as instructed** — this report stands alongside it as the record of what
was fixed and what changed. Parameter version `evidence_engine.v1-provisional-4`.

## 0. What changed, in one table

| # | Weakness (Task 11) | Fix | File(s) |
|---|---|---|---|
| 1 | Exact `source_url` match forced two distinct real facts (Notion's API + integration gallery) into one | `assess_independence()` now decides claim identity from content (text similarity) only; source URL is never consulted | `provenance.py` |
| 2 | `determine_stage()` read raw claims directly — dispute/staleness-blind | Routed through `resolve_dimension_evidence()`, exactly like every scored dimension | `stage.py` |
| 2 | "tender offer" and YC batch codes unrecognized | Keyword list expanded (`tender offer`→Growth; `yc s`/`yc w`/`y combinator`→Pre-Seed) | `stage.py` |
| 3 | Stale-only evidence reported identically to genuine absence, for Classified dimensions | Explicit pre-classification stale check, mirroring the existing Computed-dimension pattern | `pillars/product_technology.py` |
| 3 | Anonymous forum comments and bylined reporting shared one reliability weight | New `SourceType.COMMUNITY_COMMENTARY` (weight 0.5, between company disclosure and attributable reporting) | `models.py`, `parameters.py` |
| 4 | HIGH confidence unreachable — cause not yet diagnosed | Investigated (no threshold changed) — §3 below | *(no code change)* |

**Not changed, per explicit constraint:** `MIN_PILLAR_COVERAGE_PCT`, `MIN_SCORED_DIMENSIONS_PER_PILLAR`, every stage-tiered label score, `PROVENANCE_DUPLICATE_SIMILARITY_THRESHOLD`/`_UNKNOWN_`, `CONFIDENCE_MIN_RELIABILITY_FOR_HIGH`/`_MIN_CORROBORATION_GROUPS_FOR_HIGH`. No numerical parameter was adjusted to make any company score better or worse.

**A narrow, documented data correction, not a re-write of the evidence:** two `structured_fact` values in `live_research/stripe.py` and `live_research/bullet.py` were changed from a manually pre-normalized workaround value (e.g. `"late-stage tender offer"`) back to the actual raw disclosed term (`"tender offer"`, `"YC S26"`) — because fix #2 removes the need for that manual workaround, and testing the fix meaningfully requires feeding it the real term rather than my own prior hand-normalization. Two claims in `bullet.py` had their `source_type` corrected from `INDEPENDENT_REPORTING` to the new `COMMUNITY_COMMENTARY` for the same reason (fix #3 exists specifically to apply to them). **No URL, excerpt, date, publisher, or dispute/support-status was altered anywhere.** Full diffs are in git; nothing else in `live_research/` changed.

---

## 1. Fix details

### 1.1 Evidence deduplication (item 1)

`provenance.py::assess_independence()` no longer contains the `if a.source_url == b.source_url:
return LIKELY_DUPLICATE` branch. Claim identity is decided purely by content (Jaccard token
overlap over `excerpt`/`claim_text`) — the same check that already correctly identifies a
genuine restatement (near-identical wording) regardless of whether it shares a URL with the
original. Regression tests: `test_identical_source_url_with_dissimilar_text_is_independent`,
`test_identical_source_url_with_near_identical_text_is_still_a_duplicate` (the legitimate
same-URL-restatement case is still caught, correctly, by text similarity alone), and
`test_technical_depth_reaches_substantial_when_distinct_facts_share_one_source_url` — a direct
reproduction of Notion's exact scenario (`test_provenance_verification.py`).

### 1.2 Stage-evidence admissibility (item 2)

`stage.py::determine_stage()` now builds an `EvidenceLedger` scoped to the company and calls
`resolve_dimension_evidence()` for the `stage_signal` dimension before reading any
`structured_fact` — disputed and stale stage-signal claims are excluded exactly as they would be
for any scored dimension. Nine new regression tests
(`test_stage_admissibility.py`) cover: a disputed pair alone resolving to `Undetermined`; a
non-disputed signal correctly winning over a disputed one; stale exclusion; a fresh signal
winning over a stale one; the two new keyword categories (`tender offer`, YC batch codes,
including a false-positive-safety check); and that zero or only-inadmissible evidence never
gets guessed into a real stage.

### 1.3 Evidence-status reporting (item 3)

`pillars/product_technology.py::_evaluate_classified_dimension()` gained a stale-only
pre-check (mirroring the Computed dimension's existing `_reason_for_absence` logic) that reports
`UNSCORED_STALE` before ever reaching the classifier, when nothing tagged is admissible but
something stale exists. A new `SourceType.COMMUNITY_COMMENTARY` (in `models.py`, included in
`INDEPENDENT_SOURCE_TYPES` — still independent of the company — but with its own, lower
`SOURCE_RELIABILITY_WEIGHT` of 0.5 in `parameters.py`) distinguishes an anonymous public comment
from attributable reporting. Disputed-claim auditability was reconfirmed as an explicit, tested
property (`test_disputed_claims_remain_in_the_ledger_for_audit`) rather than left implicit. Seven
new regression tests in `test_evidence_status_reporting.py`.

---

## 2. Before / after comparison (all five companies, identical Task 11 evidence)

| Company | Metric | Before (Task 11) | After (Task 12) | Changed because |
|---|---|---|---|---|
| **Notion** | Stage | Series B+ | **Undetermined** | Both stage-signal claims are genuinely disputed (§3.1 of the Task 11 report); the pre-fix code read them anyway. Neither non-disputed nor fresh alternative exists in this evidence set, so `Undetermined` is the honest result — not a defect, the fix working as intended. |
| | Technical Depth | Unscored (rejected) | **SUBSTANTIAL, 9.0** | The API claim and the integration-gallery claim shared one URL and were wrongly folded (item 1's bug); now correctly counted as 2 of 3 distinct facts, clearing the ≥3 floor. |
| | Defensibility | Unscored (`no_evidence`) | Unscored (**`stale`**) | Same underlying fact (the one real source is ~4 years old) — now correctly labeled. |
| | Differentiation | 7.0 (Series B+ tier) | **8.0** (Undetermined → most-permissive tier) | A direct consequence of the stage change above, not a separate fix — `CORROBORATED` at Undetermined uses the most-permissive (early-tier) band per spec Part 4.3, unchanged design behavior. |
| | Coverage / Strength / Confidence | 50% / 7.0 / Medium | **75% / 8.0 / Medium** | Both direct consequences of the two fixes above. |
| **Linear** | All fields | 7.25 / 100% / Medium, Series B+ | **Unchanged** | No stale, disputed, or shared-URL evidence existed for Linear — a clean confirmation of no regression. |
| **Stripe** | Stage | Growth (from a manually pre-normalized value) | **Growth** (from the real, unmodified "tender offer" term) | The keyword-recognition fix makes the manual workaround unnecessary; same correct outcome from honest data. |
| | All other fields | 5.88 / 100% / Medium | **Unchanged** | No stale/disputed/shared-URL evidence for Stripe. |
| **Fish Audio** | All fields | 7.17 / 75% / Medium, Seed | **Unchanged** | No stale/disputed/shared-URL evidence for Fish Audio. |
| **Bullet** | Stage | Pre-Seed (from a manual value) | **Pre-Seed** (from the real "YC S26" term) | Same keyword-recognition fix as Stripe. |
| | Product Existence | Scorable, 7.0 | **Unscored (`uncorroborated`)** | See §2.1 — a genuine, non-parameter-tuned cascading consequence of fix 3, not a targeted change to this dimension. |
| | Publishable / Strength / Coverage / Confidence | Yes / 6.75 / 50% / Low | **No / WITHHELD / 25% / Low** | Direct consequence of the Product Existence change: only 1 of 4 dimensions now scores (Technical Depth alone), failing both gates. |

### 2.1 Bullet: the one result that changed for a reason worth explaining in full

Bullet's only Product Existence evidence was an anonymous Hacker News commenter's account
("switched over to using primarily Bullet"). Before this remediation, that claim was tagged
`INDEPENDENT_REPORTING` — a source type this pillar's `_OBSERVABLE_SOURCE_TYPES` set (Computed
dimension logic, `pillars/product_technology.py`) already treats as sufficient to establish an
independently-observable artifact. After correcting its source type to the new
`COMMUNITY_COMMENTARY` (item 3's own fix — an accurate correction, since an anonymous comment is
not the same kind of independent source `_OBSERVABLE_SOURCE_TYPES` was designed around), it no
longer qualifies, and Product Existence & Maturity correctly falls to `UNSCORED_UNCORROBORATED`.
With only Technical Depth Signal left scorable (25% coverage, 1 dimension), Bullet's entire
pillar result flips from publishable to withheld.

**This is not a parameter tuned to produce this outcome** — `_OBSERVABLE_SOURCE_TYPES` itself
was not touched anywhere in this remediation; this is the correct, faithful consequence of
fixing item 3 exactly as specified, surfacing on the one company in this roster whose evidence
happened to depend on that specific gap. It is flagged here, explicitly, as an open question for
a future phase rather than resolved unilaterally in this task: **should `COMMUNITY_COMMENTARY`
ever satisfy `_OBSERVABLE_SOURCE_TYPES`** (an anonymous account of actually using a live product
is still, arguably, evidence an outside party could in principle check) **or is excluding it
correct** (no verifiable identity behind the claim)? This was not decided here — deciding it
either way without real calibration data would itself be exactly the kind of untuned-but-still-
arbitrary parameter choice this task's constraints caution against. `_OBSERVABLE_SOURCE_TYPES`
remains unchanged pending that decision.

---

## 3. Confidence-calibration investigation (item 4)

**HIGH confidence remained unreached in every one of the 18 scored dimension results across all
five companies, before and after this remediation.** Investigated directly against the real,
scored dimensions (not a hypothesis) — three distinct, separable causes were found, illustrated
with actual numbers from this evaluation's own data:

**Cause 1 — the source-reliability model, structurally, for two specific dimensions.** Product
Existence & Maturity's admissible evidence is, by the dimension's own design (spec Part 3.3),
almost always `product_documentation` (weight 0.8) or better — a product's own docs are the most
natural evidence that it exists. Linear's Technical Depth Signal (post-fix) cites three claims,
all `product_documentation` (0.8 each) → average reliability exactly 0.8, below the 0.9 floor —
**even with 3 well-corroborated distinct facts, comfortably clearing the ≥2-groups requirement,
this dimension cannot reach HIGH under the current weights, regardless of corroboration.** Notion's
post-fix Technical Depth Signal (2× 0.8, 1× 1.0 = average 0.867) shows the same pattern.

**Cause 2 — the evidence-requirement (corroboration count), for a different set of dimensions.**
Stripe's and Fish Audio's Differentiation Claim Corroboration each cite exactly **one**
independently-sourced claim — reliability 1.0, as high as this scheme allows, but
`distinct_groups = 1`, below `CONFIDENCE_MIN_CORROBORATION_GROUPS_FOR_HIGH`'s floor of 2. Here
the binding constraint is not reliability at all (a single perfectly-reliable source still
cannot reach HIGH) but this evaluation's own research depth: no second independent source for
Stripe's or Fish Audio's differentiation was found (or, for Stripe, specifically sought within
this evaluation's time budget — Task 11 §5.4 already flagged this).

**Cause 3 — threshold calibration, assessed but not adjusted.** The 0.9 reliability floor is not
unreachable in the abstract: three citations of `(1.0, 1.0, 0.8)` would average 0.933, clearing
it. **What this evaluation actually shows is that neither cause 1 nor cause 2 is a sign the
threshold itself is miscalibrated** — real dimensions in real evaluations frequently draw most of
their weight from one company-owned documentation source (structurally, not by chance) or have
only one available independent citation (a research-depth limitation, not a methodology one).
Whether 0.9/2-groups is the *right* bar, given how real evidence for this pillar's specific
dimensions actually distributes, is exactly the kind of question `docs/methodology/
NEW_ENGINE_CALIBRATION.md`'s real, larger cohort is for — **not adjusted here**, per the task's
explicit instruction not to lower thresholds to manufacture a HIGH result.

**Conclusion:** HIGH confidence's non-attainment in this evaluation is fully explained by causes
1 and 2 acting on real, specific dimensions — not by an unreachable or broken threshold. No
parameter was changed as a result of this investigation.

---

## 4. Test results

**95 tests across 9 files, all passing** (up from 77 across 7 files — 18 new regression tests:
9 in `test_stage_admissibility.py`, 7 in `test_evidence_status_reporting.py`, 2 in
`test_provenance_verification.py` reproducing/reversing the exact Notion scenario). One existing
test (`test_identical_source_url_is_a_likely_duplicate_regardless_of_text`) was renamed and
re-asserted for the deliberately-reversed correct behavior — the same "update the test to reflect
the deliberate new behavior" discipline used throughout this project whenever a fix intentionally
supersedes prior behavior.

Legacy regression re-confirmed unaffected: `test_pipeline_concurrency.py` (14/14),
`test_methodology_v2_1.py` (21/21). Isolation boundary re-verified (zero imports outside
`app.evidence_engine`).

---

## 5. Remaining limitations

- **The `_OBSERVABLE_SOURCE_TYPES` question (§2.1)** is explicitly left open, not resolved, per
  the reasoning given there.
- **Confidence's HIGH threshold remains genuinely untested at its actual boundary** — this
  evaluation's real dimensions landed either comfortably below the reliability floor (cause 1) or
  limited by a single citation (cause 2); no real dimension came close enough to 0.9/2-groups to
  actually stress-test where the line falls, echoing Task 11 §5.2's same gap for the
  similarity thresholds.
- **Five real companies remains five real companies** — this remediation fixes the mechanisms
  the live evaluation exposed; it does not and cannot constitute the larger calibration cohort
  `NEW_ENGINE_CALIBRATION.md` still describes as the real path to setting final numbers.
- **The manual `structured_fact` correction (§0)** was a one-time, explicitly-documented,
  narrowly-scoped data fix tied directly to this task's own keyword-recognition improvement —
  not a precedent for freely editing `live_research/` data in future tasks.

## 6. Readiness for the next milestone

The six weaknesses Task 11 identified are each fixed with a targeted, tested change and a
direct, explained before/after result — including one substantive, honestly-surfaced side effect
(Bullet, §2.1) rather than a uniformly rosy set of improvements. Combined with Task 11's own
finding that the underlying traceability/withholding/dispute mechanisms were already sound, this
supports proceeding to the next milestone (a larger real calibration pass and/or implementing
additional pillars) — with the `_OBSERVABLE_SOURCE_TYPES` question (§2.1) and the confidence-
threshold boundary gap (§5) flagged as the two specific open items worth resolving with real
calibration data before or during that expansion, not as blockers to starting it.
