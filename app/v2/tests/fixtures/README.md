# Test fixtures — Increment 18.2

- **`gecko_robotics_form_d_real.xml`** — the REAL, unmodified `primary_doc.xml` from Gecko Robotics, Inc.'s
  actual SEC Form D filing (accession `0001747029-25-000002`, filed 2025-06-12), downloaded directly from
  `https://www.sec.gov/Archives/edgar/data/1747029/000174702925000002/primary_doc.xml`. SEC EDGAR filings are
  U.S. government records; Form D data is explicitly published by the SEC for public reuse (see
  `docs/v2/RUNBOOK_18_2.md`'s source-strategy notes). Used both for the real Increment 18.2 development-database
  run and for this package's automated tests (`app/v2/tests/domain/test_form_d_tools.py`).
- **`synthetic_announcement_snippet.html`** — a small, deliberately fictional HTML snippet in the shape of a
  funding-announcement page, used only to test `manual_fact.py`'s substring-location logic (occurrence counting,
  ambiguous-substring handling, amount/date building) without checking a real news article's copyrighted text
  into the repository. It does not describe Gecko Robotics or any real company or event; see the file's own
  comment.
