# Engineering Case Study: From "LLM Scores a Number" to Evidence-First Architecture

How VentureGPS's analysis engine changed shape after a real, documented failure mode in its first design,
and what replaced it. This is the central engineering narrative of the project — the rest of the
documentation describes what was built; this describes why it was built that way.

## Problem

Startup due diligence from public information is noisy, incomplete, and easy for an LLM to overstate. Ask
a language model "how strong is this company's traction?" and it will almost always produce a confident-
sounding answer, whether or not the underlying public evidence actually supports one. The hard engineering
problem isn't getting an LLM to research a company — it's preventing the system from presenting "the model
said so" as equivalent to "the evidence says so."

## Initial approach

The first engine (still live today as the legacy path, `app/ai/`) analyzed six fixed pillars — market,
team, product, execution, traction, financial health — each scored by prompting an LLM to pick a 0–10
number per dimension. It was not naive: every dimension was tagged **Public**, **Inferred**, or **Private**
to control whether "Unavailable" was a legal outcome; evidence extraction and scoring ran as two separate
calls (an extraction call that never saw scoring instructions, then a scoring call that judged only the
already-extracted evidence, never re-reading raw text) specifically to contain hallucination; and Low-
confidence judgments were capped so they couldn't produce a high numeric score.

## Failure discovered

Even with that design, the core coupling remained: a single LLM call was still the thing deciding both
*whether evidence was sufficient* and *what the resulting number should be* — two different judgments,
made by the same probabilistic call, with no independent check that the second one was actually backed by
the first. A real, documented incident exposed this directly: a Retention dimension retained an LLM-
produced score of **7.0 with no `structured_facts` backing it at all** — a confident number, with no
grounded evidence behind it, that the pipeline would otherwise have accepted as if it meant something. The
fix at the time was a deterministic override for that one case (discard the LLM's score, replace with a
computed value or `None`) — correct, but reactive: it patched a symptom after it was found, rather than
making the underlying failure mode structurally impossible. Missing evidence and genuinely weak evidence
could still look identical to a reader, because nothing in the architecture *required* a measured amount of
admissible evidence before a score was allowed to exist.

## Architectural decision

Rather than keep patching individual dimensions as new instances of the same failure surfaced, the decision
was to build a second, clean-slate engine (`app/evidence_engine/`) around one non-negotiable rule:
**evidence precedes assessment; assessment precedes scoring — there is no code path from "the model said
so" directly to a number.** This is a different kind of system, not a third revision of the same one: no
pillar definition, dimension, weight, or scoring formula carries over from either prior engine.

## Solution

An **Evidence Ledger** of typed, source-grounded claims, built through a pipeline where every stage after
extraction is deterministic code, not another model call:

- **Grounding** — a claim's excerpt must be verbatim-present in the real retrieved source text, or it is
  rejected before it ever becomes a `Claim`.
- **Canonicalization** — claims are normalized into a consistent typed-fact shape so the same underlying
  fact (e.g. a funding round mentioned two different ways on two different pages) can be recognized as the
  same fact.
- **Semantic-fit validation** — catches the class of error schema validation alone cannot: a claim that is
  structurally valid JSON but semantically assigned to the wrong category (a funding amount tagged as a
  hiring metric). Found and fixed as a real gap during live evaluation, not designed in from the start —
  see `docs/methodology/SEMANTIC_EVIDENCE_CONTRACT.md`.
- **Deterministic scoring and publication gates** — pillar scores, company-level Evidence Coverage,
  Confidence, and the publish/withhold decision are pure, reproducible arithmetic over already-validated
  claims (`app/evidence_engine/scoring.py`, `cross_pillar_audit.py`). A pillar below its evidence-coverage
  floor is explicitly **withheld**, never scored anyway. There is no overall company score — Coverage and
  Confidence are reported as their own concept, not compressed into one number that implies more certainty
  than the evidence supports.

The same discipline this project had already established for a *different* subsystem — VentureGPS V2's
AI-candidate/deterministic-authority boundary for company identity (`docs/v2/ADR-0001-truth-model.md`,
"AI MAY PROPOSE. AI MAY NOT DECIDE," enforced down to a database `CHECK` constraint) — is what this new
engine applies to evidence itself.

## Production integration

