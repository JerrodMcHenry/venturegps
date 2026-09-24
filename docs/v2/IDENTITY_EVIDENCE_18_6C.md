# First-party company identity evidence — Increment 18.6c

Closes the specific gap Increment 18.6's coverage audit found: no V2 source can ever propose a company
identifier (domain/website URL), because SEC Form D's own schema has no such field
(`app/v2/tools/form_d_company_proposer.py` documents this directly). This increment adds the smallest
reusable addition to close it — reusing every existing mechanism, adding exactly one new CLI command and one
new registered Source.

## What this is, and is not

- **Not automated extraction.** A human reads a first-party page (the company's own site, an investor-
  relations page, a company-issued announcement) and names two exact substrings: one stating the company's
  name, one stating its domain or website URL. This tool only locates and hashes what the human pointed at —
  it never decides what the page says, the same discipline `add-announcement-candidate` (Increment 18.2)
  already established for financing facts Form D cannot state either.
- **Not a news aggregator.** There is no fetcher, no crawler, no feed parser here. Evidence still enters the
  system exactly the way every other manually-sourced document already does: a human saves the page, then
  `ingest` (unchanged, Increment 18.2) loads it as an immutable `RawPayload`/`Observation` under the new
  `first_party_company_page` source.
- **Produces only an untrusted candidate.** Identical trust boundary to every other candidate in V2: nothing
  here can attach, merge, or create a canonical company. A human decides that separately, through the
  existing, unmodified `decide-company` command or the review interface.

## The one new Source

`SourceType.FIRST_PARTY_COMPANY` already existed in the domain vocabulary (`app/v2/domain/source.py`) but was
never registered or used before this increment. `bootstrap` now also registers:

```
source_key: first_party_company_page
name: Official company website or investor-relations page (manual upload)
source_type: first_party_company
collection_method: manual_upload
```

No schema change, no new enum value, no new table — `register_source`, called exactly as it already is for
every other source.

## Usage

```bash
DB="postgresql+psycopg2://<host>/<isolated-dev-db>"

# 1. A human saves the page (or a relevant excerpt) to a local file, then ingests it exactly like any other
#    manually-sourced document (unchanged command):
python -m app.v2.tools.cli --database-url "$DB" ingest \
  --source first_party_company_page --file ./gecko_homepage.txt \
  --record-id "https://www.geckorobotics.com/" --observation-type company_web_page \
  --acquisition-key "gecko-identity-2026-09-24"

# 2. Propose the identity candidate: two exact substrings, located and byte-hash-verified independently.
python -m app.v2.tools.cli --database-url "$DB" add-identity-candidate \
  --observation-id <id from step 1> \
  --name-find "Gecko Robotics, Inc." \
  --identifier-type website_url --identifier-value "https://www.geckorobotics.com/" \
  --identifier-find "https://www.geckorobotics.com/"
```

`--name-occurrence` / `--identifier-occurrence` (default `0`) disambiguate when a substring appears more than
once on the page — the command prints how many times each was found before acting, so the choice is always an
informed one, never a silent guess (the exact `locate_evidence` pattern `add-announcement-candidate` already
uses).

## What is rejected, and how

| Scenario | Result |
|---|---|
| The named substring doesn't appear (or not `occurrence+1` times) | `FactNotFoundError` → attempt marked `failed`, command exits 1, nothing persisted |
| The identifier value is not a well-formed domain/URL | `ProposedIdentifier`'s own model validator refuses it (`InvalidInputError`/`UnsupportedInputError`) before persistence is attempted |
| The proposed name or identifier value doesn't literally appear inside its own cited span (e.g. `--name` was typed differently from what `--name-find` actually locates) | `verify_proposal` (unchanged, the same check every other proposer's output goes through) refuses it, `value_not_in_evidence` |
| The exact same observation is submitted again | Reported as `{"status": "duplicate", ...}`, pointing at the candidate already proposed — never a second identical row, never an unhandled exception (mirrors `_collect_and_extract_one`'s own duplicate-filing behavior) |
| The proposed identifier is later `attach`ed to a company that doesn't own it, while a *different* canonical company already does | Refused by the existing, unmodified `IdentifierConflictError` in `attach_candidate_to_company` — this command does not add or weaken that check in any way |

Every rejection marks the processing attempt `failed` with a real, typed `detail_code` (the domain error's own
`.code`, e.g. `value_not_in_evidence`) — never a raw exception name, never evidence content.

## Toward future official-announcement and news ingestion (not built here)

This increment deliberately stops at identity. The same shape (`ingest` under a new source type +
a small human-guided "locate this substring" command reusing `manual_fact.py`'s helpers +
`store_company_candidates`/`persist_financing_event_candidates`, unchanged) is already how
`add-announcement-candidate` (financing facts) and now `add-identity-candidate` (identity facts) both work —
a future increment adding, say, business-description evidence for market classification, or a bounded
"reputable reporting" corroboration source, would follow the identical pattern: register a `Source` under an
already-existing `SourceType` if one fits (`RESEARCH`, `MEDIA_NEWS` are both already defined), ingest via the
unchanged `ingest` command, and add one small, human-guided command that locates exact substrings and builds
the appropriate typed proposal. No general fetcher, no crawler, and no AI extraction should be introduced to
do this — the discipline this file's own module docstring states (`app/v2/tools/manual_fact.py`) is the reason
none of the four companies researched in Increment 18.6b needed one to get real, byte-verified identity
evidence into the system.

## Demonstration (isolated dev database, no canonical decision made)

Against `venturegps_v2_dev_1801`:
1. `bootstrap` — registered `first_party_company_page` (id 15), everything else already present (idempotent).
2. `ingest` — a short, genuine excerpt of Gecko Robotics' own public self-description and domain
   (`https://www.geckorobotics.com/`, verified live during Increment 18.6b's research), observation id 57.
3. `add-identity-candidate` — candidate #39: `proposed_name="Gecko Robotics, Inc."`,
   `identifiers=[{"type": "website_url", "value": "https://www.geckorobotics.com/"}]`, both spans re-verified
   byte-exact against the live payload.
4. Re-running the identical command reported `{"status": "duplicate", "candidate_ids": [39]}` — not a second
   candidate.
5. Confirmed directly against the database: `company`, `resolution_decision` and `company_identifier` row
   counts are **unchanged** (8 / 15 / 0) before and after every step above — no canonical company was created,
   no identifier was attached, no existing decision was touched.

Candidate #39 remains fully untrusted and pending — attaching it to the existing canonical Gecko Robotics
company is a human decision for the reviewer, not made by this increment.
