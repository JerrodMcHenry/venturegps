# Robotics Coverage Report — Increment 18.6

Real, read-only audit against the isolated `venturegps_v2_dev_1801` database, run 2026-09-23. No data was
modified to produce this report. Everything below is queried live from `v2.*`; nothing is estimated or
inferred beyond what a query directly returned.

## Phase 1 — Coverage audit

### Real vs. test data (must be read separately)

The database currently holds **8 canonical companies**, **7 markets**, and **6 taxonomy versions**. Exactly
**one** of each is real:

| | Real | Test fixture |
|---|---|---|
| Market | `robotics` (`fd5740bb-0c77-43a4-a654-9b1580c8ec31`) | 6× `zztest-v2-review-robotics-<marker>` (from `app/tests/test_v2_review_api.py` runs) |
| Taxonomy version | `venturegps_taxonomy.v1` | 5× `zztest_v2_review*.v1` |
| Canonical company | **Gecko Robotics, Inc.** (`b19376f7-8549-40db-828b-4444a4176f28`), classified `robotics`/primary by `admin:jerrod` | 7× "Zztest V2 Review Robotics Inc. `<marker>`", each classified into its own zztest market, all decided by the synthetic test identity `admin:zztest_v2_review_admin` |
| Source | `sec_edgar_form_d`, `sec_edgar_form_d_http`, `media_funding_announcement` (all `is_test=false`) | `zztest_v2_review_synthetic_*` (`is_test=true`, marked explicitly) |

**One thing to flag rather than silently work around**: `zztest_v2_review_source` (the fixture source
`app/tests/test_v2_review_api.py` uses for most of its scenarios) is **not itself marked `is_test`** — only
the two newer `..._synthetic_*` sources are (added specifically to test the `is_test` filter in Increment
18.5). Its candidates are still trivially distinguishable by name (`Zztest V2 Review ...`) and were excluded
from every count below by name and by source, but if this database is ever used for a real publication
decision, mark it too: `mark-source-test --source-key zztest_v2_review_source --as admin:<you> --confirm`.

### Canonical Robotics coverage: one company

**Gecko Robotics, Inc.** — the only canonical, Robotics-classified company.

