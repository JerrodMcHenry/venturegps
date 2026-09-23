# Human review dossier — Gecko Robotics, Inc. (Increment 18.2 development run)

**This is a proposal for your review, not a record of your approval.** Every fact below is queried directly
from the isolated `venturegps_v2_dev_1801` database (never preview/production) as it stands after Increment
18.2's demonstration run. The decisions already recorded there were made under `admin:jerrod` authority by me,
standing in for a human reviewer, solely to prove the pipeline works end to end — **not your actual review of
this company or this data.**

## 1. Primary evidence: SEC Form D filing

- **Filer:** Gecko Robotics, Inc. (SEC CIK `0001747029`)
- **Accession number:** `0001747029-25-000002`
- **Filed:** 2025-06-12
- **URL:** https://www.sec.gov/Archives/edgar/data/1747029/000174702925000002/primary_doc.xml
- **Stored as:** Observation id `1`, content hash
  `77aac5298bf1b987f9bc165aec4144ee67713f8a09bbaa74804365d796fe8deb`, ingested under source `sec_edgar_form_d`.
- Checked into the repo verbatim for reproducibility: `app/v2/tests/fixtures/gecko_robotics_form_d_real.xml`.

## 2. Company identity evidence

- **Proposed name:** "Gecko Robotics, Inc." — cited from the filing's own `<entityName>` element (byte span
  [228:248] of the exact stored payload).
- **Identifiers proposed: none.** Form D's own schema has no website/domain field for the issuer — this is an
  honest absence, not an omission on this pipeline's part.
- **Canonical status:** already created in the dev database — Company id `b19376f7-8549-40db-828b-4444a4176f28`,
  canonical name "Gecko Robotics, Inc.", resolution decision id `1` (`create_company`, `human:admin:jerrod`).

## 3. Offering amount and amount sold (kept separate, per the domain model — neither is a "verified" figure)

Both cited directly from the filing's `<offeringSalesAmounts>` block; both remain **candidate-level facts only**
— the domain model has no path to promote either one to any canonical amount field (only an
`announced_round_amount`, from a *different* kind of evidence, may become `verified_round_amount`, and only
under human authority):

| Fact | Amount | Evidence |
|---|---|---|
| `offering_amount` | $139,900,000.00 | `<totalOfferingAmount>139900000</totalOfferingAmount>` |
| `amount_sold` | $121,534,561.00 | `<totalAmountSold>121534561</totalAmountSold>` |

## 4. The reported $125M announced round

- **Source:** SiliconANGLE (reputable media reporting, third-party — not the company's or an investor's own
  words; see "unresolved items" below).
- **URL:** https://siliconangle.com/2025/06/12/gecko-robotics-raises-125m-inspect-monitor-critical-infrastructure/
- **Exact cited text:** "Gecko Robotics raises $125M to inspect and monitor critical infrastructure" (the
  page's own headline/title text, occurrence 1 of 9 near-identical repetitions across its meta tags).
- **Stored as:** Observation id `2`, content hash `0d11efeac5b04db187909d8b8a5ec9e74f27d9132e811a73a9b7de8b5a70c6b6`.
- **Amount:** $125,000,000.00, proposed as `announced_round_amount` (financing candidate id `2`).
- **Canonical status:** already accepted as the event's `verified_round_amount` in the dev database
  (financing-resolution decision `attach_to_event`, `human:admin:jerrod`).
- **A separate, real number this dossier deliberately does not conflate with the round size:** the company's own
  announcement page (`geckorobotics.com/news/gecko-reaches-unicorn-status`) states a **$1.25B valuation** —
  fetched during evidence-gathering but never proposed as a fact, since a post-money valuation is not a round
  amount (its round-size figure required JavaScript rendering not present in a plain downloaded copy of that
  page, which is why the reputable-media citation above was used instead).

## 5. Dates, clearly distinguished

| Date kind | Value | Source | Canonical? |
|---|---|---|---|
| `first_sale_date` | 2025-05-15 | Form D `<dateOfFirstSale><value>` | **Yes** — accepted onto the event |
| `filing_date` | 2025-06-12 | Form D `<signatureDate>` | **Yes** — accepted onto the event |
| `announcement_date` | *(none proposed)* | — | No candidate fact exists for this |

## 6. Unresolved conflicts or missing facts

- **No genuine numeric conflict.** The three amounts (offering $139.9M, sold $121.5M, announced round $125M)
  measure three different things by design and are not expected to match; none should be read as contradicting
  another.
- **`announcement_date` was never actually proposed or stored as a candidate fact**, despite the announcement
  observation being ingested with an `event_date` of 2025-06-12 — that value is only Observation-level metadata
  (when the collector believes the article was published), not a byte-evidenced, verifiable candidate date. If
  you want a real `announcement_date` fact on this event, it needs to be added the same human-guided way the
  amount was (a human names the exact substring stating the date).
- **`financing_type` is unknown** — see the separate report on this (Item 2 of this increment). Legitimately
  absent; nothing downstream requires it.
- **`stage` is unknown** — Form D never states one; the announcement evidence used here was never checked for
  stage language either (its own headline doesn't state "Series X").
- **The $125M source is third-party media reporting, not the company's or an investor's own announcement** —
  the company's own page was fetched but its round-size text wasn't present in the static download (see item 4).
  If you want a first-party source specifically, that would need to be re-obtained (e.g. rendering the page
  fully, or the investor's own announcement, if Cox Enterprises published one).

## 7. Proposed canonical decisions, for your actual approval

1. **Create** a canonical Company: "Gecko Robotics, Inc." from candidate `1`.
2. **Create** a canonical FinancingEvent from Form D candidate `1`, accepting `first_sale_date` and
   `filing_date` (never `offering_amount`/`amount_sold` — the domain has no path to promote those).
3. **Attach** announcement candidate `2` to that same event, accepting `verified_round_amount` = $125,000,000.00.
4. **Classify** the company into Robotics (`venturegps_taxonomy.v1`, role `primary`).

All four are already applied in the isolated dev database from the earlier demonstration run. They are laid out
here exactly as a fresh reviewer would need to see them to decide independently — please treat them as pending
your own sign-off, not as already approved.
