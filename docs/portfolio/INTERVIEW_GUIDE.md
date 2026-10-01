# Interview Guide

Talking points for technical interviews about VentureGPS, grounded in this repository as it actually
exists — no invented scale, traffic, or revenue claims. See `docs/portfolio/ENGINEERING_CASE_STUDY.md` for
the fuller narrative behind several of these answers.

## What did you build?

A full-stack, production-deployed AI-assisted startup due-diligence application. Given a company name and
website, it researches public evidence and produces a structured assessment across six intelligence
pillars, showing exactly what evidence it found, where each claim came from, and which categories it
couldn't assess from public information. Backend: Python/FastAPI, PostgreSQL, OpenAI + Tavily. Frontend:
Next.js/TypeScript, Clerk auth. Deployed on Render (backend + DB) and Vercel (frontend), live at
`https://app.venturegps.ai/`. I designed and built the evidence pipeline, the deterministic scoring/
validation layer, the production integration (feature flag, persistence, migrations), the security
boundaries, and ran the controlled production deployment myself.

## What was the hardest engineering problem?

Preventing an LLM from being the thing that decides whether a company looks good. The first version of the
scoring engine asked an LLM to assign a 0–10 number per dimension — even with evidence tagging and a
two-stage extract/score split, I found a real, documented case where a dimension retained an LLM-produced
score of 7.0 with *zero* structured evidence backing it. That told me the architecture, not just that one
prompt, was wrong: a single probabilistic call was deciding both whether evidence was sufficient and what
the resulting number should be, with nothing independently checking the second against the first. The fix
wasn't a better prompt — it was moving to an architecture where scoring is mechanically impossible without
first passing through a deterministic, inspectable evidence-validation stage.

## Why not let the LLM score companies directly?

Because "the model produced the same number twice" and "the model was right" are not the same property, and
a single model call can't reliably certify its own evidence basis. An LLM is good at proposing — finding a
plausible claim, structuring it, drafting language. It's a worse fit for being the sole authority on a
decision a user will act on, especially when the failure mode (a confident number with no real evidence
behind it) is invisible unless you specifically go looking for it, which is exactly what happened in the
first version.

## What is deterministic vs. probabilistic in this system?

**Probabilistic (real AI calls, not assumed reproducible):** search query execution, and evidence extraction
— turning retrieved page text into structured claim candidates. **Deterministic (plain code, zero LLM calls,
same input always produces the same output):** grounding checks, semantic-fit validation, contradiction
detection, claim canonicalization/routing, and every number a user sees — pillar scores, company-level
Evidence Coverage, Confidence, and the publish/withhold decision. The dividing line is exact: nothing after
"a claim has been extracted and validated" ever calls a model again.

## How do you prevent hallucinated evidence from affecting scores?

Three independent, deterministic checks, each catching a different failure mode a prompt alone can't
reliably prevent: **(1) grounding** — a claim's excerpt must be verbatim-present in the actual retrieved
source text, checked by string matching, not asked of the model; a claim that fails this is rejected, never
repaired or trusted anyway. **(2) semantic-fit validation** — a claim can be schema-valid (passes Pydantic)
and still be semantically wrong, e.g. a funding amount mislabeled as a hiring metric; a dedicated check
catches this class of error, found as a real gap during live evaluation against real companies, not
designed in up front. **(3) scoring isolation** — even a claim that passes both checks only ever reaches
scoring as validated, typed evidence; the scoring code itself has no path back to raw model output.

## Why can Coverage go down after improving the engine?

Because Coverage measures how much of the methodology could be evaluated from *admissible* evidence, and
tightening validation (e.g. adding the semantic-fit check) means claims that used to pass now correctly
don't. A coverage drop after a validation fix is evidence the fix is working, not a regression — the
alternative (coverage staying flat or rising because invalid claims were silently still counted) would be
the actual red flag.

## Why no overall company score?

Because a single 0–100 number implies a precision and completeness the underlying evidence frequently
doesn't support, especially for an early-stage company with thin public information. Coverage (how much of
the methodology could be evaluated) and Confidence (how sure the engine is in the evidence it gathered) are
reported as their own, differently-shaped concepts instead — explicitly not a performance score, and never
compressed into one figure. This was a deliberate product and architecture decision together, not a
limitation I'd remove given more time.

## How does authorization work?

Clerk-issued JWTs, verified server-side against Clerk's own JWKS (RS256 signature, issuer, and authorized-
party checks) — the frontend holding a session is never itself trusted; every authenticated route re-
verifies the token. Resource-level authorization is ownership-scoped: an analysis is retrieved strictly by
its UUID, then the row's owner is compared against the authenticated caller — a non-owner and a nonexistent
id both return the identical 404, never a distinguishing 403, so an attacker can't use response differences
to enumerate which ids exist. I independently re-verified this against the live production database with an
unauthenticated `curl` call (no cookies, no token) and confirmed a 401 with no data returned, rather than
just trusting the code.

## How did you handle SSRF?

Website retrieval doesn't trust a user-supplied URL at face value: it allow-lists scheme, rejects private/
loopback/link-local/cloud-metadata-range addresses, pins DNS resolution to the validated address to prevent
a rebinding attack between validation and the actual fetch, bounds how many redirects it will follow and
re-validates each hop, and caps response size. The new evidence engine doesn't reimplement any of this — it
reuses the existing, already-tested fetcher unchanged, specifically so the security boundary has one
implementation, not two that could drift apart.