The new engine was built and live-validated in isolation (offline tests, then controlled live-evaluation
runs against real companies) before touching the real product at all. Integration was deliberately additive,
not a replacement:

- **Legacy compatibility.** The original engine is completely unmodified and remains the default path for
  every request.
- **One server-side feature-flag boundary** (`resolve_engine()`) — a client requesting the new engine can
  never authorize it by itself; only the server's own environment flag can.
- **A thin Route → Service → Adapter → Persistence boundary**, where the Adapter is the *only* place the
  real engine's pipeline and real providers are constructed — no methodology logic duplicated at the
  integration layer.
- **Additive, independently-migrated persistence.** A new table, in its own, separately-owned Alembic
  environment — not a new column bolted onto the legacy schema, and not borrowed space in an unrelated
  subsystem's migration history (VentureGPS V2's), which would have created a misleading architectural
  dependency for convenience alone.
- **Authenticated, UUID-scoped retrieval.** Every report is looked up strictly by an application-generated
  UUID and checked against the authenticated caller's own identity — a non-owner and a nonexistent id
  return the identical 404, so probing ids can never be used to learn what exists.

## Security

- **SSRF.** Website retrieval reuses the legacy engine's own already-hardened fetcher unchanged (scheme
  allow-listing, private/loopback/link-local/cloud-metadata rejection, DNS-rebinding-safe IP pinning,
  bounded redirects, response-size caps) — the new engine adds nothing to, and weakens nothing in, that
  boundary.
- **Prompt-injection posture.** Retrieved web content is explicitly, instructionally treated as untrusted
  data in the extraction prompt — a page's own text is never allowed to act as an instruction to the model,
  only as material to quote from.
- **Safe rendering.** Untrusted retrieved text is rendered as plain text on the frontend, never as raw HTML;
  external source links carry hardening attributes and are never implied to mean independent verification.
- **Ownership isolation.** Verified not just in code but against the real, live production database with an
  unauthenticated request (`curl`, no credentials) returning a 401 with no data at all.

## Validation

The path to production was deliberately staged, each phase gating the next:

1. **Offline tests** — the engine's own isolated suite (604 tests across 28 files) with every provider
   mocked, no real external call anywhere.
2. **Controlled live evaluations** — a handful of real companies run through real Tavily/OpenAI calls, in
   isolation, specifically to find failure modes offline tests couldn't (this is how the semantic-fit gap
   above was actually found).
3. **Local end-to-end validation** — the full product integration, exercised through a real authenticated
   browser against a local backend, before touching any shared environment.
4. **Production smoke test** — one real, paid, authenticated analysis against the live deployed application,
   with persistence, report rendering, reload behavior, and privacy boundaries all independently re-verified
   against production itself, not assumed to still hold from an earlier environment.

## Tradeoffs

Stated plainly, not hidden in the implementation:

- **Lower Coverage is preferable to unsupported certainty.** A sparse, honest report is the intended
  outcome when public evidence is thin — not a defect to be tuned away.
- **A synchronous ~40-second analysis is an acceptable tradeoff for a beta**, not a scale-tested production
  latency target. (A real production run measured 39.46 seconds end to end.)
- **Public evidence inherently limits how complete any assessment can be** — this system reports what
  public sources show, not private company data it has no access to.
- **The legacy engine remains live.** Running two engines side by side is real, intentional operational
  cost, accepted in exchange for never forcing users onto a materially sparser report without warning
  during the new engine's controlled rollout.
- **There is deliberately no overall company score.** This is a product tradeoff as much as a technical one
  — it is a harder thing to show a user than a single number, and it is the more honest one.

## What I would build next

Kept short and realistic — not implemented as part of this project, and not a sign anything here is
incomplete for what it claims to be:

- **Asynchronous job execution**, if real usage ever made a ~40-second synchronous request a problem —
  not needed at today's scale.
- **Richer production observability** — token-usage and per-analysis cost instrumentation (currently
  absent in production, a known, documented gap) and structured per-stage timing dashboards, beyond the
  existing stdout-based logging.
- **Improved evidence recall** — broader source discovery for company types current research queries serve
  less well.
- **Additional supported input types** for the new engine (currently website-only; the legacy engine already
  supports pasted text and PDFs).
- **A real production evaluation dataset** — a repeatable, multi-company regression gate, beyond the current
  mix of one small calibration harness and point-in-time live-evaluation reports.
