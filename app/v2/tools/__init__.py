"""
VentureGPS Increment 18.2 -- operational tooling for the first real Robotics ingestion, per the Increment 18.1
audit's own recommended first coding increment. Everything here is deterministic (this package, like every
app/v2 package outside app.v2.ai, is deterministic-zone by default -- see
app/v2/tests/architecture/boundary_rules.py's own docstring: "A package added tomorrow is deterministic
automatically"): no AI SDK, no model credentials, no network access anywhere in this package. Network access
(downloading a filing) happens OUTSIDE this package, by a human, before anything here is invoked -- the same
CollectionMethod.MANUAL_UPLOAD boundary app/v2/domain/source.py already documents. This package only reads
local files a human has already obtained and calls existing app.v2 repositories/services; it introduces no new
persistence, no new tables and no changes to any existing domain model.

    form_d_xml.py                deterministic Form D XML parsing: safe (defusedxml, no external entity
                                  resolution), byte-exact (every extracted value is re-located in the ORIGINAL
                                  raw bytes and cross-checked against what the parser itself extracted)
    form_d_company_proposer.py   CandidateProposer implementation (app.v2.candidates.proposer.CandidateProposer)
                                  for company identity, from Form D evidence only
    form_d_financing_proposer.py plain function proposing a FinancingEventCandidateProposal from Form D evidence
                                  for an ALREADY-CANONICAL company (financing candidates require a real
                                  company_id -- see app/v2/domain/financing.py's own docstring)
    manual_fact.py                a human-guided (not automated/NLP) way to add ONE additional proposed amount or
                                  date from a second piece of evidence (e.g. a funding announcement), where the
                                  human names the exact substring the evidence states and this module locates
                                  and hashes it -- never infers or parses free text itself
    cli.py                        the local, unauthenticated-network-surface CLI: source/market/taxonomy
                                  bootstrap, evidence ingestion, extraction, candidate inspection, and human
                                  decisions. Requires explicit confirmation before any canonical write.

See docs/v2/RUNBOOK_18_2.md for the full, real, end-to-end walkthrough this package was built to run.
"""
