# Runbook: Increment 18.2 — First Real Robotics Ingestion

This is the real, reproducible, end-to-end walkthrough for taking one genuine Robotics company and its real
financing evidence from an SEC filing through to VentureGPS's existing V2 Capital Metrics/Signal API, using only
existing, already-tested V2 infrastructure plus the new tooling in `app/v2/tools/`. Everything below was
actually run, once, against an isolated development database (never the shared preview or production database)
as part of this increment; the exact IDs shown are from that real run.

> **Superseded in part by Increment 18.3** (`docs/v2/RUNBOOK_18_3.md`): automated SEC Form D collection now
> exists (`app/v2/tools/sec_form_d_collector.py`, the `collect-form-d`/`discover-form-d`/`collect-form-d-batch`
> CLI commands). The "No automated fetching" line below described this increment's own scope accurately at the
> time; it no longer describes the whole tool. Everything else on this page -- the manual-upload `ingest` path,
> the extraction/resolution/classification walkthrough -- is unchanged and still accurate.

## What this is, and is not

- **Local only.** `app/v2/tools/cli.py` is a command-line tool. There is no HTTP server, no listening socket, no
  unauthenticated endpoint anywhere in this package.
- **No automated fetching (as of Increment 18.2).** Every file `ingest` reads is a file a human already
  downloaded onto local disk. There was no HTTP-fetch code anywhere in `app/v2` as of this increment (see the
  Increment 18.1 audit) -- see the note above for what changed in 18.3.
- **No AI extraction.** The Form D parser (`app/v2/tools/form_d_xml.py`) is deterministic XML parsing; the
  financing-announcement path (`app/v2/tools/manual_fact.py`) is human-guided substring location, not free-text
  inference — see that module's own docstring for why a second automated proposer was deliberately not built.
- **Every canonical write is a human decision.** `decide-company`, `decide-financing` and `classify` all record
  `Authority(kind=HUMAN, id=<you>)` and require `--confirm` (or an interactive "yes").

## Prerequisites

1. A disposable Postgres database, migrated to head:
   ```bash
   psql "postgresql://<host>/postgres" -c "CREATE DATABASE venturegps_v2_dev;"
   V2_DATABASE_URL="postgresql+psycopg2://<host>/venturegps_v2_dev" python -m alembic -c alembic.ini upgrade head
   ```
   **Never point this at the shared preview or production database.** `--database-url` on every CLI command
   below is required with no default specifically so this can't happen by accident.
2. `pip install defusedxml` (new dependency this increment added — see "What changed" below).
3. One real piece of primary evidence: an SEC Form D `primary_doc.xml`, downloaded directly from EDGAR by a
   human. This runbook used Gecko Robotics, Inc.'s real, public Form D filing (CIK 1747029, accession
   `0001747029-25-000002`, filed 2025-06-12), fetched from
   `https://www.sec.gov/Archives/edgar/data/1747029/000174702925000002/primary_doc.xml` — the same file is
   checked into `app/v2/tests/fixtures/gecko_robotics_form_d_real.xml` for the automated tests. SEC EDGAR
   filings are U.S. government records; see the Increment 18.1 report's source-strategy section for the full
   rights/reliability discussion.
4. Optionally, a second piece of evidence (a company or investor announcement) if you want a real
   `verified_round_amount` to flow through to Capital Deployed — see step 9. This run used a reputable media
   report (SiliconANGLE) naming the same $125M figure, since the company's own announcement page's round-size
   text required JavaScript rendering not present in a plain downloaded copy (its `$1.25B` valuation figure
   *was* present statically, but a valuation is not a round amount and was correctly never proposed as one).

## The real run

```bash
DB="postgresql+psycopg2://postgres@127.0.0.1:54331/venturegps_v2_dev_1801"

# 1. Bootstrap: idempotent, safe to re-run.
python -m app.v2.tools.cli --database-url "$DB" bootstrap

# 2. Ingest the real Form D filing.
python -m app.v2.tools.cli --database-url "$DB" ingest \
  --source sec_edgar_form_d --file gecko_form_d.xml \
  --record-id "0001747029-25-000002" --observation-type sec_form_d_filing \
  --event-date 2025-06-12 --acquisition-key "sec_form_d:0001747029-25-000002:manual"
# -> observation_id: 1

# 3. Extract the company candidate (deterministic Form D XML parsing).
python -m app.v2.tools.cli --database-url "$DB" extract-company --observation-id 1
# -> candidate_ids: [1]

# 4. A human reads it.
python -m app.v2.tools.cli --database-url "$DB" show-company-candidate 1
# proposed_name: "Gecko Robotics, Inc.", identifiers: [] (Form D has no website field -- see "known schema gaps")

# 5. A human decision: create the canonical Company.
python -m app.v2.tools.cli --database-url "$DB" decide-company 1 --action create --as admin:jerrod --confirm
# -> company_id: b19376f7-8549-40db-828b-4444a4176f28

# 6. NOW that the company is canonical, extract the financing candidate from the SAME Form D evidence.
python -m app.v2.tools.cli --database-url "$DB" extract-financing \
  --observation-id 1 --company-id b19376f7-8549-40db-828b-4444a4176f28
# -> offering_amount $139,900,000.00 and amount_sold $121,534,561.00, both real, both from the filing

# 7. A human decision: create the canonical FinancingEvent, accepting the two real Form D dates.
python -m app.v2.tools.cli --database-url "$DB" decide-financing 1 --action create-event \
  --facts "first_sale_date,filing_date" --as admin:jerrod --confirm
# -> financing_event_id: e4a1e27f-89b2-4189-bdb5-1b00168cc811

# 8. Ingest the second document (a real, reputable announcement stating the round size).
python -m app.v2.tools.cli --database-url "$DB" ingest \
  --source media_funding_announcement --file announcement.html \
  --observation-type funding_announcement_article --event-date 2025-06-12 \
  --acquisition-key "siliconangle:gecko-robotics-125m:manual"
# -> observation_id: 2

# 9. Human-guided (not automated) financing candidate: the human names the exact substring the announcement
#    states, the CLI only locates and hashes it.
python -m app.v2.tools.cli --database-url "$DB" add-announcement-candidate \
  --observation-id 2 --company-id b19376f7-8549-40db-828b-4444a4176f28 \
  --amount 125000000 --currency USD --find "Gecko Robotics raises \$125M" --occurrence 0
# -> candidate_ids: [2]

# 10. A human decision: attach this candidate to the SAME event, accepting verified_round_amount specifically
#     (never offering_amount or amount_sold -- see app.v2.financing_resolution.promotion's own rule).
python -m app.v2.tools.cli --database-url "$DB" decide-financing 2 --action attach-to-event \
  --event-id e4a1e27f-89b2-4189-bdb5-1b00168cc811 --facts "verified_round_amount" --as admin:jerrod --confirm

# 11. A human decision: classify the company into Robotics.
python -m app.v2.tools.cli --database-url "$DB" classify \
  --company-id b19376f7-8549-40db-828b-4444a4176f28 --market-slug robotics \
  --taxonomy-version venturegps_taxonomy.v1 --role primary --as admin:jerrod --confirm

# 12. Verify through the EXISTING, unchanged V2 API engines.
python -m app.v2.tools.cli --database-url "$DB" verify --market-slug robotics \
  --taxonomy-version venturegps_taxonomy.v1 --as-of 2025-09-23
```

