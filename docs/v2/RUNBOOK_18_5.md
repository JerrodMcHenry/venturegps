# Runbook: Increment 18.5 — Scheduled SEC Collection & Review Queue Operations

Builds on `docs/v2/RUNBOOK_18_2.md` and `docs/v2/RUNBOOK_18_3.md` (read both first). This increment adds
**no new collection or extraction logic at all** — every filing still goes through the exact same
`app.v2.tools.sec_form_d_collector` + `app.v2.tools.cli._collect_and_extract_one` pipeline Increment 18.3
built and tested. What's new is purely operational:

1. A **bounded, externally-triggered** way to run that pipeline repeatedly (`run-collection`), with a
   database-enforced lock against overlapping runs and a persistent job-history record.
2. **Review-queue operations** on top of the existing internal review interface: pagination, filters, search,
   a way to keep synthetic/test evidence out of ordinary review, and a safe, explicit classification for
   evidence-integrity failures instead of a generic 500.
3. A minimal **collection operations UI** (a third tab in `/admin/v2-review`) showing recent runs and the
   review backlog, with an optional, admin-gated manual trigger.

## What this is, and is not

- **Not a scheduler.** There is no long-running process, no `while True: sleep()` loop anywhere in this
  codebase, no Celery/Redis/APScheduler/cron dependency (the architecture test suite's
  `worker_framework_prefixes` rule structurally forbids importing any of those). `run-collection` does one
  bounded run and exits. Scheduling is an **external** cron entry (or Render Cron Job, or `launchd`, or
  anything else that can run a shell command on an interval) that invokes the CLI.
- **Still no automatic canonical promotion.** Nothing in this increment creates a Company, a FinancingEvent,
  or a classification — scheduled or manual. Collection still only ever produces untrusted candidates for a
  human to review through the existing `/admin/v2-review` interface or the `decide-company`/`decide-financing`
  CLI commands.
- **Still no AI extraction.** Same deterministic Form D parser and proposers as every prior increment.
- **The manual trigger runs synchronously, in-request.** There is no background job queue (a deliberate
  decision — see above), so `POST /admin/v2-review/collection-runs/trigger` performs the real, bounded
  (≤25 filings) collection **while the HTTP request is open**. The frontend gives this call a 120s timeout.
  For anything larger or more frequent than an occasional manual nudge, use the CLI on a real interval instead.

## Enabling and disabling scheduled collection

**Disabled by default, everywhere, always** — this is enforced in code, not just left undocumented:

```python
# app/v2/tools/cli.py
def _collection_is_enabled(args) -> bool:
    return bool(args.enabled) or os.environ.get("V2_COLLECTION_ENABLED") == "1"
```

`run-collection` checks this **before** acquiring the run lock or making any network call. Without one of the
two opt-ins below, it prints `{"status": "disabled", ...}` and exits 0 — a safe no-op a cron job can hit
without erroring.

To actually enable it, either:
- pass `--enabled` explicitly on each invocation, or
- set `V2_COLLECTION_ENABLED=1` in the environment the cron job runs under.

Nothing in this codebase sets `V2_COLLECTION_ENABLED` automatically in any environment (dev, preview, or
production) — that is a deployment-level decision the operator makes explicitly, outside this codebase.

## Running collection manually

```bash
DB="postgresql+psycopg2://<host>/<isolated-dev-db>"   # never the shared preview or production database

# One bounded run: discover (bounded, ≤25), collect + extract each result, record job history, exit.
python -m app.v2.tools.cli --database-url "$DB" run-collection \
  --query "robotics" --max-filings 10 --trigger-type manual --as admin:yourname --enabled

# Dry run: discovers and reports what would be collected; no network fetch of any filing, no candidates.
python -m app.v2.tools.cli --database-url "$DB" run-collection \
  --query "robotics" --max-filings 10 --as admin:yourname --enabled --dry-run
```

`--trigger-type manual` requires `--as ACTOR_ID` (same shape as every other human-decision command, e.g.
`admin:jerrod`) — this is recorded verbatim as the run's `triggered_by`, purely for the job-history record; it
does **not** grant any promotion authority (collection never promotes anything regardless of who triggered it).

### Scheduling it for real (external cron)

```cron
# Every 30 minutes, only when explicitly enabled via the environment:
*/30 * * * * V2_COLLECTION_ENABLED=1 /path/to/venv/bin/python -m app.v2.tools.cli \
  --database-url "$V2_DATABASE_URL" run-collection --query "robotics" --max-filings 15 --trigger-type scheduled
```

Scheduled runs never need `--as` (they use the fixed, non-human `triggered_by="cli:scheduled"`). Configuring
this cron entry is an operator action outside this repository — nothing here creates or manages the cron
entry itself.

### Manual trigger from the review UI

`/admin/v2-review` → **Collection operations** tab → enter a query and max filings, check the explicit
confirmation box, click **Trigger collection**. Same underlying `run_bounded_collection` function as the CLI,
reached through `POST /admin/v2-review/collection-runs/trigger` — admin-gated (`RequireAdmin`), every input
validated server-side (`TriggerCollectionRequest`: query shape, `max_filings` bounded to 1-25), refused with a
clean `409` if the job's lock is already held.