- **Financing**: one canonical `FinancingEvent` (`e4a1e27f-89b2-4189-bdb5-1b00168cc811`), with:
  - `verified_round_amount`: **USD $125,000,000.00** — accepted from the **media announcement candidate's**
    `announced_round_amount`, per the domain rule (never from Form D's `offering_amount`/`amount_sold`).
  - `filing_date` 2025-06-11, `first_sale_date` 2025-05-14 (both from the Form D candidate).
  - **No `stage` and no `financing_type` accepted** — the candidates may not have proposed them with usable
    evidence, or the human reviewer chose not to accept them; either way, this is a real gap, not a display
    issue.
- **Identifiers**: **none** — no domain or website URL is recorded for the canonical company.

### Pending candidates from real (non-test) sources: 5 company, 0 financing

Both financing candidates from real sources are already resolved (`create_event`, then `attach_to_event` —
these two decisions are exactly what produced the FinancingEvent above). All remaining work is on the
**company** side:

| id | Proposed name | Source | Accession | Status |
|---|---|---|---|---|
| 1 | Gecko Robotics, Inc. | `sec_edgar_form_d` (manual, Increment 18.2) | 0001747029-25-000002 | **resolved** — `create_company` |
| 2 | Gecko Robotics, Inc. | `sec_edgar_form_d_http` (automated, Increment 18.3) | 0001747029-25-000002 | **pending** |
| 3 | HII Gecko Robotics Series I, a Series of Gecko Robotics, LLC | `sec_edgar_form_d_http` | 0002082041-25-000004 | **pending** |
| 4 | Soma Capital Gecko Robotics SPV, LP | `sec_edgar_form_d_http` | 0001903315-22-000001 | **pending** |
| 30 | Corindus Vascular Robotics, Inc. | `sec_edgar_form_d_http` (Increment 18.5's real demo) | 0001713695-19-000004 | **pending** |

### Duplicate / ambiguous entities found

- **Candidate #2 is the same real company as the already-canonical #1**, collected a second time via the
  automated HTTP source (a *different* `source_key`, so the write-layer's own dedup — keyed on
  `(source_id, source_record_identifier)` — correctly does **not** merge them; they are legitimately two
  distinct candidate rows citing the same real filing through two different collection paths). **The
  review UI's identity-match warning will not catch this**: neither candidate proposes any identifier (see
  below), so `find_company_ids_by_identifier` has nothing to match on. This has to be caught by a human
  reading the name, not the tooling — flagged here explicitly for that reason. The correct action is
  **attach**, not **create**.
- **Candidates #3 and #4 are investment vehicles (SPVs), not the operating company.** Each is a *separate
  legal issuer* that filed its own Form D (distinct accession numbers) — "HII Gecko Robotics Series I" and
  "Soma Capital Gecko Robotics SPV, LP" are special-purpose entities formed to invest *in* Gecko Robotics,
  not Gecko Robotics itself. Proposing them as canonical companies would misrepresent VentureGPS's own
  identity graph. See Phase 2 for the source-strategy stance on this.
- **Candidate #30 (Corindus Vascular Robotics, Inc.) has no evident relationship to any existing candidate or
  company** — a genuinely new name, not a duplicate.

### Missing evidence, structurally

**No company candidate from any Form D source has ever proposed an identifier** (`v2.company_candidate_identifier`
is empty for all 5 real candidates). This is not a bug to fix quietly — it's inherent to the source:
`app/v2/tools/form_d_company_proposer.py` documents it directly (`"NO identifiers -- Form D's own schema has
no website/domain field"`). **Identity evidence (a domain or canonical URL) can only come from a different
source type** — a company's own announcement or website, or investor coverage that states it — never from
Form D alone. This directly shapes Phase 2's source strategy below.

### Source freshness

All five real observations were **collected today** (2026-09-23, `observed_time`/`recorded_time` all within
the same session) — freshness is not yet a real constraint on this dataset; it will become one as soon as
this coverage effort spans more than one collection run. `docs/v2/RUNBOOK_18_5.md`'s `list-collection-runs`
is the mechanism to track it going forward.

---

## Phase 2 — Source strategy for Robotics

**Evidence tiers, and what each may and may not establish:**

1. **SEC Form D (primary, legal/offering evidence)** — `sec_edgar_form_d_http` (automated) /
   `sec_edgar_form_d` (manual). Establishes: the issuer's legal name (candidate identity proposal), the
   filing's `offering_amount` and `amount_sold` (**never** treated as an announced round amount — the
   domain has no path that would let them become `verified_round_amount`; only a candidate's own
   `announced_round_amount` can), `filing_date` and `first_sale_date`. **Never establishes**: a domain/
   identifier, a financing stage in the VC sense (Form D has no such field), or a discovery-time company/
   industry category as a classification.