## Why two Alembic environments?

Because the three persistence domains in this repository — the legacy engine's tables, VentureGPS V2's
schema, and the new evidence engine's own table — each needed independent migration ownership, and the
existing V2 Alembic environment was structurally hard-wired to its own schema (its autogenerate scope
explicitly excludes the default schema, and its downgrade path can drop its entire schema). Putting the new
engine's table there would have either required weakening V2's own migration-safety scope or created a
misleading dependency between two unrelated subsystems, just for migration convenience. A second, minimal,
independent environment — no autogenerate, one hand-written revision, its own version-table name — was the
smallest change that kept all three domains from being able to corrupt or depend on each other's schema
history. I treated this as a real architectural decision worth writing an ADR for, not a default.

## Why JSONB for the evidence artifact?

The analysis result is a rich, nested object (pillars, dimensions, evidence excerpts, telemetry) that
genuinely doesn't benefit from being flattened into dozens of relational columns — most of it is never
queried by field, only read whole by id. Relational columns exist only for what ownership, listing,
filtering, and report selection actually need (owner id, company name, engine, coverage, confidence,
publishable flag, timestamps); the full artifact lives in one JSONB column, write-once, never updated after
a completed run.

## What happens if OpenAI or Tavily fails?

Caught once at the service boundary. A missing credential is checked explicitly before any provider is even
constructed, and maps to a generic "this analysis mode isn't available right now" message, with the real
missing-variable *name* (never a value) logged server-side only. A mid-run provider exception is logged with
a full traceback server-side and mapped to a generic "could not be completed, please try again" — the client
never sees a raw exception, stack trace, or credential fragment either way.

## Why is the analysis synchronous?

It's an accepted, explicit tradeoff for a controlled beta, not an oversight: a real production run measured
39.46 seconds end to end, which is tolerable for a single-request, low-volume feature behind an opt-in
checkbox. If usage ever grew enough to make that a real problem, the next step would be asynchronous job
execution with a polling or websocket-based status — a known, deliberately-deferred piece of future work,
not something I'd claim is already solved.

## How would you scale it?

The honest answer at today's scale is "I haven't needed to" — there's no real production traffic volume yet
to scale against, and I'd rather say that plainly than invent a scaling story. If asked what I'd actually
do: move the acquisition pipeline off the request/response cycle into an async worker/queue so request
latency stops being coupled to provider call latency; add real token-usage/cost instrumentation (currently
absent in production — a documented gap) before scaling spend; and consider read replicas or caching for
the retrieval layer only once there's measured evidence it's the bottleneck, not before.

## What would you change with 100k users?

Move analysis off the synchronous request path (above), add the cost/observability instrumentation that
doesn't exist yet, and build a real, repeatable production evaluation dataset instead of the current mix of
a small calibration harness and point-in-time live-evaluation reports — at that scale, methodology drift
needs a regression gate, not a manual spot-check. I would not change the deterministic-scoring/evidence-
validation architecture itself; that boundary is what the system should scale with, not around.

## How did you test the system?

Layered, matching how much confidence each layer can actually provide: an offline suite for the evidence
engine itself (604 tests, every provider mocked, no real external call); a dedicated integration-test file
for the product-wiring layer (engine selection, ownership-scoped retrieval, error-mapping — 14 tests);
migration-safety tests that directly assert the new engine's table creation never touches the legacy
`analyses` table or VentureGPS V2's schema; VentureGPS V2's own architecture-boundary and domain test suite
(2,226 passing tests); the legacy backend's own security/auth/concurrency suite; and a full frontend suite
(434 tests) plus TypeScript and lint checks. Above all of that: staged live validation — controlled live
evaluations against real companies before touching the product, a local end-to-end pass through a real
authenticated browser, and finally one real, paid production analysis against the live deployed application
with persistence, report rendering, reload behavior, and the unauthenticated-access boundary all
independently re-verified against production itself.

## Tell me about a bug/failure that changed the architecture.

The Retention-dimension incident described above (an LLM-produced score of 7.0 with no evidence backing it)
is the clearest one — it's documented in this repository's own readiness audit, not something I'm
reconstructing from memory. A second, smaller one: during live evaluation of the new engine, I found a
semantic-fit gap — the model could produce a claim that was schema-valid but assigned to a semantically
wrong category. Neither was caught by type-checking or schema validation; both needed a dedicated,
deterministic check written specifically because an LLM's structured output being *syntactically* correct
doesn't mean it's *semantically* correct.

## What code did AI generate versus what engineering decisions did you own?

I used Claude Code throughout this project's development — for implementation, for exploring the codebase,
and for parts of this documentation. The engineering decisions were mine to make and defend: the move to an
evidence-first architecture after finding the scoring-confidence failure, the deterministic/probabilistic
boundary and where exactly to draw it, the choice of a second independent migration environment over the
two more convenient-but-wrong alternatives (extending the legacy schema, or borrowing V2's), the decision to
show Coverage/Confidence instead of an overall score, the feature-flag rollout strategy, and the controlled
production deployment sequence (migrate → deploy disabled → verify baseline → enable → smoke test) and its
own rollback criteria. I can explain and defend every one of those in detail, including the parts I'd do
differently with more time — see "What I would build next" in the case study.
