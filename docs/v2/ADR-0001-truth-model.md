# ADR-0001: VentureGPS V2 truth model and AI boundary

- **Status:** Accepted (Phase 1, Increment 1)
- **Scope:** everything under `app/v2/`
- **Enforced by:** `app/v2/tests/architecture/` (see "Enforcement")

## Context

VentureGPS is becoming a public intelligence platform whose value depends on
being trustworthy: every important claim must trace to evidence, and every
derived number must be reproducible. The legacy system (`app/ai/*`,
`app/database/db.py`, `app/api.py`) is a founder-analysis product in which LLM
output is stored and scored as if it were fact (for example company identity
keyed on an LLM-extracted name, LLM-generated dimension scores, an LLM
"readiness score"). That design cannot carry V2. A repository audit and the
Phase 1 plan concluded that V2 is built beside legacy, not by reworking it.

## Decision

### 1. Four layers of truth

| Layer | Meaning | Examples | Who may write it |
|---|---|---|---|
| **Observed** | What a source actually exposed, when we acquired it | Observation, raw payload | Ingestion (deterministic) |
| **Canonical** | VentureGPS's resolved representation of real entities/events | Company, aliases, identifiers, later financing events | Only deterministic validation plus a deterministic rule or an explicit human decision |
| **Derived** | Deterministic calculations over canonical data with versioned methodology | Metrics, signals, Market Pulse, approved Radar | Deterministic engines only |
| **Interpretation** | Human/AI explanation | Summaries, narratives, "why" text | Humans or AI, read-only over the layers above |

Interpretation never modifies upstream layers. Observations are immutable.
Corrections to canonical truth preserve provenance (retraction/supersession
records, never silent overwrite). Event time, observed time and recorded time
are distinct.

### 2. The AI boundary

```
External evidence -> Observation
  -> AI (or rule / human) may PROPOSE
  -> typed Candidate
  -> deterministic schema validation
  -> deterministic evidence validation
  -> deterministic rule OR explicit human decision
  -> canonical state
```

- **AI may create candidates.** Extraction, entity matching, classification,
  clustering, summarization and explanation are legitimate uses.
- **AI is never the authority that promotes a candidate into canonical
  truth.** Phase 1 policy: an AI-derived candidate can be promoted only by a
  human decision.
- **Later**, a deterministic, versioned promotion rule may accept an
  AI-produced candidate *after independent deterministic evidence validation*.
  In that case the **rule** is the canonical authority and is recorded as the
  decider, not the model.
- **Never: AI confidence -> canonical truth.** A confident, well-formed model
  answer has no standing by itself.
- AI must not own canonical company identity, merges, event identity, amounts,
  dates without evidence, metrics, signals, Market Pulse, Radar rules,
  methodology/taxonomy versions, provenance, or any deterministic business
  rule.
- **Prompts are soft controls.** They are never an integrity or security
  boundary; deterministic validation is.

### 3. Deterministic core

Everything in `app/v2` except `app/v2/ai` (and tests) is the **deterministic
core**. It must be importable, testable and correct with **no** AI/model
provider SDK installed, **no** AI credentials, and **no** model network access.
If AI is unavailable, canonical and derived behavior is unchanged.

### 4. Package boundary (default-deny)

| Zone | Where | May import |
|---|---|---|
| `ai` | `app/v2/ai/**` | Provider SDKs; `app.v2.domain`; `app.v2.resolution.ports`. **Not** repositories/db/workers, SQL drivers, or any legacy `app.*`. |
| `wiring` | `app/v2/wiring.py` (composition root, does not exist yet) | The only non-`ai` module allowed to import `app.v2.ai` |
| `deterministic` | every other `app/v2/**` package, including ones not yet created | `app.v2.*` (not `ai`), stdlib, general libraries. **Not** provider SDKs, `app.v2.ai`, legacy `app.*`, or AI/search credentials |

The dependency points inward: interfaces the AI implements (for example a
candidate-proposer port) are owned by the deterministic side, and AI code
depends on them, never the reverse. AI code has no database handle; a
deterministic orchestrator persists whatever it returns.

### 5. Strangler migration and legacy freeze

V2 lives in `app/v2/` (and, from Increment 2, its own Postgres schema `v2`)
beside legacy. V2 imports no legacy code. Legacy behavior is not changed by V2
work. Legacy DDL is **frozen**: no new `add_*`/`create_*` functions run at
import in `app/database/db.py` / `app/api.py`; new schema is added through
versioned migrations. Old AI-generated analyses are not evidence and are not
migrated into canonical V2 truth.

## Consequences

- Untrusted or AI-derived information cannot reach canonical state without
  passing deterministic checks; unsupported claims are rejected or
  quarantined, visibly.
- The deterministic core stays cheap to test and cannot be broken by a
  provider outage or key rotation.
- More ceremony than the legacy "call the model, store the result" style.
  Accepted deliberately.
- Static import scanning is a tripwire, not a proof: it cannot see
  string-built module names. A runtime probe (below) complements it, and code
  review remains necessary.

## Enforcement

`app/v2/tests/architecture/` (run with `pytest`; rules are data in
`boundary_rules.py`, so new packages/dependencies are a one-line edit):

- deterministic code cannot import `app.v2.ai`, model-provider SDKs, or legacy
  `app.*`, and cannot reference `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` or
  `TAVILY_API_KEY`;
- `app.v2.ai` cannot import V2 repositories/db/workers, SQL drivers/ORM/
  migration tooling, other V2 packages outside its allowlist, or legacy code;
- unresolvable dynamic imports fail closed;
- the scanner is itself tested against deliberately invalid samples;
- a clean-subprocess probe imports the V2 packages and inspects `sys.modules`
  for transitive leaks;
- V2 tests run with AI credentials removed from the environment;
- pytest refuses to collect anything outside `app/v2` (legacy tests are
  scripts that use the real database).

## Alternatives considered

- **Rework legacy in place.** Rejected: its core pipeline stores LLM output as
  truth; retrofitting the boundary would touch a 4,469-line `app/api.py` and a
  7,101-line `app/database/db.py`.
- **Convention/prompt-based AI restrictions.** Rejected: prompts and code
  review alone do not enforce a hard architectural invariant.
