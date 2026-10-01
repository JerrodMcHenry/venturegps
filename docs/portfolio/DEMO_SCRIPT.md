# Demo Script

A 3–5 minute technical walkthrough of VentureGPS's Evidence Engine v1, live in production
(`https://app.venturegps.ai/`). This is an engineering demo — the goal is to show judgment and the reasoning
behind specific decisions, not to sell the product. Uses the already-persisted production analysis from the
Task 34 smoke test (`/evidence/3d7f9b043f7f44788e4507c4ee1d36c9`, Notion) — **do not run a new paid
analysis just to give this demo**; the existing one has everything it needs, and reloading it costs
nothing and re-runs no pipeline.

## 1. The problem (20–30 sec)

"Startup due diligence from public information is noisy and incomplete, and an LLM will happily give you a
confident-sounding answer whether or not the evidence actually supports one. The engineering problem I set
out to solve here wasn't 'get an LLM to research a company' — it was 'prevent the system from presenting
the model's opinion as if it were the evidence itself.'"

## 2. Submit a company (20 sec)

Either run the demo live against the Analyze page (`app.venturegps.ai/analyze`, check "Try our evidence-
first analysis (beta)", enter a company name + website) **or**, to avoid a second paid analysis, open the
existing persisted report directly and narrate the submission step from there. If running live: "This mode
currently takes a company name and website — it's intentionally narrower than the legacy flow, which also
accepts pasted text and PDFs, because this is a controlled beta of a newer architecture."

## 3. The loading state (while an analysis runs, if demoing live)

"Notice the loading copy doesn't fake live per-stage progress — it tells you what the pipeline does
(research, evidence review, structuring, methodology, report) without pretending to know which exact step
it's on right now, because the backend doesn't actually report that. Small thing, but it's the same honesty
principle the rest of the product follows: don't claim more certainty than you actually have."

## 4. The report (60–90 sec)

Open the report. Point out, in order:

- **No overall score.** "There's deliberately no single 0–100 number here. Instead: Evidence Coverage —
  how much of the methodology could actually be evaluated from available evidence — and Confidence — how
  sure the engine is in the evidence it gathered, not a prediction of success. Compressing those into one
  score would imply more certainty than the evidence supports."
- **Six pillars, each independently gated.** "Each pillar only gets published if it clears its own
  evidence-coverage floor. [Point at one published, one withheld pillar.] This one published with real
  scored dimensions; this one is explicitly withheld, and it says why — not silently scored low, withheld."

## 5. Evidence and provenance (30 sec)

Expand "All evidence." "Every scored claim traces back to a real excerpt from a real, named public source,
with a link. This isn't a black box — you can go check the exact sentence the engine is relying on."

## 6. The withheld pillar — why refusal to score is a feature (the key moment)

"This is the part I'd want an interviewer to push on. [Open a withheld pillar.] 'Insufficient independent
evidence… this reflects missing or insufficient public evidence, not a negative assessment.' A system that
always produces a confident number is lying by omission when the evidence doesn't actually support one. The
hard engineering work here wasn't making the system score things — it was making it correctly refuse to,
and be honest about why, with a specific measured floor it didn't clear."

## 7. Architecture (45–60 sec)

"Under the hood: user → Next.js → Clerk auth → FastAPI → an analysis service → an engine adapter → real
search and LLM-extraction calls — that part's probabilistic, not reproducible run to run. Everything after
that — canonicalization, a semantic-fit check, contradiction detection, and every score you just saw — is
plain deterministic Python. No model call ever computes a final number. That boundary is enforced in code,
not in a prompt — [open `docs/portfolio/EVIDENCE_ENGINE_V1_ARCHITECTURE.md` if time allows] it's documented
and tested, not just a design intention."

## 8. Close with the engineering lesson

"The real story here isn't 'I built an AI app.' It's that the first version of this scoring system had a
real, documented failure — an LLM-assigned score with zero evidence behind it — and the fix wasn't a better
prompt, it was moving scoring entirely out of the model's hands into deterministic code that can't produce
a number without first passing through a validation stage it can't talk its way around. That's the decision
I'd want to be judged on."

---

**If asked to go further:** `docs/portfolio/ENGINEERING_CASE_STUDY.md` has the full narrative;
`docs/portfolio/INTERVIEW_GUIDE.md` has prepared answers to the likely follow-up questions (scaling,
testing, SSRF, migration design, cost/failure handling).