2. **Official company and investor announcements (primary, financing + identity)** —
   `media_funding_announcement` (or a comparable new source, manually uploaded or collected). Establishes:
   `announced_round_amount` (the *only* path to `verified_round_amount`, and only under human authority),
   business description text for classification evidence, and — critically — the identifiers Form D
   structurally cannot provide (a company's own domain, stated in its own announcement).
3. **Reputable reporting (secondary, corroboration only)** — never the sole source for a financing amount or
   a classification; used to corroborate or add missing dates/stage language already evidenced elsewhere,
   never to originate a fact that appears nowhere else.

**Classification discipline**: a company is **never** classified into Robotics because a discovery query
found it, because "robotics" appears in its name, or because of an SEC industry code on the filing. Primary
classification requires the same evidence-and-human-decision path every other 18.4/18.5 classification used:
a human reviewer reads real business-description evidence (from an announcement or the company's own
material) and explicitly calls `classify_company` with `role=primary`. Nothing here changes that boundary or
proposes automating it.

**SPV / investment-vehicle handling**: an entity whose proposed name states it is a *fund, series, or SPV
formed to invest in* another named company (e.g. "... Series of X, LLC", "... SPV, LP") is a strong signal
that the candidate names an investment vehicle, not an operating company. This report does **not** propose
auto-rejecting on a name pattern (that would be exactly the kind of "infer from a name" shortcut this
increment explicitly rules out) — it proposes that a human reviewer treat "does the proposed name describe an
investment vehicle rather than an operating business" as an explicit, first checklist item before deciding
`create`/`attach`/`reject`/`defer`, informed by reading the underlying filing text.

**What identity evidence Robotics candidates specifically need**: at least one `domain` or `website_url`
identifier, sourced from a non-Form-D observation (an announcement, or the company's own site), before an
`attach` decision can be trusted to actually catch a duplicate automatically in future review (see the #1/#2
finding above) — until then, duplicate detection for Form-D-only candidates stays a manual, name-reading step.

---

## Phase 5 — Controlled scheduling design (not activated)

Reuses `run-collection` (Increment 18.5) exactly as documented in `docs/v2/RUNBOOK_18_5.md` — nothing new to
build. A deployment-ready, disabled-by-default configuration for Robotics specifically:

```cron
# Robotics discovery, twice daily, bounded to 10 filings per run. DISABLED unless V2_COLLECTION_ENABLED=1 is
# set in the environment this cron entry actually runs under -- setting it is a separate, explicit deployment
# step, never implied by adding this entry.
0 8,20 * * * V2_COLLECTION_ENABLED=1 /path/to/venv/bin/python -m app.v2.tools.cli \
  --database-url "$V2_DATABASE_URL" run-collection \
  --job-name robotics --query "robotics" --max-filings 10 --trigger-type scheduled \
  >> /var/log/venturegps/robotics-collection.log 2>&1
```

- **Disabled by default**: the cron *entry* above is inert without `V2_COLLECTION_ENABLED=1` in its own
  environment — adding the entry is not the same action as enabling it, by design (see `RUNBOOK_18_5.md`).
- **Bounded**: `--max-filings 10` (well under the hard cap of 25); twice daily, not continuous.
- **Concurrency**: the existing `uq_collection_run_one_active_per_job` lock, scoped to `job_name="robotics"`
  — a slow run is never joined by a second one; unaffected by, and never contends with, any other job name.
- **Lease recovery**: default 900s lease (generous for a 10-filing run); `run-collection` recovers any
  expired lease for this `job_name` automatically before acquiring it, and `recover-collection-runs
  --job-name robotics` is available standalone.
- **SEC access limits**: unchanged from Increment 18.3 — `MAX_DISCOVERY_RESULTS=25` (this config requests
  well under that), the same bounded-retry/rate-limit/redirect/SSRF controls in
  `docs/v2/SEC_COLLECTION_SECURITY.md`, all untouched by this increment.
- **Job history**: `list-collection-runs --job-name robotics` (CLI) or the Collection Operations tab
  (`job_name` isn't currently a UI filter — the tab shows the 20 most recent runs across all jobs, which is
  sufficient at this volume; add a job filter to the UI if/when multiple scheduled jobs are running
  concurrently in practice).
- **Manual disable**: remove `V2_COLLECTION_ENABLED` from the cron environment (or delete the crontab entry).
  No code change needed either way.
- **Recovery procedure**: `recover-collection-runs --job-name robotics`, then inspect
  `list-collection-runs --job-name robotics --limit 5` for the `interrupted` row's `failure_detail`.

**Not done, per the explicit constraint**: no cron entry was installed, no environment variable was set on
any real host, no worker process was started.

---

## Phase 6 — Coverage acceptance criteria (for publishing real Robotics intelligence)

Publication readiness is **per-company** for identity/financing/classification, and **per-market-metric** for
anything Capital Signal produces. Meeting the per-company bar does not by itself make a *metric* ready — see
the last row.

| Dimension | Criterion |
|---|---|
| **Evidence completeness** | Every accepted canonical fact (name, each financing fact, classification) traces to a specific, byte-verified evidence excerpt with real provenance (source + accession/record id) — never a fact with no citable evidence, matching the domain's own existing invariant (there is no path to accept a fact without one). |
| **Identity resolution** | At least one `domain` or `website_url` identifier recorded on the canonical company, sourced from a non-Form-D observation. (Gecko Robotics currently has **zero** — see Phase 1 — so it does not yet meet this bar itself.) |
| **Financing verification** | `verified_round_amount` present only where independently corroborated (an announcement's `announced_round_amount`, never a bare Form D `offering_amount`/`amount_sold`) — already structurally enforced; readiness here means the corroborating source was actually reviewed by a human, not merely that the domain *would* refuse the alternative. |
| **Market classification** | An explicit `primary` classification exists, made by a human reading real business-description evidence — never inferred from discovery query, name, or SEC code (Phase 2). |
| **Duplicate handling** | No two canonical companies represent the same real-world entity; every known SPV/investment-vehicle candidate for that company has been explicitly `reject`ed or `defer`red (not left silently pending) so it cannot be mistaken for coverage. |
| **Data freshness** | The evidence behind any published fact is dated, and its collection/observation time is visible — "freshness" itself has no fixed staleness threshold yet; this increment does not invent one, since no company here has been re-observed over time to know what a meaningful threshold would be. |
| **Review backlog** | Zero *unresolved* company candidates naming a real, credible operating company for the market being published — a candidate correctly `reject`ed or `defer`red does not block publication; one still sitting unresolved does. |
| **Operational failure state** | No `collection_run` for the relevant `job_name` is currently `interrupted` without an explanation reviewed (i.e., `recover-collection-runs` has been run and its output read, not just left for the lock to eventually clear itself). |
| **Capital Signal specifically** | **A market's Capital Signal is not meaningful from one company or one financing event.** Per the existing, unmodified methodology (`docs/v2/CAPITAL_METHODOLOGY.md`), each metric needs **≥3 non-zero historical 30-day windows** to be trusted at all — below that it is `insufficient_data`, by design, never silently downgraded to "stable". Robotics currently has exactly one verified financing event; Capital Signal for this market should be expected, and presented, as `insufficient_data` until real coverage and real time have both accumulated. This increment does not change that methodology and does not claim otherwise. |

Today, against these criteria: Gecko Robotics has real, evidenced financing and a real human classification,
but **fails** the identity-resolution bar (no identifier) and Robotics as a market **fails** the Capital
Signal bar (one event, not three windows). Coverage is real but not yet publication-ready by this report's
own criteria — stated plainly, not rounded up.

---

## Phase 7 — Tests and remaining limitations

No application code changed in this increment (audit, strategy and documentation only) — re-verified, not
re-built:

- `python -m pytest app/v2/tests/architecture/` — **894 passed**.
- `V2_TEST_DATABASE_URL=.../venturegps_v2_test_1802 python -m pytest app/v2/` (attested disposable DB only,
  never `venturegps_v2_dev_1801`) — **3,270 passed**.
- `venturegps_v2_dev_1801` inspected read-only throughout this report; no row was created, changed, or
  deleted to produce it.

**Remaining limitations**:
- Identity-match detection cannot catch a same-company duplicate when neither candidate proposes an
  identifier (the #1/#2 Gecko Robotics case) — a human-review checklist item, not a tooling gap this
  increment closes.
- No second real source type (an announcement or company-site collector) exists yet to supply identifiers or
  `announced_round_amount` for a *new* company the way Gecko Robotics' financing was corroborated — that
  corroboration was itself collected manually in Increment 18.2, not through any automated pipeline.
- `zztest_v2_review_source` remains unmarked `is_test` on this database (documented above, with the exact
  command to fix it) — left as-is per this increment's "no automatic reclassification" constraint from 18.5.
- Freshness has no defined staleness threshold yet (see Phase 6) — everything observed so far was collected
  in a single day.