## No overlapping runs, and how recovery works

A **database-enforced partial unique index** (`uq_collection_run_one_active_per_job`, on `job_name` `WHERE
status = 'running'`) is the actual lock — it holds even across process crashes and concurrent invocations, not
just within one Python process's memory. A second concurrent `run-collection` (or trigger) for the same
`job_name` (default `sec_form_d`) gets a clean refusal (`CollectionAlreadyRunningError`, CLI exit 1 / API 409),
never a second run and never data corruption.

**Interrupted jobs** (a crashed process, a killed CLI, a machine that lost power mid-run) leave a `collection_run`
row stuck at `status='running'` — but only until its `lease_expires_at` (15 minutes by default,
`--lease-seconds` to change it) passes. Recovery is automatic on the *next* `run-collection` for that job
(it always calls `recover_interrupted_runs` first, before acquiring the lock), and can also be run standalone:

```bash
python -m app.v2.tools.cli --database-url "$DB" recover-collection-runs           # all jobs
python -m app.v2.tools.cli --database-url "$DB" recover-collection-runs --job-name sec_form_d
```

A recovered run moves to the terminal `interrupted` status with `failure_detail="lease_expired"` — never
silently retried, never left ambiguous. Its `job_name` lock is immediately free for a new run.

## Inspecting job history

```bash
python -m app.v2.tools.cli --database-url "$DB" list-collection-runs --job-name sec_form_d --limit 20
```

Or in the UI: **Collection operations** tab shows the 20 most recent runs, each with status, query, and
discovered/collected/duplicate/failed/candidate counts. `collection_run` rows are mutable only while
`status='running'`; once terminal, the database itself refuses any further `UPDATE` or `DELETE`
(`v2.collection_run_guard()`), so a run's recorded outcome is permanent history, same as every other
audit-relevant table in V2.

## Handling the review backlog

`/admin/v2-review` now supports, on both the Company and Financing candidate tabs:
- **Status filter**: pending / resolved / all.
- **Search**: company name or the source's own record identifier (e.g. an SEC accession number).
- **Pagination**: 20 per page.
- **Include test-source candidates**: off by default (see below); check it to inspect synthetic/test evidence
  specifically, never mixed into the ordinary queue.

The **Collection operations** tab's "Review backlog" panel shows the current pending-candidate counts
(`GET /admin/v2-review/collection-summary`) so an operator can see at a glance whether collection is outpacing
review.

### Evidence-integrity failures are now explicit

A candidate whose stored evidence no longer matches its recorded hash or bounds (corruption, or the one
realistic bypass of the append-only trigger — see `docs/v2/REVIEW_API_SECURITY.md`) now returns a dedicated
**`422 evidence_integrity_failed`** from every read and decide endpoint, instead of a generic `500`. The
review UI shows this as "failed integrity verification... cannot be reviewed" — never the underlying hash or
byte content either way, whichever status code it arrives as.

## Marking a source as test

**Never automatic, never inferred from a candidate's name.** A Source's `is_test` flag (default `false` for
every existing and every newly-registered source) is the *only* thing the review queue's default filter
checks — never a "Zztest"-style name prefix on the candidate itself. The one and only way to set it:

```bash
python -m app.v2.tools.cli --database-url "$DB" mark-source-test --source-key <key> --as admin:yourname --confirm
```

This is a genuinely separate, explicit administrative step — Increment 18.4's own deliberately-tampered test
records (the `Zztest V2 Review Tamper Co`/`zztest_v2_review_source` fixtures used by
`app/tests/test_v2_review_api.py`) are **not** reclassified by this increment's migration or by any other code
here. If you want them excluded from the default review queue on a database where you've been running that
test file, mark their source explicitly:

```bash
python -m app.v2.tools.cli --database-url "$DB" mark-source-test --source-key zztest_v2_review_source --as admin:yourname --confirm
```

There is no unmark/reverse operation yet — reversing a test classification is a separate, later decision, not
built here.

## Operational limitations and remaining risks

- **No background job queue.** The manual trigger blocks the HTTP request for the run's full duration
  (bounded, but not instant). Fine for occasional operator use; not a substitute for the CLI on a real
  schedule for anything more frequent.
- **`run-collection` is a single-process, single-attempt CLI invocation.** It does not retry a failed *run* as
  a whole (individual filing failures within a run are already retried per Increment 18.3's own bounded
  backoff) — a `failed`/`partial` run just sits in history until the next scheduled or manual invocation.
- **The single-active-run lock is per `job_name`, not global.** Two different `job_name`s can run
  concurrently by design (useful for, e.g., different queries under different schedules); if that's not
  wanted, always use the same `job_name`.
- **`mark-source-test` has no reverse operation.** Marking a source as test is a one-way administrative
  action today.
- **The review UI's collection-run history has no pagination beyond `limit`** (defaults to 20); very long
  job histories are inspected via `list-collection-runs --limit N` on the CLI for now.
- **No alerting.** A job stuck `failed`/`partial`/`interrupted` is visible in the UI and CLI, but nothing
  pages anyone. Operational monitoring beyond this UI is out of scope here.