Step 12's real output showed the $125,000,000.00 verified amount correctly attributed to the historical window
containing the real `first_sale_date` (2025-05-15), `financing_activity: 1` and `companies_funded: 1` in that
window, and `overall: "insufficient_data"` for the market as a whole — correct and honest: one real event is not
enough history (capital_signal.v1 needs ≥3 non-zero historical windows), not a bug.

## Known schema gaps (reported, not worked around)

Per this increment's own instruction — identify exact schemas first; if Form D doesn't map faithfully, report
the mismatch rather than changing the trusted domain model:

1. **`financing_type` is never proposed from Form D.** Form D's `<isEquityType>true</isEquityType>` does carry
   the security-type fact, but the existing evidence-verification regex
   (`app.v2.candidates.financing_evidence.TYPE_PHRASES`) requires the word "equity" to appear as its own
   standalone, word-bounded token in the cited evidence text. Confirmed directly against the real filing: the
   substring "Equity" only ever appears embedded inside the tag name `isEquityType` (word-boundary-adjacent to
   "is"/"Type"), never as a free-standing word. Citing the tag would fail that check honestly; synthesizing a
   standalone "equity" string not actually present in the bytes would be evidence fabrication. Neither is
   acceptable, so `financing_type` stays unproposed for Form-D-derived candidates.
2. **`stage` is never proposed from Form D.** Confirmed by direct search: no Form D document contains
   "seed"/"series"/"growth" vocabulary at all — this isn't a verification mismatch, just genuinely absent
   information, correctly left `unknown` rather than guessed.
3. **No company identifier (domain/website) is ever proposed from Form D.** Form D's own schema has no website
   field. `IdentifierType` (`domain`, `website_url`) also has no slot for a CIK or a legal-name+jurisdiction
   pair, which Form D DOES provide — worth considering for a future increment, not attempted here.
4. **Resolved in Increment 18.2.1** (originally reported here as a failing pre-existing architecture test in
   18.2): `app.v2.resolution.promotion` could until then only be imported by `app.v2.resolution.rules`, because
   no operational tool had ever needed the HUMAN-decision functions there before this CLI. The fix was a new,
   narrow module, `app.v2.resolution.human_review` — the human-authority counterpart to `rules.py`'s
   rule-authority front door, adding no logic of its own — and the CLI now imports from there, never from
   `promotion.py` directly. The boundary test now asserts exactly two sanctioned importers
   (`app.v2.resolution.rules`, `app.v2.resolution.human_review`), not a broader grant to
   `app.v2.tools`/application code in general. See `app/v2/resolution/human_review.py`'s and
   `app/v2/resolution/promotion.py`'s own docstrings for the full reasoning. The full architecture suite now
   passes with zero deselections.

## What changed outside `app/v2/tools/`

- `requirements.txt`: added `defusedxml` (XML parsing with external entity resolution disabled — the standard
  library's own `xml.etree.ElementTree` is explicitly not recommended for untrusted input, and this increment's
  own security requirement is exactly "no external entity resolution").
- `app/v2/resolution/human_review.py` (new, Increment 18.2.1): the narrow, second sanctioned caller of
  `resolution.promotion` — see "Known schema gaps" item 4 above.
- `app/v2/resolution/promotion.py` and `app/v2/tests/architecture/test_resolution_boundaries.py`: docstrings and
  one assertion updated (Increment 18.2.1) to document and enforce the new, still-narrow two-module boundary.
- No database schema changed; no migration added or modified. `app/v2/domain`, `app/v2/financing_resolution`,
  `app/v2/classification` and every repository are untouched.
- See `docs/v2/EVIDENCE_REVIEW_18_2_GECKO_ROBOTICS.md` for the human-review dossier on the real data this
  runbook produced.
