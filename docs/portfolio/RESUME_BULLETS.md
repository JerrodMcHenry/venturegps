# Resume Bullets

Technically credible, grounded in this repository — no claimed production traffic, customer adoption, or
scale that doesn't exist. Pick the subset that fits the role.

- Designed and deployed a full-stack AI-assisted due-diligence platform (Python/FastAPI, Next.js/
  TypeScript, PostgreSQL) with a server-authoritative feature-flag rollout, authenticated ownership-scoped
  persistence, and an independent database migration boundary; validated end to end in production with a
  real authenticated request through live search/LLM providers.

- Built an evidence-acquisition and validation pipeline that separates probabilistic AI proposal (search,
  structured-output extraction) from deterministic evidence validation and scoring (grounding checks,
  semantic-fit validation, fail-closed publication gates) — architected specifically to prevent a documented
  failure mode where an LLM-assigned score carried no verifiable evidence behind it.

- Implemented production security controls including JWT-based authentication with ownership-scoped,
  non-enumerable resource retrieval; SSRF-hardened external content fetching (private/loopback/metadata-
  address rejection, DNS-rebinding-safe resolution, bounded redirects); and fail-closed behavior for every
  external-dependency and configuration failure path.

- Built the project's testing and migration infrastructure from the ground up: 600+ tests for the evidence
  pipeline, 2,200+ for a separate domain-modeling subsystem with its own architecture-boundary enforcement,
  and a dedicated database-migration-safety suite proving a new persistence layer could never corrupt
  unrelated schema history — plus a CI pipeline exercising all of it on every push.
