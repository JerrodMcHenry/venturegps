# Runbook: Increment 18.3 — Automated SEC Form D Collection

Builds on `docs/v2/RUNBOOK_18_2.md` (read that first for source/market/taxonomy bootstrap and the human-decision
workflow, unchanged here). This increment adds ONE new capability: fetching a real Form D filing directly from
SEC EDGAR, instead of a human downloading it by hand first. Everything downstream of "we now have the exact raw
bytes" — ingestion, extraction, candidate persistence, human resolution, classification, metrics — is exactly
the same, unmodified code from Increment 18.2.

## What this is, and is not

- **A dedicated SEC Form D collector, not a general-purpose scraper.** `app/v2/tools/sec_form_d_collector.py`
  knows exactly two things: fetch one Form D filing's `primary_doc.xml` by CIK + accession, and search EDGAR's
  own full-text search API (bounded) for candidate filings. Nothing else.
- **Still local only.** No server, no scheduled job (explicitly out of scope this increment — see "Remaining
  limitations" below), no listening socket.
- **Still no automatic canonical promotion.** Collection automatically runs ingestion and company-candidate
  *extraction* (producing untrusted candidates) — it never creates a Company, a FinancingEvent, or a
  classification. Every canonical write still requires the same explicit, confirmed human decision from
  Increment 18.2's `decide-company` / `decide-financing` / `classify` commands.
- **Still no AI extraction.** The collector fetches bytes; parsing is the same deterministic Form D XML parser
  from Increment 18.2, unmodified.

## Setup

```bash
export VENTUREGPS_SEC_COLLECTOR_USER_AGENT="Your Org (contact: you@example.com)"
```
Required, no default (see `docs/v2/SEC_COLLECTION_SECURITY.md`). Collection commands refuse to run without it.

## Commands

```bash
DB="postgresql+psycopg2://<host>/<isolated-dev-db>"

# One specific, known filing (never the shared preview or production database).
python -m app.v2.tools.cli --database-url "$DB" collect-form-d --cik 1747029 --accession 0001747029-25-000002

# Dry run: validates inputs and prints the exact URL that would be fetched. No network call, no database write.
python -m app.v2.tools.cli --database-url "$DB" collect-form-d --cik 1747029 --accession 0001747029-25-000002 --dry-run

# Bounded discovery (SEC's own full-text search, read-only -- never collects anything itself).
python -m app.v2.tools.cli --database-url "$DB" discover-form-d --query "gecko robotics" --max-results 10

# Bounded batch: discover, then collect + extract each result, reporting new/duplicate/failed per item.
python -m app.v2.tools.cli --database-url "$DB" collect-form-d-batch --query "gecko robotics" --max-results 5
python -m app.v2.tools.cli --database-url "$DB" collect-form-d-batch --query "gecko robotics" --max-results 5 --dry-run
```

Each item's outcome is exactly one of:
- **`new`** — a genuinely new observation was ingested and a company candidate extracted (`pending_review: true`
  — it is not, and never becomes automatically, a canonical company).
- **`duplicate`** — this exact filing was already ingested and extracted; the existing candidate is reported,
  nothing new is written (a fresh acquisition *Sighting* is still recorded — see Increment 18.2's own
  duplicate-evidence behavior, unchanged).
- **`failed`** — network/SSRF/parsing/extraction failure for that one item; reported with a reason, never raised
  past a batch item boundary (one failure does not abort the rest of the batch).
- **`dry_run`** — nothing was fetched or written; only the URL that would have been fetched is reported.

## The real collection this increment demonstrated

Against the isolated `venturegps_v2_dev_1801` database (never preview/production):

1. `bootstrap` (idempotent; also fixed a real, pre-existing idempotency bug in the taxonomy-version step — see
   "What changed" below).
2. `collect-form-d --cik 1747029 --accession 0001747029-25-000002` — a genuine HTTPS fetch to
   `www.sec.gov`, byte-identical to the file fetched by hand in Increment 18.2 (verified directly:
   `result.content == open("app/v2/tests/fixtures/gecko_robotics_form_d_real.xml","rb").read()` is `True`).
   Result: `status: "new"`, a new Observation (distinct from Increment 18.2's manually-uploaded one — see "Two
   sources" below), one new company candidate, `pending_review: true`.
3. The same command run again: `status: "duplicate"`, same observation, same candidate, nothing new written.
4. `discover-form-d --query "gecko robotics" --max-results 3` — a real, bounded full-text-search query, three
   real results returned (different Gecko-Robotics-related entities and investment vehicles, not just the one
   already collected).
5. `collect-form-d-batch --query "gecko robotics" --max-results 2` — collected two more real, distinct filings
   in one bounded call, both reported `new`; run again, both correctly reported `duplicate`.

### A real finding this run surfaced: CIK zero-padding and redirects

The first real batch attempt failed both items with `UnsafeTargetError: refusing to follow a redirect (status
301)`. Investigated, not worked around: EDGAR's own archive server 301-redirects a zero-padded CIK path segment
(e.g. `/data/0002082001/...`) to its canonical non-padded form (`/data/2082001/...`) — confirmed directly with a
plain `curl` request outside this codebase. The collector's own policy (never follow a redirect — see the
security doc) correctly refused it rather than silently following. The real fix was `normalize_cik()`: strip
leading zeros before building the URL, so the correct URL is requested the first time and the redirect never
needs to happen. This is exactly why the redirect-refusal test exists — it is a genuine boundary, not a
formality, and it caught a real bug in this same increment's own new code before deployment.

### Two sources, one real-world origin

Increment 18.2 registered `sec_edgar_form_d` (`collection_method: manual_upload`). This increment adds a
*separate* source, `sec_edgar_form_d_http` (`collection_method: http_fetch`), rather than changing the existing
one — so every observation's provenance (manually uploaded in 18.2, or automatically collected from here on)
stays visible from the source alone, not just a code comment. Both point at the same real-world origin, SEC
EDGAR.

## What changed outside `app/v2/tools/`

- `app/v2/tools/cli.py`: three new commands (`collect-form-d`, `discover-form-d`, `collect-form-d-batch`), plus
  a real, pre-existing bug fix: `bootstrap`'s taxonomy-version step called `register_taxonomy_version`
  unconditionally, unlike its source/market steps, which check-then-register. Re-running `bootstrap` against an
  already-bootstrapped database raised `ConflictError` instead of the idempotent no-op its own docstring
  promised. Fixed with the same check-then-register pattern already used for source/market.
- Nothing in `app/v2/domain`, `app/v2/ingestion`, `app/v2/candidates`, `app/v2/resolution`,
  `app/v2/financing_resolution`, `app/v2/classification`, `app/v2/repositories`, or any migration was touched.
  No new dependency: `requests` was already in `requirements.txt`.

## Remaining limitations (explicitly out of scope this increment)

- **No scheduled/recurring collection.** Every collection is explicitly, manually invoked — proving this works
  reliably on demand was the point of this increment, per its own instructions; a scheduler is future work.
- **No general SEC form coverage.** Only Form D. Extending to other form types is a new, separately-scoped
  parser + evidence-verification question (see Increment 18.2's own reported `financing_type`/`stage` gaps,
  which a different form type might or might not share).
- **Discovery result quality depends entirely on the query text.** `discover-form-d`/`collect-form-d-batch` pass
  the query straight through to EDGAR's own full-text search; a broad query returns a mix of real operating
  companies and unrelated investment vehicles/SPVs with similar names (visible directly in this run's own
  output) — a human still needs to look at `display_name` before deciding a discovered filing is worth
  collecting, exactly as Increment 18.1's source-strategy report already anticipated.
- **A single logical filer can appear under many different CIKs** (special-purpose investment vehicles,
  predecessor entities, etc.) — this collector does not attempt to resolve that; it is exactly why company
  identity resolution stays a separate, human decision (Increment 18.2), never automated here.
